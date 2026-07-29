import asyncio
from collections import deque
import logging
import time

from aiohttp import ClientSession

from .base import (
    SIGNAL_CLOUD_ERROR,
    SIGNAL_CONNECTED,
    SIGNAL_UPDATE,
    XDevice,
    XRegistryBase,
)
from .cloud import XRegistryCloud
from .local import XRegistryLocal

_LOGGER = logging.getLogger(__name__)

SIGNAL_ADD_ENTITIES = "add_entities"
COMMAND_ERRORS_MAXLEN = 100
RECONCILE_DELAY = 2
LOCAL_TTL = 60


class XRegistry(XRegistryBase):
    config: dict = None
    task: asyncio.Task | None = None

    def __init__(self, session: ClientSession):
        super().__init__(session)

        self.devices: dict[str, XDevice] = {}
        self.cloud_locks: dict[str, asyncio.Lock] = {}
        self.cloud_pending: dict[str, dict] = {}
        self.cloud_error_tasks: dict[str, asyncio.Task] = {}
        self.cloud_errors: deque[dict] = deque(maxlen=COMMAND_ERRORS_MAXLEN)
        # Opt-in: a retry is safe only for explicit switch on/off commands.
        self.cloud_retry = False

        self.cloud = XRegistryCloud(session)
        # Let cloud protocol logs resolve a device ID to its local friendly name.
        self.cloud.devices = self.devices
        self.cloud.dispatcher_connect(SIGNAL_CONNECTED, self.cloud_connected)
        self.cloud.dispatcher_connect(SIGNAL_CLOUD_ERROR, self.cloud_error)
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

        for task in self.cloud_error_tasks.values():
            task.cancel()
        self.cloud_error_tasks.clear()
        self.cloud_pending.clear()
        self.cloud_locks.clear()

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
                ok = await self.send_cloud(device, params, query_cloud, seq)
                if ok != "online":
                    main_device["localping"] = 0  # instant local ping request

        elif can_local:
            ok = await self.local.send(main_device, params_lan or params, cmd_lan, seq)
            if ok != "online":
                main_device["localping"] = 0  # instant local ping request

        elif can_cloud:
            await self.send_cloud(device, params, query_cloud, seq)

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
        self,
        device: XDevice,
        params: dict = None,
        query: bool = True,
        sequence: str = None,
        timeout: float = 5,
        force: bool = False,
        origin: str = "command",
    ) -> str | None:
        """Send one cloud command, serialised per device and safely recorded.

        The bridge framework 3.3.0 cannot control Zigbee children via LAN. This
        method deliberately uses the cloud transport only and never retries a
        failed actuator command unless the user explicitly opts in.
        """
        if not force and not self.can_cloud(device):
            return None

        did = device["deviceid"]
        if sequence is None:
            sequence = await self.sequence()

        command = {
            "action": "update" if params else "query",
            "params": params.copy() if params else None,
            "param_keys": sorted(params) if params else [],
            "safe_retry": self.is_safe_retry(params),
            "sequence": sequence,
            "timestamp": time.time(),
            "started_monotonic": time.monotonic(),
            "origin": origin,
            **self.cloud_context(device),
        }

        lock = self.cloud_locks.setdefault(did, asyncio.Lock())
        async with lock:
            # Re-check while holding the per-device lock. A previous command may
            # have completed while this one was waiting, making a second on/off
            # request redundant and a potential source of cloud 411 responses.
            if self.is_redundant_switch_command(device, params):
                _LOGGER.debug("Skip redundant cloud command for %s", did)
                return "online"

            # Keep parameter values in memory only while the command is in flight.
            self.cloud_pending[sequence] = command
            device["last_cloud_command"] = {
                k: v
                for k, v in command.items()
                if k not in ("params", "safe_retry", "started_monotonic")
            }
            try:
                ok = await self.cloud.send(device, params, sequence, timeout)
            finally:
                self.cloud_pending.pop(sequence, None)

            if ok == "online" and query and params:
                # Queue the state query before the next command for this device.
                # This keeps the command order deterministic without replaying an
                # actuator command and improves the redundant-command check above.
                query_sequence = await self.sequence()
                self.cloud_pending[query_sequence] = {
                    "action": "query",
                    "param_keys": [],
                    "sequence": query_sequence,
                    "started_monotonic": time.monotonic(),
                    "origin": "post-update-query",
                    **self.cloud_context(device),
                }
                try:
                    await self.cloud.send(device, sequence=query_sequence, timeout=0)
                finally:
                    self.cloud_pending.pop(query_sequence, None)

        command["latency_ms"] = round(
            (time.monotonic() - command["started_monotonic"]) * 1000
        )
        device["last_cloud_command"]["latency_ms"] = command["latency_ms"]

        if ok == "online":
            device["last_cloud_success"] = time.time()

        return ok

    @staticmethod
    def cloud_context(device: XDevice) -> dict:
        """Return useful transport context without command values or credentials."""
        context = {"transport": "cloud"}
        if rssi := device.get("params", {}).get("subDevRssi"):
            context["device_rssi"] = rssi

        if not (parent := device.get("parent")):
            return context

        context["parentid"] = parent.get("deviceid")
        context["parent_model"] = parent.get("productModel")
        if rssi := parent.get("params", {}).get("rssi"):
            context["bridge_rssi"] = rssi
        if version := parent.get("params", {}).get("hostVersion"):
            context["bridge_framework"] = version
        if parent.get("productModel") == "ZBBridge-P":
            context["transport_reason"] = "zbbridge_child_lan_unsupported"
        return context

    @staticmethod
    def is_safe_retry(params: dict | None) -> bool:
        """Only explicit on/off is safe to repeat after an ambiguous timeout."""
        return params is not None and params.get("switch") in ("on", "off") and len(
            params
        ) == 1

    @staticmethod
    def is_redundant_switch_command(device: XDevice, params: dict | None) -> bool:
        """Return true only for a known, already satisfied switch state."""
        return XRegistry.is_safe_retry(params) and (
            device.get("params", {}).get("switch") == params["switch"]
        )

    @staticmethod
    def is_command_confirmed(device: XDevice, command: dict, sequence: str) -> bool:
        """Confirm that the reconciliation response reports the requested state."""
        params = command.get("params") or {}
        return device.get("cloud_seq") == sequence and all(
            device.get("params", {}).get(key) == value for key, value in params.items()
        )

    def cloud_error(self, event: dict) -> None:
        """Record a redacted cloud error and schedule one status reconciliation."""
        did = event.get("deviceid")
        device = self.devices.get(did)
        command = self.cloud_pending.get(event.get("sequence"), {})

        record = {
            "code": event.get("error"),
            "deviceid": did,
            "sequence": event.get("sequence"),
            "action": command.get("action", event.get("action")),
            "param_keys": command.get("param_keys", []),
            "timestamp": time.time(),
        }
        for key in (
            "origin",
            "transport",
            "transport_reason",
            "device_rssi",
            "bridge_rssi",
            "bridge_framework",
        ):
            if command.get(key) is not None:
                record[key] = command[key]
        if started := command.get("started_monotonic"):
            record["latency_ms"] = round((time.monotonic() - started) * 1000)
        if device and (parent := device.get("parent")):
            record["parentid"] = parent.get("deviceid")
            record["parent_model"] = parent.get("productModel")

        self.cloud_errors.append(record)
        if not device:
            return

        device["last_cloud_error"] = record
        code = record["code"]
        if code not in (411, 504) or did in self.cloud_error_tasks:
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Allows synchronous unit tests and does not affect Home Assistant.
            return

        self.cloud_error_tasks[did] = loop.create_task(
            self.reconcile_cloud_error(device, record, command)
        )

    async def reconcile_cloud_error(
        self, device: XDevice, record: dict, command: dict
    ) -> None:
        """Verify state after an eWeLink 411/504 without replaying the command."""
        did = device["deviceid"]
        try:
            await asyncio.sleep(RECONCILE_DELAY)
            sequence = await self.sequence()
            result = await self.send_cloud(
                device,
                query=False,
                sequence=sequence,
                timeout=5,
                force=True,
                origin="error-reconciliation",
            )
            confirmed = result == "online" and self.is_command_confirmed(
                device, command, sequence
            )
            record["reconcile"] = {"result": result, "confirmed": confirmed}

            # An opt-in retry is limited to an unconfirmed, idempotent switch set.
            if (
                not confirmed
                and record["code"] in (411, 504)
                and self.cloud_retry
                and command.get("safe_retry")
            ):
                await asyncio.sleep(RECONCILE_DELAY)
                record["retry"] = await self.send_cloud(
                    device,
                    command["params"],
                    query=True,
                    force=True,
                    origin="error-retry",
                )
        except asyncio.CancelledError:
            raise
        except Exception as err:
            record["reconcile"] = type(err).__name__
            _LOGGER.debug("Cloud error reconciliation failed for %s", did, exc_info=err)
        finally:
            self.cloud_error_tasks.pop(did, None)

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

        device["params"].update(params)

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
