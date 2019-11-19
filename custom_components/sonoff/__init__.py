import ipaddress
import json
import logging
import time
from base64 import b64decode
from base64 import b64encode
from functools import lru_cache
from typing import Callable

import requests
from Crypto.Cipher import AES
from Crypto.Hash import MD5
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad
from Crypto.Util.Padding import unpad
from homeassistant.helpers.discovery import load_platform

from zeroconf import ServiceBrowser, Zeroconf

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'sonoff'

ZEROCONF_NAME = 'eWeLink_{}._ewelink._tcp.local.'


def setup(hass, config):
    hass.data[DOMAIN] = devices = config[DOMAIN].get('devices', [])

    def add_device(deviceid: str, data: dict):
        info = {'deviceid': deviceid, 'data': data}
        load_platform(hass, 'switch', DOMAIN, info, config)

    listener = EWeLinkListener(devices)
    listener.listen(add_device)

    return True


def encrypt(payload: dict, apikey: str):
    apikey = apikey.encode('utf-8')

    hash_ = MD5.new()
    hash_.update(apikey)
    key = hash_.digest()

    iv = get_random_bytes(16)
    plaintext = json.dumps(payload['data']).encode('utf-8')

    cipher = AES.new(key, AES.MODE_CBC, iv=iv)
    padded = pad(plaintext, AES.block_size)
    ciphertext = cipher.encrypt(padded)

    payload['encrypt'] = True
    payload['iv'] = b64encode(iv).decode('utf-8')
    payload['data'] = b64encode(ciphertext).decode('utf-8')

    return payload


def decrypt(payload: dict, apikey: str):
    try:
        apikey = apikey.encode('utf-8')

        hash_ = MD5.new()
        hash_.update(apikey)
        key = hash_.digest()

        encoded = ''.join([payload[f'data{i}'] for i in range(1, 4, 1) if
                           f'data{i}' in payload])

        cipher = AES.new(key, AES.MODE_CBC, iv=b64decode(payload['iv']))
        ciphertext = b64decode(encoded)
        padded = cipher.decrypt(ciphertext)
        return unpad(padded, AES.block_size)

    except:
        _LOGGER.warning("Decrypt error")
        return None


class EWeLinkListener:
    def __init__(self, devices):
        self.devices = devices

        self._add_device = None

    def listen(self, add_device: Callable):
        """Начать поиск всех устройств Sonoff в сети.

        :param add_device: функция, которая будет вызываться при обнаружении
        нового устройства
        """
        self._add_device = add_device

        zeroconf = Zeroconf()
        ServiceBrowser(zeroconf, '_ewelink._tcp.local.', listener=self)

    @lru_cache()
    def get_config(self, deviceid: str):
        """Получение конфига устройства по его deviceid."""
        return next((p for p in self.devices if p['deviceid'] == deviceid), {})

    def add_service(self, zeroconf: Zeroconf, type_: str, name: str):
        _LOGGER.debug(f"Add service {name}")

        info = zeroconf.get_service_info(type_, name)

        properties = {
            k.decode(): v.decode() if isinstance(v, bytes) else v
            for k, v in info.properties.items()
        }

        _LOGGER.debug(f"Properties: {properties}")

        host = str(ipaddress.ip_address(info.address))
        deviceid = properties['id']

        config = self.devices.get(deviceid, {})
        if isinstance(config, EWeLinkDevice):
            config.host = host
            return

        if properties.get('encrypt'):
            # Если нет ключа - не добавляем устройство
            apikey = config.get('apikey')
            if not apikey:
                _LOGGER.warning(f"No apikey for device {deviceid}")
                return

            data = decrypt(properties, apikey)
            data = json.loads(data)
            _LOGGER.debug(f"Data: {data}")
        else:
            raise NotImplementedError()

        self.devices[deviceid] = device = \
            EWeLinkDevice(host, deviceid, config, zeroconf)

        self._add_device(deviceid, data)

    def remove_service(self, zeroconf: Zeroconf, type: str, name: str):
        _LOGGER.debug(f"Remove service {name}")


class EWeLinkDevice:
    """Класс, реализующий протокол взаимодействия с устройством."""

    def __init__(self, host: str, deviceid: str, config: dict,
                 zeroconf: Zeroconf = None):
        self.host = host
        self.deviceid = deviceid
        self.config = config
        self.zeroconf = zeroconf

        self._browser = None
        self._update_handlers = []

    def listen(self, update_device: Callable):
        """Начать принимать изменение состояния устройства.

        :param update_device: функция, которая будет вызываться при получении
            новых данных от устройства
        """
        self._update_handlers.append(update_device)

        if not self._browser:
            service = ZEROCONF_NAME.format(self.deviceid)
            self._browser = ServiceBrowser(self.zeroconf, service,
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

        if properties.get('encrypt'):
            data = decrypt(properties, self.config['apikey'])
            data = json.loads(data)
            _LOGGER.debug(f"Data: {data}")
        else:
            raise NotImplementedError()

        for handler in self._update_handlers:
            handler(data)

    def send(self, command: str, data: dict):
        """Послать команду на устройство."""
        _LOGGER.debug(f"Send {command} to {self.deviceid}")

        payload = encrypt({
            'sequence': str(int(time.time())),
            'deviceid': self.deviceid,
            'selfApikey': '123',
            'data': data
        }, self.config['apikey'])

        try:
            requests.post(f'http://{self.host}:8081/zeroconf/{command}',
                          json=payload, timeout=5)
        except:
            _LOGGER.warning(f"Can't send {command} to {self.deviceid}")
