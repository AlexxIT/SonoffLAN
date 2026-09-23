"""This registry can read data from LAN devices and send commands to them.
For non DIY devices data will be encrypted with devicekey. The registry cannot
decode such messages by itself because it does not manage the list of known
devices and their devicekey.
"""

import asyncio
import base64
from contextlib import suppress
import errno
import hashlib
import ipaddress
import json
import logging
import os
import re
import socket

import aiohttp
from aiohttp.hdrs import CONTENT_TYPE
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from zeroconf import DNSIncoming, DNSQuestionType, DNSText, ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo

from .base import SIGNAL_CONNECTED, SIGNAL_UPDATE, XDevice, XRegistryBase

_LOGGER = logging.getLogger(__name__)
SERVICE_TYPE = "_ewelink._tcp.local."
DEVICE_ID_RE = re.compile(r"^ewelink[-_]?([0-9a-z]{10})(?:[._-]|$)", re.I)


def mdns_service_candidates(deviceid: str, stored: str | None = None) -> list[str]:
    names: list[str] = []
    if stored:
        names.append(stored)
    for prefix in ("eWeLink_", "eWelink_", "ewelink-", "ewelink_"):
        name = f"{prefix}{deviceid}.{SERVICE_TYPE}"
        if name not in names:
            names.append(name)
    return names


def parse_deviceid_from_service_name(name: str) -> str | None:
    match = DEVICE_ID_RE.match(name)
    if not match:
        return None
    return match.group(1)


def decode_txt_record(raw: bytes) -> dict[str, str | None]:
    """Decode DNS-SD length-prefixed TXT properties."""
    properties: dict[str, str | None] = {}
    offset = 0
    while offset < len(raw):
        size = raw[offset]
        offset += 1
        end = offset + size
        if end > len(raw):
            return {}
        item = raw[offset:end]
        offset = end
        key, separator, value = item.partition(b"=")
        try:
            properties[key.decode()] = value.decode() if separator else None
        except UnicodeDecodeError:
            continue
    return properties


def encrypt(payload: dict, devicekey: str):
    plaintext = json.dumps(payload["data"], separators=(",", ":")).encode("utf-8")
    key = hashlib.md5(devicekey.encode("utf-8")).digest()
    iv = os.urandom(16)

    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(plaintext) + padder.finalize()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()

    payload["encrypt"] = True
    payload["data"] = base64.b64encode(ciphertext).decode("utf-8")
    payload["iv"] = base64.b64encode(iv).decode("utf-8")

    return payload


def decrypt(payload: dict, devicekey: str):
    ciphertext = base64.b64decode(payload["data"])
    key = hashlib.md5(devicekey.encode("utf-8")).digest()
    iv = base64.b64decode(payload["iv"])

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded_data = decryptor.update(ciphertext) + decryptor.finalize()

    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded_data) + unpadder.finalize()


