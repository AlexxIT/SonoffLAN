import json
import logging
import os
import time
from typing import Optional, List, Callable

from aiohttp import ClientSession

from .sonoff_cloud import EWeLinkCloud
from .sonoff_local import EWeLinkLocal

_LOGGER = logging.getLogger(__name__)

ATTRS = ('connection', 'host', 'rssi', 'humidity', 'temperature', 'power',
         'current', 'voltage', 'battery')

# map cloud attrs to local attrs
ATTRS_MAP = {
    'currentTemperature': 'temperature',
    'currentHumidity': 'humidity'
}

EMPTY_DICT = {}


def load_cache(filename: str):
    """Load device list from file."""
    if os.path.isfile(filename):
        try:
            with open(filename, 'rt', encoding='utf-8') as f:
                return json.load(f)
        except:
            _LOGGER.error("Can't read cache file.")
    return None


def save_cache(filename: str, data: dict):
    """Save device list to file."""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))


def get_attrs(state: dict) -> dict:
    for k in ATTRS_MAP:
        if k in state:
            state[ATTRS_MAP[k]] = state.pop(k)

    return {k: state[k] for k in ATTRS if k in state}


class EWeLinkRegistry:
    """
    device:
      deviceid: str
      params: dict, init state
      connection: str, connection type (local, cloud, error)
      host: str, local IP
      uiid: int, cloud type
      type: str, local type (strip, plug, light, rf)
      handlers: list, update handlers
    """
    devices: Optional[dict] = None

    def __init__(self, session: ClientSession):
        self._cloud = EWeLinkCloud(session)
        self._local = EWeLinkLocal(session)

    def _registry_handler(self, deviceid: str, state: dict, sequence: str):
        """Feedback from local and cloud connections

        :param deviceid: example `1000abcdefg`
        :param data: example `{'switch': 'on'}`
        :param sequence: message serial number to verify uniqueness
        """
        device = self.devices.get(deviceid)
        if not device:
            _LOGGER.warning(f"Unknown deviceid: {deviceid}")
            return

        # skip update with same sequence (from cloud and local or from local)
        if sequence:
            if device.get('seq') == sequence:
                return
            device['seq'] = sequence

        if 'handlers' in device:
            attrs = get_attrs(state)
            try:
                for handler in device['handlers']:
                    handler(state, attrs)
            except Exception as e:
                _LOGGER.exception(f"Registry update error: {e}")

    def concat_devices(self, newdevices: dict):
        """Concat current device list with new device list."""
        if self.devices:
            for deviceid, devicecfg in newdevices.items():
                if deviceid in self.devices:
                    self.devices[deviceid].update(devicecfg)
                else:
                    self.devices[deviceid] = devicecfg

        else:
            self.devices = newdevices

    def cache_load_devices(self, cachefile: str):
        """Load devices from cache."""
        self.devices = load_cache(cachefile)

    async def cloud_login(self, username: str, password: str):
        return await self._cloud.login(username, password)

    async def cloud_load_devices(self, cachefile: str = None):
        """Load devices list from Cloud Servers."""
        newdevices = await self._cloud.load_devices()
        if newdevices is not None:
            newdevices = {p['deviceid']: p for p in newdevices}
            if cachefile:
                save_cache(cachefile, newdevices)
            self.devices = newdevices

    async def cloud_start(self):
        if self.devices is None:
            self.devices = {}

        await self._cloud.start([self._registry_handler], self.devices)

    async def local_start(self, handlers: List[Callable]):
        if self.devices is None:
            self.devices = {}

        if handlers:
            handlers.append(self._registry_handler)
        else:
            handlers = [self._registry_handler]

        self._local.start(handlers, self.devices)

    async def stop(self):
        # TODO: do something
        pass

    async def send(self, deviceid: str, params: dict):
        """Send command to device."""
        sequence = str(int(time.time() * 1000))

        connection = 'error'

        if self._local.started and self._cloud.started:
            # try to send a command locally (wait no more than a second)
            if await self._local.send(deviceid, params, sequence, 1):
                connection = 'local'
            # otherwise send a command through the cloud
            elif await self._cloud.send(deviceid, params, sequence):
                connection = 'cloud'

        elif self._local.started:
            if await self._local.send(deviceid, params, sequence, 5):
                connection = 'local'

        elif self._cloud.started:
            if await self._cloud.send(deviceid, params, sequence):
                connection = 'cloud'

        # update device attrs
        for handler in self.devices[deviceid]['handlers']:
            handler(EMPTY_DICT, {'connection': connection})


