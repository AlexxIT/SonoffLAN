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
    task: asyncio.Task | None = None

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

        # Devices without parent will be first, so via_device option won't fail
        devices = sorted(devices, key=lambda d: d.get("params", {}).get("parentid", ""))

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
            self.task = None

    async def send(
        self,
        device: XDevice,
        params: dict = None,
        params_lan: dict = None,
        cmd_lan: str = None,
        query_cloud: bool = True,
        timeout_lan: int = 1,
    ) -> None:
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
                    main_device["localping"] = 0  # instant local ping request
                elif query_cloud and params:
                    # force update device actual status
                    await self.cloud.send(device, timeout=0)

        elif can_local:
            ok = await self.local.send(main_device, params_lan or params, cmd_lan, seq)
            if ok != "online":
                main_device["localping"] = 0  # instant local ping request

        elif can_cloud:
            ok = await self.cloud.send(device, params, seq)
            if ok == "online" and query_cloud and params:
                await self.cloud.send(device, timeout=0)

        else:
            return

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

    # TODO: Unify send_bulk and send_bulk_configure
    async def send_bulk_configure(self, device: XDevice, params: dict):
        assert "configure" in params

        if "params_bulk" in device:
            for new in params["configure"]:
                for old in device["params_bulk"]["configure"]:
                    # check on duplicates
                    if new["outlet"] == old["outlet"]:
                        old["startup"] = new["startup"]
                        break
                else:
                    device["params_bulk"]["configure"].append(new)
        else:
            device["params_bulk"] = params

        await asyncio.sleep(0.1)

        if params := device.pop("params_bulk", None):
            return await self.send(device, params)

    async def send_cloud(
        self, device: XDevice, params: dict = None, query=True
    ) -> str | None:
        if not self.can_cloud(device):
            return None
        ok = await self.cloud.send(device, params)
        if ok == "online" and query and params:
            await self.cloud.send(device, timeout=0)
        return ok

    def cloud_connected(self):
        for deviceid in self.devices.keys():
            self.dispatcher_send(deviceid)

        # if not self.task:
        #     self.task = asyncio.create_task(self.run_forever())

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
        device["cloud_seq"] = seq = msg.get("sequence")

        _LOGGER.debug(f"{did} <= Cloud3 | %s | {seq}", params)

        # process online change
        if "online" in params:
            device["online"] = params["online"]
            # check if LAN online after cloud status change
            device["localping"] = 0  # instant local ping request

        # Fix bug - cloud sends `{"subDevRssi": 127}` even for offline devices
        elif device["online"] is False and params.keys() != {"subDevRssi"}:
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
                _LOGGER.debug("Can't decrypt message %s", msg, exc_info=e)
                return

        elif "devicekey" in device:
            # unencripted device with devicekey in config, this means that the
            # DIY device is still connected to the ewelink account
            device.pop("devicekey")

        # realid can be different from mainid for SPM-4RELAY
        realid = msg.get("subdevid", mainid)
        tag = "Local3" if "host" in msg else "Local0"
        host = msg.get("host", "^^^")
        device["local_seq"] = seq = msg.get("seq")

        _LOGGER.debug(f"{realid} <= {tag} | {host} | %s | {seq}", params)

        if "params" in device:
            device["params"].update(params)
        else:
            device["params"] = params

        # we can get data from device, but without host
        if "host" in msg and device.get("host") != msg["host"]:
            # params for custom sensor
            device["host"] = params["host"] = msg["host"]
            device["localtype"] = msg["localtype"]

        ts = time.time()
        device["local"] = True
        device["localfail"] = 0
        device["localping"] = ts + 59  # one second less than a minute
        device["localrecv"] = ts

        self.dispatcher_send(realid, params)

        # send empty msg to main device for updating available flag
        if realid != mainid:
            self.dispatcher_send(mainid, None)

    async def run_forever(self):
        while True:
            ts = time.time()
            for device in self.devices.values():
                try:
                    if "local" in device:
                        self.update_local(device, ts)
                    elif parent := device.get("parent"):
                        # Support childrens only for SPM-Main (128)
                        if parent.get("localtype") == "meter":
                            self.update_local_child(parent, device)
                except Exception as e:
                    _LOGGER.warning("run_forever", exc_info=e)
            await asyncio.sleep(5)

    def update_local(self, device: XDevice, ts: float):
        # 1. Update sensors data for Power and TH devices if we haven't received them
        #    for more than 5 seconds.
        if (
            ts >= device["localrecv"] + 4  # one second less than 5 second
            and device["localfail"] < 3  # no more than 3 times
        ):
            uiid = device["extra"]["uiid"]
            # TH10R2 (15) and THR316D/THR320D (181) shouldn't be here, but anyway
            if uiid in (15, 32, 181, 182, 190, 262, 277):
                if led := device["params"].get("sledOnline"):
                    params = {"sledOnline": led}
                    asyncio.create_task(self.send_local(device, "sledonline", params))
                    return
            elif uiid == 126:
                asyncio.create_task(self.send_local(device, "statistics"))
                return

        # 2. Update local availability for all local devices (online and offline).
        if ts >= device["localping"]:
            asyncio.create_task(self.send_local(device))

    def update_local_child(self, parent: XDevice | dict, device: XDevice):
        # 3. Update sensors data for SPM-Main childrens.
        if parent["localfail"] >= 3:
            return
        outlet = device.get("active_outlet", 0)
        device["active_outlet"] = outlet + 1 if outlet < 3 else 0
        params = {
            "subDevId": device["deviceid"],
            "uiActive": {"outlet": outlet, "time": 60},
        }
        asyncio.create_task(self.send_local(parent, "uiActive", params))

    def can_cloud(self, device: XDevice) -> bool:
        if not self.cloud.online:
            return False
        return device.get("online")

    def can_local(self, device: XDevice) -> bool:
        if not self.local.online:
            return False
        if parent := device.get("parent"):
            # Known local parents - SPM-Main, RFBridge and ZBBridge-P
            # But ZBBridge-P can't control local devices
            if parent.get("localtype") in ("meter", "rf"):
                return parent.get("local")
        return device.get("local")

    async def send_local(
        self, device: XDevice, command: str = None, params: dict = None
    ):
        ok = await self.local.send(device, params, command)
        if ok == "online":
            if not device["local"]:
                device["local"] = True
                did = device["deviceid"]
                _LOGGER.debug(f"{did} !! Local4 | Device online")
                self.dispatcher_send(did)

            device["localfail"] = 0
            device["localping"] = time.time() + 59
            return

        device["localfail"] += 1

        # requests with command (sledonline or statistics) can't fail device to offline
        if command or device["localfail"] < 3:
            return

        if device["local"]:
            device["local"] = False
            did = device["deviceid"]
            _LOGGER.debug(f"{did} !! Local4 | Device offline")
            self.dispatcher_send(did)

        device["localping"] = time.time() + 59
