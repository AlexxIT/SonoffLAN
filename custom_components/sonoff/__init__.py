import ipaddress
import json
import logging
import time
from functools import lru_cache
from typing import Callable, Optional

import voluptuous as vol
from aiohttp import ClientSession
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_DEVICES, \
    CONF_NAME, CONF_DEVICE_CLASS, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import ServiceCall
from homeassistant.helpers import config_validation as cv, discovery
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import HomeAssistantType

from zeroconf import ServiceBrowser, Zeroconf
from . import utils

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'sonoff'

CONF_RELOAD = 'reload'
CONF_DEFAULT_CLASS = 'default_class'

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional(CONF_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_RELOAD, default='once'): cv.string,
        vol.Optional(CONF_DEFAULT_CLASS, default='switch'): cv.string,
        vol.Optional(CONF_DEVICES): {
            cv.string: vol.Schema({
                vol.Optional(CONF_NAME): cv.string,
                vol.Optional(CONF_DEVICE_CLASS): vol.Any(str, list),
                vol.Optional('devicekey'): cv.string,
            }, extra=vol.ALLOW_EXTRA),
        },
    }, extra=vol.ALLOW_EXTRA),
}, extra=vol.ALLOW_EXTRA)

ZEROCONF_NAME = 'eWeLink_{}._ewelink._tcp.local.'


async def async_setup(hass: HomeAssistantType, hass_config: dict):
    utils.init_zeroconf_singleton(hass)

    config = hass_config[DOMAIN]

    # load devices from file in config dir
    filename = hass.config.path('.sonoff.json')
    devices = utils.load_cache(filename)

    session = async_get_clientsession(hass)

    # reload devices from ewelink servers
    if CONF_USERNAME in config and CONF_PASSWORD in config:
        reload = config.get(CONF_RELOAD, 'once')
        if not devices or reload == 'always':
            _LOGGER.debug("Load device list from ewelink servers")
            newdevices = await utils.load_devices(
                config[CONF_USERNAME], config[CONF_PASSWORD], session)
            if newdevices is not None:
                newdevices = {p['deviceid']: p for p in newdevices}
                utils.save_cache(filename, newdevices)
                devices = newdevices

    # load devices from configuration.yaml
    if not devices:
        devices = config.get(CONF_DEVICES, {})

    # concat ewelink devices with yaml devices
    elif CONF_DEVICES in config:
        for deviceid, devicecfg in config[CONF_DEVICES].items():
            if deviceid in devices:
                _LOGGER.debug(f"Update device config {deviceid}")
                # TODO: check update
                devices[deviceid].update(devicecfg)
            else:
                _LOGGER.debug(f"Add device config {deviceid}")
                devices[deviceid] = devicecfg

    hass.data[DOMAIN] = devices

    default_class = config[CONF_DEFAULT_CLASS]
    utils.init_device_class(default_class)

    def add_device(devicecfg: dict, state: dict):
        """Add device to Home Assistant.

        :param devicecfg: device config (deviceid, devicekey, device_class...)
        :param state: init state of device (switch)
        """
        deviceid = devicecfg['deviceid']

        device_class = devicecfg.get('device_class')
        if not device_class:
            device_class = utils.guess_device_class(devicecfg)

        if not device_class:
            _LOGGER.warning(f"Please, send this device type to developer: "
                            f"{devicecfg['type']}")

            # Fallback guess device_class from device state
            if 'switch' in state:
                device_class = default_class
            elif 'switches' in state:
                device_class = [default_class] * 4
            else:
                device_class = 'binary_sensor'

        if isinstance(device_class, str):
            # read single device_class
            info = {'deviceid': deviceid, 'channels': None}
            hass.async_create_task(discovery.async_load_platform(
                hass, device_class, DOMAIN, info, hass_config))
        else:
            # read multichannel device_class
            for i, component in enumerate(device_class, 1):
                # read device with several channels
                if isinstance(component, dict):
                    if 'device_class' in component:
                        # backward compatibility
                        channels = component['channels']
                        component = component['device_class']
                    else:
                        component, channels = list(component.items())[0]

                    if isinstance(channels, int):
                        channels = [channels]
                else:
                    channels = [i]

                info = {'deviceid': deviceid, 'channels': channels}
                hass.async_create_task(discovery.async_load_platform(
                    hass, component, DOMAIN, info, hass_config))

    listener = EWeLinkListener(devices, session)
    listener.listen(add_device)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, listener.stop)

    async def send_command(call: ServiceCall):
        data = dict(call.data)

        deviceid = str(data.pop('device'))
        command = data.pop('command')

        device = devices.get(deviceid)
        if isinstance(device, EWeLinkDevice):
            await device.send(command, data)
        else:
            _LOGGER.error(f"Device {deviceid} not found")

    hass.services.async_register(DOMAIN, 'send_command', send_command)

    return True