class EWeLinkDevice:
    registry: EWeLinkRegistry = None
    deviceid: str = None
    channels: list = None
    _available: bool = True
    _attrs: dict = None
    _name: str = None
    _is_on: bool = None
    _is_th_3_4_0: bool = False

    def __init__(self, registry: EWeLinkRegistry, deviceid: str,
                 channels: list = None):
        self.registry = registry
        self.deviceid = deviceid
        self.channels = channels

    def _init(self, force_refresh: bool = True):
        device: dict = self.registry.devices[self.deviceid]

        try:
            # https://developers.home-assistant.io/docs/device_registry_index/
            self._attrs = {
                'manufacturer': device['brandName'],
                'model': device['productModel'],
                'sw_version': f"{device['extra']['extra']['model']} "
                              f"v{device['params']['fwVersion']}"
            }
        except:
            self._attrs = {}

        # Присваиваем имя устройства только на этом этапе, чтоб в `entity_id`
        # было "sonoff_{unique_id}". Если имя присвоить в конструкторе - в
        # `entity_id` попадёт имя в латинице.
        if self.channels and len(self.channels) == 1:
            ch = str(self.channels[0] - 1)
            self._name = device.get('tags', {}).get('ck_channel_name', {}). \
                             get(ch) or device.get('name')
        else:
            self._name = device.get('name')

        self._is_th_3_4_0 = 'mainSwitch' in device['params']

        # init update_handler
        device['handlers'].append(self._update_handler)

        if force_refresh:
            state = device['params']
            attrs = get_attrs(state)
            self._update_handler(state, attrs)

    def _is_on_list(self, state: dict) -> List[bool]:
        if self.channels:
            switches = state['switches']
            return [
                switches[channel - 1]['switch'] == 'on'
                for channel in self.channels
            ]
        else:
            return [state['switch'] == 'on']

    def _update_handler(self, state: dict, attrs: dict):
        raise NotImplemented

    async def _turn_on(self):
        if self.channels:
            switches = [
                {'outlet': channel - 1, 'switch': 'on'}
                for channel in self.channels
            ]
            await self.registry.send(self.deviceid, {'switches': switches})
        elif self._is_th_3_4_0:
            await self.registry.send(self.deviceid, {
                'switch': 'on', 'mainSwitch': 'on', 'deviceType': 'normal'})
        else:
            await self.registry.send(self.deviceid, {'switch': 'on'})

    async def _turn_off(self):
        if self.channels:
            switches = [
                {'outlet': channel - 1, 'switch': 'off'}
                for channel in self.channels
            ]
            await self.registry.send(self.deviceid, {'switches': switches})
        elif self._is_th_3_4_0:
            await self.registry.send(self.deviceid, {
                'switch': 'off', 'mainSwitch': 'off', 'deviceType': 'normal'})
        else:
            await self.registry.send(self.deviceid, {'switch': 'off'})

    async def _turn_bulk(self, channels: dict):
        """Включает, либо выключает указанные каналы.

        :param channels: Словарь каналов, ключ - номер канала, значение - bool
        """
        switches = [
            {'outlet': channel - 1, 'switch': 'on' if switch else 'off'}
            for channel, switch in channels.items()
        ]
        await self.registry.send(self.deviceid, {'switches': switches})
