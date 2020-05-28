import asyncio
import ipaddress
import json
import logging
import time
from base64 import b64encode, b64decode
from typing import Callable, List

from Crypto.Cipher import AES
from Crypto.Hash import MD5
from Crypto.Random import get_random_bytes
from aiohttp import ClientSession, ClientOSError

from zeroconf import ServiceBrowser, Zeroconf, ServiceStateChange

_LOGGER = logging.getLogger(__name__)


# some venv users don't have Crypto.Util.Padding
# I don't know why pycryptodome is not installed on their systems
# https://github.com/AlexxIT/SonoffLAN/issues/129

def pad(data_to_pad: bytes, block_size: int):
    padding_len = block_size - len(data_to_pad) % block_size
    padding = bytes([padding_len]) * padding_len
    return data_to_pad + padding


def unpad(padded_data: bytes, block_size: int):
    padding_len = padded_data[-1]
    return padded_data[:-padding_len]


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
        self.loop = asyncio.get_event_loop()

    @property
    def started(self) -> bool:
        return self._zeroconf is not None

    def start(self, handlers: List[Callable], devices: dict = None):
        self._handlers = handlers
        self._devices = devices
        self._zeroconf = Zeroconf()
        browser = ServiceBrowser(self._zeroconf, '_ewelink._tcp.local.',
                                 handlers=[self._zeroconf_handler])
        # for beautiful logs
        browser.name = 'Sonoff_LAN'

    def stop(self, *args):
        self._zeroconf.close()

    def _zeroconf_handler(self, zeroconf: Zeroconf, service_type: str,
                          name: str, state_change: ServiceStateChange):
        if state_change == ServiceStateChange.Removed:
            _LOGGER.debug(f"Zeroconf Removed: {name}")
            # TTL of record 5 minutes
            deviceid = name[8:18]
            # _LOGGER.debug(f"{deviceid} <= Local2 | Zeroconf Removed Event")
            # check if device added
            if 'handlers' in self._devices[deviceid]:
                coro = self.check_offline(deviceid)
                self.loop.create_task(coro)
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
                _LOGGER.info(f"{deviceid} <= Local{state_change.value} | "
                             f"No devicekey for device")
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

        _LOGGER.debug(f"{deviceid} <= Local{state_change.value} | {state}")

        host = str(ipaddress.ip_address(info.addresses[0]))
        # update every time device host change (alsow first time)
        if device.get('host') != host:
            # state connection for attrs update
            state['local'] = 'online'
            # device host for local connection
            device['host'] = host
            # update or set device init state
            if 'params' in device:
                device['params'].update(state)
            else:
                device['params'] = state
                # set uiid with: strip, plug, light, rf
                device['uiid'] = properties['type']

        for handler in self._handlers:
            handler(deviceid, state, properties.get('seq'))

    async def check_offline(self, deviceid: str):
        """Try to get response from device after received Zeroconf Removed."""
        log = f"{deviceid} => Local4"
        device = self._devices[deviceid]
        if device.get('check_offline') or device['host'] is None:
            _LOGGER.debug(f"{log} | Skip parallel checks")
            return

        device['check_offline'] = True
        sequence = str(int(time.time() * 1000))

        for t in range(20, 61, 20):
            _LOGGER.debug(f"{log} | Check offline with timeout {t}s")

            t0 = time.time()

            conn = await self.send(deviceid, {'cmd': 'info'}, sequence, t)
            if conn == 'online':
                device['check_offline'] = False
                _LOGGER.debug(f"{log} | Welcome back!")
                return

            if t < 60 and conn != 'timeout':
                # sometimes need to wait more
                await asyncio.sleep(t - time.time() + t0)

        _LOGGER.debug(f"{log} | Device offline")

        device['check_offline'] = False
        device['host'] = None

        for handler in self._handlers:
            handler(deviceid, {'local': 'offline'}, None)

    async def send(self, deviceid: str, data: dict, sequence: str, timeout=5):
        device: dict = self._devices[deviceid]

        # cmd for D1 and RF Bridge 433
        command = data.get('cmd') or next(iter(data))

        payload = {
            'sequence': sequence,
            'deviceid': deviceid,
            'selfApikey': '123',
            'data': data
        }

        if 'devicekey' in device:
            payload = encrypt(payload, device['devicekey'])

        log = f"{deviceid} => Local4 | {data}"

        try:
            r = await self.session.post(
                f"http://{device['host']}:8081/zeroconf/{command}",
                json=payload, timeout=timeout)
            resp = await r.json()
            err = resp['error']
            # no problem with any response from device for info command
            if err == 0 or command == 'info':
                _LOGGER.debug(f"{log} <= {resp}")
                return 'online'
            else:
                _LOGGER.warning(f"{log} <= {resp}")
                return f"E#{err}"

        except asyncio.TimeoutError:
            _LOGGER.debug(f"{log} !! Timeout {timeout}")
            return 'timeout'
        except ClientOSError as e:
            _LOGGER.warning(f"{log} !! {e}")
            return 'E#COS'
        except:
            _LOGGER.exception(log)
            return 'E#???'