class EWeLinkListener:
    def __init__(self, devices: dict, session: ClientSession):
        """Ищет устройства ewelink в локально сети.

        :param devices: словарь настроек устройств, где ключ - deviceid
        """
        self.devices = devices
        self.session = session

        self._add_device = None
        self._zeroconf = None

    def listen(self, add_device: Callable):
        """Начать поиск всех устройств Sonoff в сети.

        :param add_device: функция, которая будет вызываться при обнаружении
        нового устройства
        """
        from homeassistant.components.zeroconf import Zeroconf
        self._add_device = add_device
        self._zeroconf = Zeroconf()
        ServiceBrowser(self._zeroconf, '_ewelink._tcp.local.', listener=self)

    def stop(self, *args):
        self._zeroconf.close()

    def add_service(self, zeroconf: Zeroconf, type_: str, name: str):
        """Стандартная функция ServiceBrowser."""
        _LOGGER.debug(f"Add service {name}")

        info = zeroconf.get_service_info(type_, name)

        properties = {
            k.decode(): v.decode() if isinstance(v, bytes) else v
            for k, v in info.properties.items()
        }

        _LOGGER.debug(f"Properties: {properties}")

        host = str(ipaddress.ip_address(info.address))
        deviceid = properties['id']

        device = self.devices.get(deviceid)
        if isinstance(device, EWeLinkDevice):
            # TODO: check update host
            device.host = host
            return
        else:
            config: dict = device or {}

        if properties.get('encrypt'):
            # Если нет ключа - не добавляем устройство
            devicekey = config.get('devicekey')
            if not devicekey:
                _LOGGER.warning(f"No devicekey for device {deviceid}")
                return

            data = utils.decrypt(properties, devicekey)
            # Fix Sonoff RF Bridge sintax bug
            if data.startswith(b'{"rf'):
                data = data.replace(b'"="', b'":"')
        else:
            data = ''.join([properties[f'data{i}'] for i in range(1, 4, 1)
                            if f'data{i}' in properties])

        state = json.loads(data)
        _LOGGER.debug(f"State: {state}")

        if 'deviceid' not in config:
            config['deviceid'] = deviceid

        # strip, plug, light, rf
        config['type'] = properties['type']

        self.devices[deviceid] = EWeLinkDevice(host, config, state, zeroconf,
                                               self.session)

        self._add_device(config, state)

    def remove_service(self, zeroconf: Zeroconf, type: str, name: str):
        """Стандартная функция ServiceBrowser."""
        _LOGGER.debug(f"Remove service {name}")