class XRegistryLocal(XRegistryBase):
    browser: AsyncServiceBrowser = None
    online: bool = False
    zeroconf: Zeroconf | None = None

    def __init__(self, session: aiohttp.ClientSession):
        super().__init__(session)
        self._handler_tasks: set[asyncio.Task] = set()

    def start(self, zeroconf: Zeroconf):
        self.zeroconf = zeroconf
        self.browser = AsyncServiceBrowser(
            zeroconf, SERVICE_TYPE, [self._handler1]
        )
        self.online = True
        self.dispatcher_send(SIGNAL_CONNECTED)

    async def stop(self):
        self.online = False
        if self.browser:
            await self.browser.async_cancel()
            self.browser = None
        for task in list(self._handler_tasks):
            task.cancel()
        for task in list(self._handler_tasks):
            with suppress(asyncio.CancelledError):
                await task
        self._handler_tasks.clear()
        self.zeroconf = None

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
        deviceid = parse_deviceid_from_service_name(name)
        if not deviceid:
            return

        task = asyncio.create_task(
            self._handler2(zeroconf, service_type, name, deviceid)
        )
        self._handler_tasks.add(task)
        task.add_done_callback(self._handler_tasks.discard)

    async def _handler2(
        self, zeroconf: Zeroconf, service_type: str, name: str, deviceid: str
    ):
        """Step 2. Request additional info about add and update event from device."""
        try:
            info = AsyncServiceInfo(service_type, name)
            if not await info.async_request(zeroconf, 3000) or not info.properties:
                _LOGGER.debug(f"{deviceid} <= Local0 | Can't get zeroconf info")
                return

            # support update with empty host and host without port
            host = None
            for addr in info.addresses:
                try:
                    addr = ipaddress.IPv4Address(addr)
                except ipaddress.AddressValueError:
                    continue
                host = f"{addr}:{info.port}" if info.port else str(addr)
                break
            if not host and info.server and info.port:
                host = f"{info.server}:{info.port}"

            data = {
                k.decode(): v.decode() if isinstance(v, bytes) else v
                for k, v in info.properties.items()
            }

            self._handler3(deviceid, host, data, service_name=name)

        except Exception as e:
            _LOGGER.debug(f"{deviceid} <= Local0 | Zeroconf error", exc_info=e)

    async def pull_mdns(self, device: XDevice, timeout_ms: int = 1500) -> bool:
        """Actively query mDNS after sledonline ack-only HTTP responses."""
        if not self.zeroconf:
            return False
        return await self._pull_mdns_from(self.zeroconf, device, timeout_ms)

    async def pull_mdns_direct(self, device: XDevice, timeout_ms: int = 1500) -> bool:
        """Capture one fresh device publication without another Zeroconf instance."""
        if "sledOnline" not in device.get("params", {}) or not device.get("host"):
            return False

        device_host = device["host"].rsplit(":", 1)[0]
        listener = route = None
        try:
            route = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            route.connect((device_host, 5353))
            source_ip = route.getsockname()[0]
            route.close()
            route = None

            listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("", 5353))
            membership = socket.inet_aton("224.0.0.251") + socket.inet_aton(source_ip)
            listener.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
            listener.setblocking(False)

            result = await self.send(
                device,
                {"sledOnline": device["params"]["sledOnline"]},
                "sledonline",
                timeout=max(1, min(3, int(timeout_ms / 1000) or 1)),
            )
            if result not in ("ack", "online", "online_no_data"):
                return False
            if result == "online":
                return True

            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout_ms / 1000
            while remaining := deadline - loop.time():
                if remaining <= 0:
                    break
                try:
                    packet, address = await asyncio.wait_for(
                        loop.sock_recvfrom(listener, 9000), remaining
                    )
                except asyncio.TimeoutError:
                    break
                if address[0] != device_host:
                    continue

                incoming = DNSIncoming(packet)
                if not incoming.valid:
                    continue
                for record in incoming.answers():
                    if not isinstance(record, DNSText):
                        continue
                    if parse_deviceid_from_service_name(record.name) != device["deviceid"]:
                        continue
                    properties = decode_txt_record(record.text)
                    if not properties:
                        continue
                    self._handler3(
                        device["deviceid"],
                        device["host"],
                        properties,
                        service_name=record.name,
                    )
                    return True
        except (OSError, ValueError) as e:
            _LOGGER.debug(
                f"{device['deviceid']} <= Local0 | Direct mDNS capture", exc_info=e
            )
        finally:
            if route:
                route.close()
            if listener:
                listener.close()
        return False

    async def _pull_mdns_from(
        self, zeroconf: Zeroconf, device: XDevice, timeout_ms: int
    ) -> bool:
        deviceid = device["deviceid"]
        for name in mdns_service_candidates(deviceid, device.get("mdns_service")):
            try:
                cached = list(zeroconf.cache.async_entries_with_name(name))
                if cached:
                    zeroconf.cache.async_remove_records(cached)
                info = AsyncServiceInfo(SERVICE_TYPE, name)
                if (
                    not await info.async_request(
                        zeroconf,
                        timeout_ms,
                        question_type=DNSQuestionType.QU,
                    )
                    or not info.properties
                ):
                    continue

                host = None
                for addr in info.addresses:
                    try:
                        addr = ipaddress.IPv4Address(addr)
                    except ipaddress.AddressValueError:
                        continue
                    host = f"{addr}:{info.port}" if info.port else str(addr)
                    break
                if not host and info.server and info.port:
                    host = f"{info.server}:{info.port}"

                data = {
                    k.decode(): v.decode() if isinstance(v, bytes) else v
                    for k, v in info.properties.items()
                }
                device["mdns_service"] = name
                self._handler3(deviceid, host, data, service_name=name)
                return True
            except Exception as e:
                _LOGGER.debug(f"{deviceid} <= Local0 | pull_mdns {name}", exc_info=e)
        return False

    def _handler3(
        self, deviceid: str, host: str | None, data: dict, service_name: str | None = None
    ):
        """Step 3. Process new data from device."""

        raw = "".join([data[f"data{i}"] for i in range(1, 5, 1) if f"data{i}" in data])

        msg = {
            "deviceid": deviceid,
            "subdevid": data.get("id", deviceid),
            "localtype": data.get("type"),
            "seq": data.get("seq"),
        }

        if host:
            msg["host"] = host
        if service_name:
            msg["mdns_service"] = service_name

        encrypted = data.get("encrypt")
        if isinstance(encrypted, str):
            encrypted = encrypted.lower() == "true"

        if encrypted:
            if not raw:
                return
            msg["data"] = raw
            msg["iv"] = data["iv"]
        elif raw:
            msg["params"] = json.loads(raw)
        else:
            return

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

        # If the command is empty, we try to retrieve it from the parameters
        if command is None:
            # If the parameters are empty, use the dummy command
            # Even if the device doesn't support it, it will still respond in some way
            command = next(iter(params)) if params else "getState"

        payload = {
            "sequence": sequence or await self.sequence(),
            "deviceid": device["deviceid"],
            "selfApikey": "123",
            "data": params or {},
        }

        if "devicekey" in device:
            payload = encrypt(payload, device["devicekey"])

        host = device["host"]
        if ":" not in host:
            host += ":8081"  # default port, some devices may have another

        log = f"{device['deviceid']} => Local4 | {host} | {command} {params or {}}"

        try:
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
                if r.headers.get(CONTENT_TYPE) == "text/html":
                    _LOGGER.debug(f"{log} <= text/html")
                    if command == "getState":
                        return "online_no_data"
                    return "error"

                resp: dict = await r.json()
                _LOGGER.debug(f"{log} <= {resp}")
                if resp["error"] == 0:
                    # Encrypted response — decrypt happens in local_update
                    if "iv" in resp:
                        msg = {
                            "deviceid": device["deviceid"],
                            "localtype": device.get("localtype"),
                            "seq": resp["seq"],
                            "data": resp["data"],
                            "iv": resp["iv"],
                        }
                        if params and params.get("subDevId"):
                            msg["subdevid"] = params["subDevId"]
                        self.dispatcher_send(SIGNAL_UPDATE, msg)
                    # Plaintext response data (DIY / some energy replies)
                    elif isinstance(resp.get("data"), dict):
                        msg = {
                            "deviceid": device["deviceid"],
                            "localtype": device.get("localtype"),
                            "seq": resp.get("seq"),
                            "params": resp["data"],
                        }
                        if params and params.get("subDevId"):
                            msg["subdevid"] = params["subDevId"]
                        self.dispatcher_send(SIGNAL_UPDATE, msg)
                    elif command in ("switch", "switches", "pulse", "pulses") and params:
                        return "ack"
                    elif command in ("sledonline", "statistics", "uiActive"):
                        return "ack"

                    return "online"

                elif command == "getState":
                    return "online_no_data"

                else:
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

        except aiohttp.ServerDisconnectedError as e:
            _LOGGER.debug(log, exc_info=e)
            return "E#COS"

        except asyncio.CancelledError:
            raise

        except Exception as e:
            _LOGGER.error(log, exc_info=e)
            return "E#???"

    @staticmethod
    def decrypt_msg(msg: dict, devicekey: str = None) -> dict:
        # Fix Sonoff SPM-Main empty message {'seq': ***, 'data': '', 'iv': '***'}
        # Fix Sonoff ZbBridge-U without any message
        if not msg.get("data"):
            return {}

        data = decrypt(msg, devicekey)

        # Fix Sonoff RF Bridge sintax bug
        if data and data.startswith(b'{"rf'):
            data = data.replace(b'"="', b'":"')

        # Fix https://github.com/AlexxIT/SonoffLAN/issues/1160
        data = data.rstrip(b"\x02")

        return json.loads(data)
