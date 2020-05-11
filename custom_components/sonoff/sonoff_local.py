import ipaddress
import json
import logging
from base64 import b64encode, b64decode
from typing import Callable, List

from aiohttp import ClientSession
from zeroconf import ServiceBrowser, Zeroconf, ServiceStateChange

from Crypto.Cipher import AES
from Crypto.Hash import MD5
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

_LOGGER = logging.getLogger(__name__)


def encrypt(payload: dict, devicekey: str):
    devicekey = devicekey.encode('utf-8')

    hash_ = MD5.new()
    hash_.update(devicekey)
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


def decrypt(payload: dict, devicekey: str):
    try:
        devicekey = devicekey.encode('utf-8')

        hash_ = MD5.new()
        hash_.update(devicekey)
        key = hash_.digest()

        encoded = ''.join([payload[f'data{i}'] for i in range(1, 4, 1)
                           if f'data{i}' in payload])

        cipher = AES.new(key, AES.MODE_CBC, iv=b64decode(payload['iv']))
        ciphertext = b64decode(encoded)
        padded = cipher.decrypt(ciphertext)
        return unpad(padded, AES.block_size)

    except:
        return None


class EWeLinkLocal:
    _devices: dict = None
    _handlers = None
    _zeroconf = None

    def __init__(self, session: ClientSession):
        self.session = session

    @property
    def started(self) -> bool:
        return self._zeroconf is not None

    def start(self, handlers: List[Callable], devices: dict = None,
              zeroconf: Zeroconf = None):
        self._handlers = handlers
        self._devices = devices or {}
        self._zeroconf = zeroconf or Zeroconf()
        browser = ServiceBrowser(self._zeroconf, '_ewelink._tcp.local.',
                                 handlers=[self._zeroconf_handler])
        # for beautiful logs
        browser.name = 'Sonoff_LAN'

    def stop(self, *args):
        self._zeroconf.close()

    def _zeroconf_handler(self, zeroconf: Zeroconf, service_type: str,
                          name: str, state_change: ServiceStateChange):
        """Стандартная функция ServiceBrowser."""
        if state_change == ServiceStateChange.Removed:
            _LOGGER.debug(f"Local2 <= {name}")
            # TODO: handle removed
            return

        info = zeroconf.get_service_info(service_type, name)
        properties = {
            k.decode(): v.decode() if isinstance(v, bytes) else v
            for k, v in info.properties.items()
        }

        deviceid = properties['id']
        device = self._devices.setdefault(deviceid, {})

        if properties.get('encrypt'):
            devicekey = device.get('devicekey')
            if devicekey == 'skip':
                return
            if not devicekey:
                _LOGGER.warning(f"No devicekey for device {deviceid}")
                # skip device next time
                device['devicekey'] = 'skip'
                return

            data = decrypt(properties, devicekey)
            # Fix Sonoff RF Bridge sintax bug
            if data.startswith(b'{"rf'):
                data = data.replace(b'"="', b'":"')
        else:
            data = ''.join([properties[f'data{i}'] for i in range(1, 4, 1)
                            if f'data{i}' in properties])

        state = json.loads(data)

        _LOGGER.debug(f"Local{state_change.value} <= id: {properties['id']}, "
                      f"seq: {properties.get('seq')} | {state}")

        host = str(ipaddress.ip_address(info.addresses[0]))
        # update every time device host change (alsow first time)
        if device.get('host') != host:
            # state connection for attrs update
            state['connection'] = 'local'
            # device host for local connection, state host for attrs update
            device['host'] = state['host'] = host
            # override device type with: strip, plug, light, rf
            device['type'] = properties['type']
            # update or set device init state
            if 'params' in device:
                device['params'].update(state)
            else:
                device['params'] = state

        for handler in self._handlers:
            handler(deviceid, state, properties.get('seq'))

    async def send(self, deviceid: str, data: dict, sequence: str, timeout=5):
        device: dict = self._devices[deviceid]
        if 'host' not in device:
            _LOGGER.warning(f"Local4 => id: {deviceid} | Unknown IP address")
            return False

        # cmd for D1 and RF Bridge 433
        command = data.get('cmd') or next(iter(data))

        # TODO: check `seq` param
        payload = {
            'sequence': sequence,
            'deviceid': deviceid,
            'selfApikey': '123',
            'data': data
        }

        if 'devicekey' in device:
            payload = encrypt(payload, device['devicekey'])

        _LOGGER.debug(f"Local4 => id: {deviceid} | {data}")

        try:
            r = await self.session.post(
                f"http://{device['host']}:8081/zeroconf/{command}",
                json=payload, timeout=timeout)
            resp = await r.json()
            if resp['error'] == 0:
                return True

            _LOGGER.warning(f"Local4 => id: {deviceid} | {resp}")

        except:
            _LOGGER.warning(f"Local4 => id: {deviceid} | "
                            f"Send timeout {timeout}")

        return False
