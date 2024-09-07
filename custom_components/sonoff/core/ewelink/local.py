"""This registry can read data from LAN devices and send commands to them.
For non DIY devices data will be encrypted with devicekey. The registry cannot
decode such messages by itself because it does not manage the list of known
devices and their devicekey.
"""

import asyncio
import base64
import errno
import ipaddress
import json
import logging

import aiohttp
from Crypto.Cipher import AES
from Crypto.Hash import MD5
from Crypto.Random import get_random_bytes
from aiohttp.hdrs import CONTENT_TYPE
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
        # accept: eWeLink_1000xxxxxx.local.
        # skip: ihost-1001xxxxxx.local.
        if state_change == ServiceStateChange.Removed or not name.startswith("eWeLink"):
            return

        asyncio.create_task(self._handler2(zeroconf, service_type, name))

    async def _handler2(self, zeroconf: Zeroconf, service_type: str, name: str):
        """Step 2. Request additional info about add and update event from device."""
        deviceid = name[8:18]
        try:
            info = AsyncServiceInfo(service_type, name)
            if not await info.async_request(zeroconf, 3000) or not info.properties:
                _LOGGER.debug(f"{deviceid} <= Local0 | Can't get zeroconf info")
                return

            # support update with empty host and host without port
            for addr in info.addresses:
                # zeroconf lib should return IPv4, but better check anyway
                addr = ipaddress.IPv4Address(addr)
                host = f"{addr}:{info.port}" if info.port else str(addr)
                break
            else:
                if info.server and info.port:
                    host = f"{info.server}:{info.port}"
                else:
                    host = None

            data = {
                k.decode(): v.decode() if isinstance(v, bytes) else v
                for k, v in info.properties.items()
            }

            self._handler3(deviceid, host, data)

        except Exception as e:
            _LOGGER.debug(f"{deviceid} <= Local0 | Zeroconf error", exc_info=e)

    def _handler3(self, deviceid: str, host: str, data: dict):
        """Step 3. Process new data from device."""

        raw = "".join([data[f"data{i}"] for i in range(1, 5, 1) if f"data{i}" in data])

        msg = {
            "deviceid": deviceid,
            "subdevid": data["id"],
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
        command: str = None,
        sequence: str = None,
        timeout: int = 5,
        cre_retry_counter: int = 10,
    ):
        # known commands for DIY: switch, startup, pulse, sledonline
        # other commands: switch, switches, transmit, dimmable, light, fan

        if command is None:
            if params is None:
                return "noquery"
            command = next(iter(params))

        payload = {
            "sequence": sequence or await self.sequence(),
            "deviceid": device["deviceid"],
            "selfApikey": "123",
            "data": params or {},
        }

        if "devicekey" in device:
            payload = encrypt(payload, device["devicekey"])

        log = f"{device['deviceid']} => Local4 | {device.get('host', '')} | {params}"

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

            try:
                # some devices don't support getState command
                # https://github.com/AlexxIT/SonoffLAN/issues/1442
                if command == "getState" and r.headers.get(CONTENT_TYPE) == "text/html":
                    return "online"

                resp: dict = await r.json()
                if resp["error"] == 0:
                    _LOGGER.debug(f"{log} <= {resp}")

                    if "iv" in resp:
                        msg = {
                            "deviceid": device["deviceid"],
                            "localtype": device["localtype"],
                            "seq": resp["seq"],
                            "data": resp["data"],
                            "iv": resp["iv"],
                        }
                        if params and params.get("subDevId"):
                            msg["subdevid"] = params["subDevId"]
                        self.dispatcher_send(SIGNAL_UPDATE, msg)

                    return "online"

                else:
                    _LOGGER.debug(f"{log} <= {resp}")
                    return "error"

            except Exception as e:
                _LOGGER.debug(f"{log} !! Can't read JSON {e}")
                return "error"

        except asyncio.TimeoutError:
            _LOGGER.debug(f"{log} !! Timeout {timeout}")
            return "timeout"

        except aiohttp.ClientConnectorError as e:
            _LOGGER.debug(f"{log} !! Can't connect: {e}")
            return "E#CON"

        except aiohttp.ClientOSError as e:
            if e.errno != errno.ECONNRESET:
                _LOGGER.debug(log, exc_info=e)
                return "E#COE"  # ClientOSError

            # This happens because the device's web server is not multi-threaded
            # and can only process one request at a time. Therefore, if the
            # device is busy processing another request, it will close the
            # connection for the new request and we will get this error.
            #
            # It appears that the device takes some time to process a new request
            # after the previous one was closed, which caused a locking approach
            # to not work across different devices. Simply retrying on this error
            # a few times seems to fortunately work reliably, so we'll do that.

            _LOGGER.debug(f"{log} !! ConnectionResetError")
            if cre_retry_counter > 0:
                await asyncio.sleep(0.1)
                return await self.send(
                    device, params, command, sequence, timeout, cre_retry_counter - 1
                )

            return "E#CRE"  # ConnectionResetError

        except (
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
        # fix https://github.com/AlexxIT/SonoffLAN/issues/1160
        data = data.rstrip(b"\x02")
        return json.loads(data)
