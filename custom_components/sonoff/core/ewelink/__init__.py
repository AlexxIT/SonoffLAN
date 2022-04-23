import asyncio
import json
import logging
import time
from typing import Dict, List

from aiohttp import ClientSession

from .base import XRegistryBase, SIGNAL_UPDATE, SIGNAL_CONNECTED
from .cloud import XRegistryCloud
from .local import XRegistryLocal, decrypt

_LOGGER = logging.getLogger(__name__)

SIGNAL_ADD_ENTITIES = "add_entities"


class XRegistry(XRegistryBase):
    config: dict = None
    task: asyncio.Task = None

    def __init__(self, session: ClientSession):
        super().__init__(session)

        self.devices: Dict[str, dict] = {}

        self.cloud = XRegistryCloud(session)
        self.cloud.dispatcher_connect(SIGNAL_CONNECTED, self.cloud_connected)
        self.cloud.dispatcher_connect(SIGNAL_UPDATE, self.cloud_update)

        self.local = XRegistryLocal(session)
        self.local.dispatcher_connect(SIGNAL_UPDATE, self.local_update)

    def setup_devices(self, devices: List[dict]):
        from ..devices import get_spec

        for device in devices:
            deviceid = device["deviceid"]
            try:
                device.update(self.config["devices"][deviceid])
            except Exception:
                pass

            dump = {
                k: v for k, v in device['params'].items()
                if k not in ('bindInfos', 'bssid', 'ssid', 'staMac')
            }
            uiid = device['extra']['uiid']
            _LOGGER.debug(f"{deviceid} UIID {uiid:04} | {dump}")

            spec = get_spec(device)
            entities = [cls(self, device) for cls in spec]
            self.dispatcher_send(SIGNAL_ADD_ENTITIES, entities)

            self.devices[deviceid] = device

    async def stop(self):
        self.devices.clear()
        self.dispatcher.clear()

        await self.cloud.stop()
        await self.local.stop()

        if self.task:
            self.task.cancel()

    async def send(self, device: dict, params: dict):
        seq = str(int(time.time() * 1000))

        can_local = self.local.online and device.get('host')
        can_cloud = self.cloud.online and device.get('online')

        state = {}

        if can_local and can_cloud:
            # try to send a command locally (wait no more than a second)
            state['local'] = await self.local.send(device, params, seq, 1)

            # otherwise send a command through the cloud
            if state['local'] != 'online':
                state['cloud'] = await self.cloud.send(device, params, seq)
                if state['cloud'] != 'online':
                    coro = self.local.check_offline(device)
                    asyncio.create_task(coro)

        elif can_local:
            state['local'] = await self.local.send(device, params, seq, 5)
            if state['local'] != 'online':
                coro = self.local.check_offline(device)
                asyncio.create_task(coro)

        elif can_cloud:
            state['cloud'] = await self.cloud.send(device, params, seq)

        else:
            return

        # TODO: response state
        # self.dispatcher_send(device["deviceid"], state)

    def cloud_connected(self):
        for deviceid in self.devices.keys():
            self.dispatcher_send(deviceid)

        if not self.task or self.task.done():
            self.task = asyncio.create_task(self.pow_helper())

    def cloud_update(self, msg: dict):
        did = msg["deviceid"]
        device = self.devices.get(did)
        if not device:
            _LOGGER.warning(f"UNKNOWN cloud device: {msg}")
            return

        params = msg["params"]

        _LOGGER.debug(f"{did} <= Cloud3 | {params} | {msg.get('sequence')}")

        # process online change
        if "online" in params:
            # skip same online
            if device["online"] == params["online"]:
                return
            device["online"] = params["online"]

        # any message from device - set device online to True
        elif device["online"] is False:
            device["online"] = True

        self.dispatcher_send(did, params)

    def local_update(self, msg: dict):
        did = msg["deviceid"]
        device = self.devices.get(did)
        if not device:
            if "params" not in msg:
                try:
                    # allow setup if can decrypt device message
                    devicekey = self.config["devices"][did]["devicekey"]
                    data = decrypt(msg, devicekey)
                    msg["params"] = json.loads(data)
                except Exception:
                    _LOGGER.debug(f"{did} !! skip setup for encrypted device")
                    self.devices[did] = msg
                    return

            from ..devices import setup_diy
            device = setup_diy(msg)
            self.setup_devices([device])

        params: dict = msg.get("params")
        if not params:
            devicekey = device.get("devicekey")
            if not devicekey:
                # encrypted device without devicekey
                return
            try:
                data = decrypt(msg, devicekey)
                # Fix Sonoff RF Bridge sintax bug
                if data and data.startswith(b'{"rf'):
                    data = data.replace(b'"="', b'":"')
                params = json.loads(data)
            except Exception as e:
                _LOGGER.debug("Can't decrypt message", exc_info=e)
                return

        if "online" in params:
            if params["online"] is None:
                coro = self.local.check_offline(device)
                asyncio.create_task(coro)
            elif params["online"] is False:
                self.dispatcher_send(msg["deviceid"])
            return

        _LOGGER.debug(f"{did} <= Local3 | {params} | {msg.get('seq')}")

        if "deviceType" in params:
            # Sonoff TH v3.4.0 sends `temperature` and `humidity` via LAN
            # zero temp or hum is probably bug
            # https://github.com/AlexxIT/SonoffLAN/issues/110
            # Sonoff TH v3.5.0 sends `currentXXX` (like a cloud)
            # https://github.com/AlexxIT/SonoffLAN/issues/527
            if params.get("temperature", 0) != 0:
                params["currentTemperature"] = params["temperature"]
            if params.get("humidity", 0) != 0:
                params["currentHumidity"] = params["humidity"]

        device["host"] = msg["host"]

        self.dispatcher_send(did, params)

    async def pow_helper(self):
        from ..devices import POW_UI_ACTIVE
        while True:
            if not self.cloud.online:
                await asyncio.sleep(60)
                continue

            for device in self.devices.values():
                if "extra" not in device:
                    continue

                params = POW_UI_ACTIVE.get(device["extra"]["uiid"])
                if not params:
                    continue

                await self.cloud.send(device, params, timeout=0)

            # sleep for 1 minute
            await asyncio.sleep(3600)