class EWeLinkDevice:
    """Класс, реализующий протокол взаимодействия с устройством."""

    def __init__(self, host: str, config: dict, state: dict,
                 zeroconf: Zeroconf, session: ClientSession):
        """
        :param host: IP-адрес устройства (для отправки на него команд)
        :param config: конфиг устройства (deviceid, devicekey...)
        :param state: начальное состояние устройства
        :param zeroconf: Zeroconf для получения новых состояний устройства
        """
        self.host = host
        self.config = config
        self.state = state
        self._session = session
        self._zeroconf = zeroconf

        self._browser = None
        self._update_handlers = []
        self._seq = None

    @property
    @lru_cache()
    def deviceid(self):
        return self.config['deviceid']

    @property
    @lru_cache()
    def devicekey(self):
        return self.config.get('devicekey')

    def name(self, channels: Optional[list] = None):
        if channels and len(channels) == 1:
            ch = str(channels[0] - 1)
            return self.config.get('tags', {}).get('ck_channel_name', {}). \
                       get(ch) or self.config.get('name')

        return self.config.get('name')

    def listen(self, update_device: Callable):
        """Начать принимать изменение состояния устройства.

        :param update_device: функция, которая будет вызываться при получении
            новых данных от устройства
        """
        self._update_handlers.append(update_device)

        if not self._browser:
            service = ZEROCONF_NAME.format(self.deviceid)
            self._browser = ServiceBrowser(self._zeroconf, service,
                                           listener=self)

    def update_service(self, zeroconf: Zeroconf, type_: str, name: str):
        """Событие Zeroconf, которое вызывается при изменении состояния
        устройства.
        """
        _LOGGER.debug(f"Update service {name}")

        info = zeroconf.get_service_info(type_, name)

        properties = {
            k.decode(): v.decode() if isinstance(v, bytes) else v
            for k, v in info.properties.items()
        }

        _LOGGER.debug(f"Properties: {properties}")

        # for some users devices send updates several times
        if 'seq' in properties:
            if self._seq == properties['seq']:
                return

            self._seq = properties['seq']

        if properties.get('encrypt'):
            data = utils.decrypt(properties, self.config['devicekey'])
            # Fix Sonoff RF Bridge sintax bug
            if data.startswith(b'{"rf'):
                data = data.replace(b'"="', b'":"')
        else:
            data = ''.join([properties[f'data{i}'] for i in range(1, 4, 1)
                            if f'data{i}' in properties])

        self.state = json.loads(data)
        _LOGGER.debug(f"State: {self.state}")

        for handler in self._update_handlers:
            handler(self)

    def is_on(self, channels: Optional[list]):
        """Включены ли указанные каналы.

        :param channels: Список каналов для проверки, либо None
        :return: Список bool, либо один bool соответственно
        """
        if channels:
            switches = self.state['switches']
            return [
                switches[channel - 1]['switch'] == 'on'
                for channel in channels
            ]
        else:
            return self.state['switch'] == 'on'

    async def send(self, command: str, data: dict):
        """Послать команду на устройство.

        :param command: Команда (switch, switches и т.п.)
        :param data: Данные для команды
        :return:
        """
        payload = {
            'sequence': str(int(time.time())),
            'deviceid': self.deviceid,
            'selfApikey': '123',
            'data': data
        }

        if self.devicekey:
            payload = utils.encrypt(payload, self.devicekey)

        _LOGGER.debug(f"Send {command} to {self.deviceid}: {payload}")

        try:
            r = await self._session.post(
                f"http://{self.host}:8081/zeroconf/{command}",
                json=payload)
            _LOGGER.debug(await r.text())
            resp = await r.json()
            if resp['error'] != 0:
                _LOGGER.warning(
                    f"Error when send {command} to {self.deviceid}")
        except:
            _LOGGER.warning(f"Can't send {command} to {self.deviceid}")

    @property
    @lru_cache()
    def is_th_3_4_0(self):
        return self.state.get('deviceType') in ('normal', 'temperature')

    async def turn_on(self, channels: Optional[list]):
        """Включает указанные каналы.

        :param channels: Список каналов, либо None
        """
        if channels:
            switches = [
                {'outlet': channel - 1, 'switch': 'on'}
                for channel in channels
            ]
            await self.send('switches', {'switches': switches})
        elif self.is_th_3_4_0:
            await self.send('switch', {'switch': 'on', 'mainSwitch': 'on',
                                       'deviceType': 'normal'})
        else:
            await self.send('switch', {'switch': 'on'})

    async def turn_off(self, channels: Optional[list]):
        """Выключает указанные каналы.

        :param channels: Список каналов, либо None
        """
        if channels:
            switches = [
                {'outlet': channel - 1, 'switch': 'off'}
                for channel in channels
            ]
            await self.send('switches', {'switches': switches})
        elif self.is_th_3_4_0:
            await self.send('switch', {'switch': 'off', 'mainSwitch': 'off',
                                       'deviceType': 'normal'})
        else:
            await self.send('switch', {'switch': 'off'})

    async def turn_bulk(self, channels: dict):
        """Включает, либо выключает указанные каналы.

        :param channels: Словарь каналов, ключ - номер канала, значение - bool
        """
        switches = [
            {'outlet': channel - 1, 'switch': 'on' if switch else 'off'}
            for channel, switch in channels.items()
        ]
        await self.send('switches', {'switches': switches})

    async def transmit(self, channel: int):
        await self.send('transmit', {"rfChl": channel})

    async def learn(self, channel: int):
        await self.send('capture', {"rfChl": channel})
