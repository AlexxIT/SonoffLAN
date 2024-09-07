import asyncio
import logging
import time

from aiohttp import ClientSession

from .base import SIGNAL_CONNECTED, SIGNAL_UPDATE, XDevice, XRegistryBase
from .cloud import XRegistryCloud
from .local import XRegistryLocal

_LOGGER = logging.getLogger(__name__)

SIGNAL_ADD_ENTITIES = "add_entities"
LOCAL_TTL = 60


class XRegistry(XRegistryBase):
    config: dict = None
    task: asyncio.Task = None

    def __init__(self, session: ClientSession):
        super().__init__(session)

        self.devices: dict[str, XDevice] = {}

        self.cloud = XRegistryCloud(session)
        self.cloud.dispatcher_connect(SIGNAL_CONNECTED, self.cloud_connected)
        self.cloud.dispatcher_connect(SIGNAL_UPDATE, self.cloud_update)

        self.local = XRegistryLocal(session)
        self.local.dispatcher_connect(SIGNAL_CONNECTED, self.local_connected)
        self.local.dispatcher_connect(SIGNAL_UPDATE, self.local_update)

    def setup_devices(self, devices: list[XDevice]) -> list:
        from ..devices import get_spec

        entities = []

        for device in devices:
            did = device["deviceid"]
            try:
                device.update(self.config["devices"][did])
            except Exception:
                pass

            try:
                uiid = device["extra"]["uiid"]
                _LOGGER.debug(f"{did} UIID {uiid:04} | %s", device["params"])

                if parentid := device["params"].get("parentid"):
                    try:
                        device["parent"] = next(
                            d for d in devices if d["deviceid"] == parentid
                        )
                    except StopIteration:
                        pass

                # at this moment entities can catch signals with device_id and
                # update their states, but they can be added to hass later
                entities += [cls(self, device) for cls in get_spec(device)]

                self.devices[did] = device

            except Exception as e:
                _LOGGER.warning(f"{did} !! can't setup device", exc_info=e)

        return entities

    @property
    def online(self) -> bool:
        return self.cloud.online is not None or self.local.online

    async def stop(self, *args):
        self.devices.clear()
        self.dispatcher.clear()

        await self.cloud.stop()
        await self.local.stop()

        if self.task:
            self.task.cancel()

    async def send(
        self,
        device: XDevice,
        params: dict = None,
        params_lan: dict = None,
        cmd_lan: str = None,
        query_cloud: bool = True,
        timeout_lan: int = 1,
    ):
        """Send command to device with LAN and Cloud. Usual params are same.

        LAN will send new device state after update command, Cloud - don't.

        :param device: device object
        :param params: non empty to update state, empty to query state
        :param params_lan: optional if LAN params different (ex iFan03)
        :param cmd_lan: optional if LAN command different
        :param query_cloud: optional query Cloud state after update state,
          ignored if params empty
        :param timeout_lan: optional custom LAN timeout
        """
        seq = await self.sequence()

        if "parent" in device:
            main_device = device["parent"]
            if params_lan is None and params is not None:
                params_lan = params.copy()
            if params_lan:
                params_lan["subDevId"] = device["deviceid"]
        else:
            main_device = device

        can_local = self.can_local(device)
        can_cloud = self.can_cloud(device)

        if can_local and can_cloud:
            # try to send a command locally (wait no more than a second)
            ok = await self.local.send(
                main_device, params_lan or params, cmd_lan, seq, timeout_lan
            )

            # otherwise send a command through the cloud
            if ok != "online":
                ok = await self.cloud.send(device, params, seq)
                if ok != "online":
                    asyncio.create_task(self.check_offline(main_device))
                elif query_cloud and params:
                    # force update device actual status
                    await self.cloud.send(device, timeout=0)

        elif can_local:
            ok = await self.local.send(main_device, params_lan or params, cmd_lan, seq)
            if ok != "online":
                asyncio.create_task(self.check_offline(main_device))

        elif can_cloud:
            ok = await self.cloud.send(device, params, seq)
            if ok == "online" and query_cloud and params:
                await self.cloud.send(device, timeout=0)

        else:
            return

        # TODO: response state
        # self.dispatcher_send(device["deviceid"], state)

    async def send_bulk(self, device: XDevice, params: dict):
        assert "switches" in params

        if "params_bulk" in device:
            for new in params["switches"]:
                for old in device["params_bulk"]["switches"]:
                    # check on duplicates
                    if new["outlet"] == old["outlet"]:
                        old["switch"] = new["switch"]
                        break
                else:
                    device["params_bulk"]["switches"].append(new)
        else:
            device["params_bulk"] = params

        await asyncio.sleep(0.1)

        # this can be called from different threads/loops
        # https://github.com/AlexxIT/SonoffLAN/issues/1368
        if params := device.pop("params_bulk", None):
            return await self.send(device, params)

    async def send_cloud(self, device: XDevice, params: dict = None, query=True):
        if not self.can_cloud(device):
            return
        ok = await self.cloud.send(device, params)
        if ok == "online" and query and params:
            await self.cloud.send(device, timeout=0)

    async def check_offline(self, device: XDevice):
        if not device.get("host"):
            return

        for i in range(3):
            if i > 0:
                await asyncio.sleep(5)

            ok = await self.local.send(device, command="getState")
            if ok in ("online", "error"):
                device["local_ts"] = time.time() + LOCAL_TTL
                device["local"] = True
                return

            # just one try for the long lost
            if time.time() > device.get("local_ts", 0) + LOCAL_TTL:
                break

        device["local"] = False

        did = device["deviceid"]
        _LOGGER.debug(f"{did} !! Local4 | Device offline")
        self.dispatcher_send(did)

    def cloud_connected(self):
        for deviceid in self.devices.keys():
            self.dispatcher_send(deviceid)

        if not self.task:
            self.task = asyncio.create_task(self.run_forever())

    def local_connected(self):
        if not self.task:
            self.task = asyncio.create_task(self.run_forever())

    def cloud_update(self, msg: dict):
        did = msg["deviceid"]
        device = self.devices.get(did)
        # the device may be from another Home - skip it
        if not device or "online" not in device:
            return

        params = msg["params"]

        _LOGGER.debug(f"{did} <= Cloud3 | %s | {msg.get('sequence')}", params)

        # process online change
        if "online" in params:
            device["online"] = params["online"]
            # check if LAN online after cloud status change
            asyncio.create_task(self.check_offline(device))

        elif device["online"] is False:
            device["online"] = True

        if "sledOnline" in params:
            device["params"]["sledOnline"] = params["sledOnline"]

        self.dispatcher_send(did, params)

    def local_update(self, msg: dict):
        mainid: str = msg["deviceid"]
        device: XDevice = self.devices.get(mainid)
        params: dict = msg.get("params")
        # check device in known devices list
        if not device:
            # check payload already decrypted (DIY devices)
            if not params:
                try:
                    # try to decrypt payload if we have right key in config
                    msg["params"] = params = self.local.decrypt_msg(
                        msg, self.config["devices"][mainid]["devicekey"]
                    )
                except Exception:
                    _LOGGER.debug(f"{mainid} !! skip setup for encrypted device")
                    # save device to known list, so no more decrypt tries
                    self.devices[mainid] = msg
                    return

            from ..devices import setup_diy

            # setup new device as DIY device
            device = setup_diy(msg)
            entities = self.setup_devices([device])
            self.dispatcher_send(SIGNAL_ADD_ENTITIES, entities)

        elif not params:
            if "devicekey" not in device:
                # this is known device with encrypted payload but without devicekey
                return
            try:
                # decrypt payload for known device with devicekey
                params = self.local.decrypt_msg(msg, device["devicekey"])
            except Exception as e:
                _LOGGER.debug("Can't decrypt message", exc_info=e)
                return

        elif "devicekey" in device:
            # unencripted device with devicekey in config, this means that the
            # DIY device is still connected to the ewelink account
            device.pop("devicekey")

        # realid can be different from mainid for SPM-4RELAY
        realid = msg.get("subdevid", mainid)
        tag = "Local3" if "host" in msg else "Local0"

        _LOGGER.debug(
            f"{realid} <= {tag} | {msg.get('host', '')} | %s | {msg.get('seq', '')}",
            params,
        )

        if "sledOnline" in params:
            device["params"]["sledOnline"] = params["sledOnline"]

        # we can get data from device, but without host
        if "host" in msg and device.get("host") != msg["host"]:
            # params for custom sensor
            device["host"] = params["host"] = msg["host"]
            device["localtype"] = msg["localtype"]

        device["local_ts"] = time.time() + LOCAL_TTL
        device["local"] = True

        self.dispatcher_send(realid, params)

        # send empty msg to main device for updating available flag
        if realid != mainid:
            self.dispatcher_send(mainid, None)

    async def run_forever(self):
        """This daemon function doing two things:

        1. Force update POW devices. Some models support only cloud update, some support
           local queries
        2. Ping LAN devices if they are silent for more than 1 minute
        """
        while True:
            for device in self.devices.values():
                try:
                    self.update_device(device)
                except Exception as e:
                    _LOGGER.warning("run_forever", exc_info=e)

            await asyncio.sleep(30)

    def update_device(self, device: XDevice):
        if "extra" not in device:
            return

        uiid = device["extra"]["uiid"]

        # [5] POW, [32] POWR2, [182] S40, [190] POWR3 - one channel, only cloud update
        # [181] THR316D/THR320D, [226] CK-BL602-W102SW18-01
        if uiid in (5, 32, 182, 190, 181, 226):
            if self.can_cloud(device):
                params = {"uiActive": 60}
                asyncio.create_task(self.cloud.send(device, params, timeout=0))

        # DUALR3 - two channels, local and cloud update
        elif uiid == 126:
            if self.can_local(device):
                # empty params is OK
                asyncio.create_task(self.local.send(device, command="statistics"))
            elif self.can_cloud(device):
                params = {"uiActive": {"all": 1, "time": 60}}
                asyncio.create_task(self.cloud.send(device, params, timeout=0))

        # SPM-4Relay - four channels, separate update for each channel
        elif uiid == 130:
            # https://github.com/AlexxIT/SonoffLAN/issues/1366
            if self.can_cloud(device):
                asyncio.create_task(self.update_spm_pow(device))

        # checks if device still available via LAN
        if "local_ts" not in device or device["local_ts"] > time.time():
            return

        if self.local.online:
            asyncio.create_task(self.check_offline(device))

    async def update_spm_pow(self, device: XDevice):
        for i in range(4):
            if i > 0:
                await asyncio.sleep(5)
            params = {"uiActive": {"outlet": i, "time": 60}}
            await self.cloud.send(device, params, timeout=0)

    def can_cloud(self, device: XDevice) -> bool:
        if not self.cloud.online:
            return False
        return device.get("online")

    def can_local(self, device: XDevice) -> bool:
        if not self.local.online:
            return False
        if "parent" in device:
            return device["parent"].get("local")
        return device.get("local")
