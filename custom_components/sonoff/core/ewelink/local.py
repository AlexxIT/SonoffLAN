"""This registry can read data from LAN devices and send commands to them.
For non DIY devices data will be encrypted with devicekey. The registry cannot
decode such messages by itself because it does not manage the list of known
devices and their devicekey.
"""
import asyncio
import base64
import ipaddress
import json
import logging
import time

import aiohttp
from Crypto.Cipher import AES
from Crypto.Hash import MD5
from Crypto.Random import get_random_bytes
from zeroconf import Zeroconf, ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo

from .base import XRegistryBase, XDevice, SIGNAL_CONNECTED, SIGNAL_UPDATE

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
    payload['data'] = base64.b64encode(ciphertext).decode('utf-8')
    payload['iv'] = base64.b64encode(iv).decode('utf-8')

    return payload


def decrypt(payload: dict, devicekey: str):
    devicekey = devicekey.encode('utf-8')

    hash_ = MD5.new()
    hash_.update(devicekey)
    key = hash_.digest()

    cipher = AES.new(key, AES.MODE_CBC, iv=base64.b64decode(payload['iv']))
    ciphertext = base64.b64decode(payload['data'])
    padded = cipher.decrypt(ciphertext)
    return unpad(padded, AES.block_size)


class XRegistryLocal(XRegistryBase):
    browser: AsyncServiceBrowser = None
    online: bool = False

    def start(self, zeroconf: Zeroconf):
        self.browser = AsyncServiceBrowser(
            zeroconf, '_ewelink._tcp.local.', handlers=[self._zeroconf_handler]
        )
        self.browser.name = 'Sonoff_LAN'  # for beautiful logs

        self.online = True
        self.dispatcher_send(SIGNAL_CONNECTED)

    async def stop(self):
        if not self.online:
            return
        self.online = False
        await self.browser.async_cancel()

    def _zeroconf_handler(
            self, zeroconf: Zeroconf, service_type: str, name: str,
            state_change: ServiceStateChange
    ):
        if state_change == ServiceStateChange.Removed:
            # TTL of record 5 minutes
            deviceid = name[8:18]
            _LOGGER.debug(f"{deviceid} <= Local2 | Zeroconf Removed Event")
            msg = {"deviceid": deviceid, "params": {"online": None}}
            self.dispatcher_send(SIGNAL_UPDATE, msg)
            return

        coro = self._process_zeroconf_change(
            zeroconf, service_type, name, state_change
        )
        asyncio.create_task(coro)

    async def _process_zeroconf_change(
            self, zeroconf: Zeroconf, service_type: str, name: str,
            state_change: ServiceStateChange
    ):
        info = AsyncServiceInfo(service_type, name)
        await info.async_request(zeroconf, 3000)

        if len(info.addresses) == 0:
            return

        data = {
            k.decode(): v.decode() if isinstance(v, bytes) else v
            for k, v in info.properties.items()
        }

        raw = ''.join([
            data[f'data{i}'] for i in range(1, 5, 1) if f'data{i}' in data
        ])

        msg = {
            "host": str(ipaddress.ip_address(info.addresses[0])),
            "deviceid": data["id"],
            "diy": data["type"],
            "seq": data.get("seq"),
        }

        if data.get("encrypt"):
            msg["data"] = raw
            msg["iv"] = data["iv"]
        else:
            msg["params"] = json.loads(raw)

        self.dispatcher_send(SIGNAL_UPDATE, msg)

    async def check_offline(self, device: XDevice):
        """Try to get response from device after received Zeroconf Removed."""
        deviceid = device["deviceid"]
        log = f"{deviceid} => Local4"
        if device.get('check_offline') or device['host'] is None:
            _LOGGER.debug(f"{log} | Skip parallel checks")
            return

        device['check_offline'] = True
        sequence = self.sequence()

        for t in range(20, 61, 20):
            _LOGGER.debug(f"{log} | Check offline with timeout {t}s")

            t0 = time.time()

            conn = await self.send(device, None, sequence, t)
            if conn == 'online':
                device.pop("check_offline")
                _LOGGER.debug(f"{log} | Welcome back!")
                return

            if t < 60 and conn != 'timeout':
                # sometimes need to wait more
                await asyncio.sleep(t - time.time() + t0)

        _LOGGER.debug(f"{log} | Device offline")

        device.pop('check_offline')
        device.pop("host")

        self.dispatcher_send(SIGNAL_UPDATE, {"online": False})

    async def send(
            self, device: XDevice, params: dict = None, sequence: str = None,
            timeout: int = 5
    ):
        # known commands for DIY: switch, startup, pulse, sledonline
        # other commands: switch, switches, transmit, dimmable, light, fan

        # cmd for D1 and RF Bridge 433
        if params:
            command = params.get("cmd") or next(iter(params))
        else:
            # if we change dummy param - device will send full new status
            # TODO: use different command for different devices
            command = "sledonline"
            params = {"sledonline": "on"}

        if sequence is None:
            sequence = self.sequence()

        payload = {
            "sequence": sequence,
            "deviceid": device["deviceid"],
            "selfApikey": "123",
            "data": params
        }

        if 'devicekey' in device:
            payload = encrypt(payload, device['devicekey'])

        log = f"{device['deviceid']} => Local4 | {params}"

        try:
            # noinspection HttpUrlsUsage
            r = await self.session.post(
                f"http://{device['host']}:8081/zeroconf/{command}",
                json=payload, headers={'Connection': 'close'}, timeout=timeout
            )
            resp = await r.json()
            err = resp['error']
            # no problem with any response from device for sledonline command
            if err == 0 or command == 'sledonline':
                _LOGGER.debug(f"{log} <= {resp}")
                return 'online'
            else:
                _LOGGER.warning(f"{log} <= {resp}")
                return f"E#{err}"

        except asyncio.TimeoutError:
            _LOGGER.debug(f"{log} !! Timeout {timeout}")
            return 'timeout'

        except (aiohttp.ClientOSError, aiohttp.ServerDisconnectedError,
                asyncio.CancelledError) as e:
            _LOGGER.debug(log, exc_info=e)
            return 'E#COS'

        except Exception as e:
            _LOGGER.error(log, exc_info=e)
            return 'E#???'

    @staticmethod
    def decrypt_msg(msg: dict, devicekey: str = None) -> dict:
        data = decrypt(msg, devicekey)
        # Fix Sonoff RF Bridge sintax bug
        if data and data.startswith(b'{"rf'):
            data = data.replace(b'"="', b'":"')
        return json.loads(data)
