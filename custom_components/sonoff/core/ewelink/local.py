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

import aiohttp
from Crypto.Cipher import AES
from Crypto.Hash import MD5
from Crypto.Random import get_random_bytes
from zeroconf import Zeroconf, ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo

from .base import SIGNAL_CONNECTED, SIGNAL_UPDATE, XDevice, XRegistryBase

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
    devicekey = devicekey.encode("utf-8")

    hash_ = MD5.new()
    hash_.update(devicekey)
    key = hash_.digest()

    iv = get_random_bytes(16)
    plaintext = json.dumps(payload["data"]).encode("utf-8")

    cipher = AES.new(key, AES.MODE_CBC, iv=iv)
    padded = pad(plaintext, AES.block_size)
    ciphertext = cipher.encrypt(padded)

    payload["encrypt"] = True
    payload["data"] = base64.b64encode(ciphertext).decode("utf-8")
    payload["iv"] = base64.b64encode(iv).decode("utf-8")

    return payload


def decrypt(payload: dict, devicekey: str):
    devicekey = devicekey.encode("utf-8")

    hash_ = MD5.new()
    hash_.update(devicekey)
    key = hash_.digest()

    cipher = AES.new(key, AES.MODE_CBC, iv=base64.b64decode(payload["iv"]))
    ciphertext = base64.b64decode(payload["data"])
    padded = cipher.decrypt(ciphertext)
    return unpad(padded, AES.block_size)


class XRegistryLocal(XRegistryBase):
    browser: AsyncServiceBrowser = None
    online: bool = False

    def start(self, zeroconf: Zeroconf):
        self.browser = AsyncServiceBrowser(
            zeroconf, "_ewelink._tcp.local.", [self._handler1]
        )
        self.online = True
        self.dispatcher_send(SIGNAL_CONNECTED)

    async def stop(self):
        if not self.online:
            return
        self.online = False
        await self.browser.async_cancel()

    def _handler1(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ):
        """Step 1. Receive change event from zeroconf."""
        if state_change == ServiceStateChange.Removed:
            return

        asyncio.create_task(self._handler2(zeroconf, service_type, name))

    async def _handler2(self, zeroconf: Zeroconf, service_type: str, name: str):
        """Step 2. Request additional info about add and update event from device."""
        try:
            info = AsyncServiceInfo(service_type, name)
            if not await info.async_request(zeroconf, 3000) or not info.properties:
                _LOGGER.debug(f"{name[8:18]} <= Local0 | Can't get zeroconf info")
                return

            # support update with empty host and host without port
            host = None
            for addr in info.addresses:
                # zeroconf lib should return IPv4, but better check anyway
                addr = ipaddress.IPv4Address(addr)
                host = f"{addr}:{info.port}" if info.port else str(addr)
                break

            if not host and info.server:
                host = info.server

            data = {
                k.decode(): v.decode() if isinstance(v, bytes) else v
                for k, v in info.properties.items()
            }

            self._handler3(host, data)

        except Exception as e:
            _LOGGER.debug(f"{name[8:18]} <= Local0 | Zeroconf error", exc_info=e)

    def _handler3(self, host: str, data: dict):
        """Step 3. Process new data from device."""

        raw = "".join([data[f"data{i}"] for i in range(1, 5, 1) if f"data{i}" in data])

        msg = {
            "deviceid": data["id"],
            "localtype": data["type"],
            "seq": data.get("seq"),
        }

        if host:
            msg["host"] = host

        if data.get("encrypt"):
            msg["data"] = raw
            msg["iv"] = data["iv"]
        else:
            msg["params"] = json.loads(raw)

        self.dispatcher_send(SIGNAL_UPDATE, msg)

    async def send(
        self,
        device: XDevice,
        params: dict = None,
        sequence: str = None,
        timeout: int = 5,
    ):
        # known commands for DIY: switch, startup, pulse, sledonline
        # other commands: switch, switches, transmit, dimmable, light, fan

        # cmd for D1 and RF Bridge 433
        if params:
            command = params.get("cmd") or next(iter(params))
        elif "sledOnline" in device["params"]:
            # device response with current status if we change any param
            command = "sledonline"
            params = {"sledOnline": device["params"]["sledOnline"]}
        else:
            return "noquery"

        if sequence is None:
            sequence = self.sequence()

        payload = {
            "sequence": sequence,
            "deviceid": device["deviceid"],
            "selfApikey": "123",
            "data": params,
        }

        if "devicekey" in device:
            payload = encrypt(payload, device["devicekey"])

        log = f"{device['deviceid']} => Local4 | {device.get('host','')} | {params}"

        try:
            host = device["host"]
            if ":" not in host:
                host += ":8081"  # default port, some devices may have another

            # noinspection HttpUrlsUsage
            r = await self.session.post(
                f"http://{host}/zeroconf/{command}",
                json=payload,
                headers={"Connection": "close"},
                timeout=timeout,
            )

            if command == "info":
                # better don't read response on info command
                # https://github.com/AlexxIT/SonoffLAN/issues/871
                _LOGGER.debug(f"{log} <= info: {r.status}")
                return "online"

            resp = await r.json()
            err = resp["error"]
            if err == 0:
                _LOGGER.debug(f"{log} <= {resp}")
                return "online"
            else:
                _LOGGER.warning(f"{log} <= {resp}")
                return f"E#{err}"

        except asyncio.TimeoutError:
            _LOGGER.debug(f"{log} !! Timeout {timeout}")
            return "timeout"

        except aiohttp.ClientConnectorError as e:
            _LOGGER.debug(f"{log} !! Can't connect: {e}")
            return "E#CON"

        except (
            aiohttp.ClientOSError,
            aiohttp.ServerDisconnectedError,
            asyncio.CancelledError,
        ) as e:
            _LOGGER.debug(log, exc_info=e)
            return "E#COS"

        except Exception as e:
            _LOGGER.error(log, exc_info=e)
            return "E#???"

    @staticmethod
    def decrypt_msg(msg: dict, devicekey: str = None) -> dict:
        data = decrypt(msg, devicekey)
        # Fix Sonoff RF Bridge sintax bug
        if data and data.startswith(b'{"rf'):
            data = data.replace(b'"="', b'":"')
        return json.loads(data)
