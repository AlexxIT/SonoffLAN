import asyncio
from contextlib import suppress
import logging
import time

from aiohttp import ClientSession

from .base import SIGNAL_CONNECTED, SIGNAL_UPDATE, XDevice, XRegistryBase
from .cloud import XRegistryCloud
from .local import XRegistryLocal

_LOGGER = logging.getLogger(__name__)

SIGNAL_ADD_ENTITIES = "add_entities"
LOCAL_TTL = 60
LOCAL_COMMAND_TIMEOUT = 1
LOCAL_RETRY_SECONDS = 15
LOCAL_SENSOR_DEFAULT_SECONDS = 30
LOCAL_POLL_LOOP_SECONDS = 1
LOCAL_SENSOR_COMMANDS = frozenset({"sledonline", "statistics", "uiActive"})
LOCAL_TELEMETRY_WAIT_SECONDS = 15
LOCAL_TELEMETRY_MDNS_POLL_SECONDS = 2
LOCAL_SWITCH_WAIT_SECONDS = 5
LOCAL_MDNS_PULL_TIMEOUT_MS = 1500
LOCAL_MDNS_CONCURRENCY = 3
LOCAL_NO_GETSTATE_UIIDS = frozenset({182, 190, 262, 277})
LOCAL_CONNECT_FAIL_CODES = frozenset(
    {"timeout", "E#CON", "E#COE", "E#CRE", "E#COS"}
)
LOCAL_RUNTIME_DEVICE_KEYS = frozenset(
    {
        "localfail",
        "localgetstate",
        "localrecv",
        "localping",
        "localsensorping",
        "localsensorfail",
        "localsensorfail_at",
        "localsensorack_at",
        "localsensorok",
        "localsensorpending",
        "localsensornodata",
        "localsensornodata_at",
        "localtelemetry_at",
        "localconnectfail",
        "localconnectfail_at",
        "localswitch_at",
        "localswitchpending",
        "localswitchnodata",
        "localswitchnodata_at",
        "mdns_service",
    }
)
LOCAL_TELEMETRY_KEYS = frozenset(
    {
        "power",
        "current",
        "voltage",
        "appPower",
        "reactPower",
        "currentTemperature",
        "temperature",
        "currentHumidity",
        "humidity",
    }
)
PREFER_KNOWN_LOCAL = True
LAN_ONLY = True


class XRegistry(XRegistryBase):
    config: dict = None
    task: asyncio.Task | None = None

    def __init__(self, session: ClientSession):
        super().__init__(session)

        self.devices: dict[str, XDevice] = {}
        self.config_entry = None
        self.device_update_intervals: dict[str, float] = {}
        self.store = None
        self.store_task = None
        self.metadata_task: asyncio.Task | None = None
        self.history_manager = None
        self.history_disconnect = None

        self.cloud = XRegistryCloud(session)
        self.cloud.dispatcher_connect(SIGNAL_CONNECTED, self.cloud_connected)
        self.cloud.dispatcher_connect(SIGNAL_UPDATE, self.cloud_update)

        self.local = XRegistryLocal(session)
        self.local.dispatcher_connect(SIGNAL_CONNECTED, self.local_connected)
        self.local.dispatcher_connect(SIGNAL_UPDATE, self.local_update)

        self._local_poll_tasks: dict[str, asyncio.Task] = {}
        self._local_telemetry_tasks: set[asyncio.Task] = set()
        self._inching_locks: dict[str, asyncio.Lock] = {}
        self._inching_pending: dict[str, list[dict]] = {}
        self._mdns_semaphore = asyncio.Semaphore(LOCAL_MDNS_CONCURRENCY)

    def _track_telemetry_task(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._local_telemetry_tasks.add(task)
        task.add_done_callback(self._telemetry_task_done)
        return task

    def _telemetry_task_done(self, task: asyncio.Task):
        self._local_telemetry_tasks.discard(task)
        if task.cancelled():
            return
        if exc := task.exception():
            _LOGGER.warning(
                "Local telemetry recovery task failed",
                exc_info=(type(exc), exc, exc.__traceback__),
            )

    def setup_devices(self, devices: list[XDevice]) -> list:
        from ..devices import get_spec

        entities = []

        # Devices without parent will be first, so via_device option won't fail
        devices = sorted(devices, key=lambda d: d.get("params", {}).get("parentid", ""))

        for device in devices:
            did = device["deviceid"]
            try:
                cfg = self.config["devices"][did]
                device.update(cfg)
                if cfg.get("host"):
                    device["localfail"] = device["localping"] = device["localrecv"] = 0
                    device.pop("localconnectfail", None)
                    device.pop("localconnectfail_at", None)
                if LAN_ONLY and cfg.get("devicekey"):
                    device["devicekey"] = cfg["devicekey"]
            except Exception:
                pass

            if did in self.device_update_intervals:
                device["update_interval"] = self.device_update_intervals[did]

            for key in LOCAL_RUNTIME_DEVICE_KEYS:
                device.pop(key, None)
            if device.get("host"):
                if LAN_ONLY:
                    device["local"] = True
                else:
                    device.setdefault("local", False)
                device.setdefault("localfail", 0)
                device.setdefault("localping", 0)
                device.setdefault("localrecv", 0)
                device.setdefault("localsensorping", 0)

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
                classes = list(get_spec(device))
                # One setting controls freshness for every entity belonging to
                # this physical device. Child entities use their parent's LAN
                # transport and must not create competing interval controls.
                if not device.get("parent"):
                    from ...number import XUpdateInterval

                    classes.append(XUpdateInterval)
                entities += [cls(self, device) for cls in classes]

                self.devices[did] = device

            except Exception as e:
                _LOGGER.warning(f"{did} !! can't setup device", exc_info=e)

        return entities

    @property
    def online(self) -> bool:
        return self.cloud.online is not None or self.local.online

    async def stop(self, *args):
        if self.history_manager:
            await self.history_manager.async_stop()
            self.history_manager = None
        if self.history_disconnect:
            self.history_disconnect()
            self.history_disconnect = None

        if self.metadata_task and self.metadata_task is not asyncio.current_task():
            self.metadata_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.metadata_task
        self.metadata_task = None

        for task in list(self._local_telemetry_tasks):
            task.cancel()
        for task in list(self._local_telemetry_tasks):
            with suppress(asyncio.CancelledError):
                await task
        self._local_telemetry_tasks.clear()

        for task in self._local_poll_tasks.values():
            task.cancel()
        for task in self._local_poll_tasks.values():
            with suppress(asyncio.CancelledError):
                await task
        self._local_poll_tasks.clear()
        self._inching_locks.clear()
        self._inching_pending.clear()

        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            self.task = None

        self.devices.clear()
        self.dispatcher.clear()

        await self.cloud.stop()
        await self.local.stop()

        if self.store_task:
            self.store_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.store_task
            self.store_task = None

        self.session = None

    def schedule_store_save(self):
        if not self.store:
            return
        if self.store_task and not self.store_task.done():
            return
        self.store_task = asyncio.create_task(self._async_store_save())

    async def _async_store_save(self):
        await asyncio.sleep(1)
        devices = [
            {k: v for k, v in device.items() if k not in LOCAL_RUNTIME_DEVICE_KEYS}
            for device in self.devices.values()
        ]
        await self.store.async_save(devices)

    async def send(
        self,
        device: XDevice,
        params: dict = None,
        params_lan: dict = None,
        cmd_lan: str = None,
        query_cloud: bool = True,
        timeout_lan: int = LOCAL_COMMAND_TIMEOUT,
        confirm_lan: dict = None,
    ) -> str | None:
        """Send command to device with LAN and Cloud. Usual params are same.

        LAN will send new device state after update command, Cloud - don't.

        :param device: device object
        :param params: non empty to update state, empty to query state
        :param params_lan: optional if LAN params different (ex iFan03)
        :param cmd_lan: optional if LAN command different
        :param query_cloud: optional query Cloud state after update state,
          ignored if params empty
        :param timeout_lan: optional custom LAN timeout
        :param confirm_lan: optional subset of LAN state expected after an ACK
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
        can_cloud = False if LAN_ONLY else self.can_cloud(device)
        query_cloud = False if LAN_ONLY else query_cloud
        local_params = params_lan if params_lan is not None else params
        expected = confirm_lan

        if can_local and can_cloud:
            # Personal fork policy: give known local devices room to answer.
            ok = await self.local.send(
                main_device, local_params, cmd_lan, seq, timeout_lan
            )

            if ok == "online":
                return ok

            if ok == "ack" and expected is not None:
                ok = await self._confirm_local_state(
                    main_device, expected, timeout_lan
                )
                if ok == "online":
                    return ok
            elif ok == "ack" and local_params and (
                "switch" in local_params or "switches" in local_params
            ):
                self._track_telemetry_task(
                    self._confirm_switch_via_mdns(
                        main_device, local_params, timeout_lan
                    )
                )

            main_device["localping"] = 0  # instant local ping request
            if PREFER_KNOWN_LOCAL and main_device.get("local"):
                return ok

            # otherwise send a command through the cloud
            if ok != "online":
                ok = await self.cloud.send(device, params, seq)
                if ok != "online":
                    main_device["localping"] = 0  # instant local ping request
                elif query_cloud and params:
                    # force update device actual status
                    await self.cloud.send(device, timeout=0)

        elif can_local:
            ok = await self.local.send(
                main_device, local_params, cmd_lan, seq, timeout_lan
            )
            if ok == "ack" and expected is not None:
                ok = await self._confirm_local_state(main_device, expected, timeout_lan)
            elif ok == "ack" and local_params and (
                "switch" in local_params or "switches" in local_params
            ):
                self._track_telemetry_task(
                    self._confirm_switch_via_mdns(
                        main_device, local_params, timeout_lan
                    )
                )
            if ok != "online":
                main_device["localping"] = 0  # instant local ping request

        elif can_cloud:
            ok = await self.cloud.send(device, params, seq)
            if ok == "online" and query_cloud and params:
                await self.cloud.send(device, timeout=0)

        else:
            return None

        return ok

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
        if LAN_ONLY:
            _LOGGER.error("Cloud commands are disabled in SonoffLANonly")
            return None
        if not self.can_cloud(device):
            return None
        ok = await self.cloud.send(device, params)
        if ok == "online" and query and params:
            await self.cloud.send(device, timeout=0)
        return ok

    @staticmethod
    def _value_matches(current, expected) -> bool:
        if isinstance(expected, dict):
            return isinstance(current, dict) and all(
                key in current and XRegistry._value_matches(current[key], value)
                for key, value in expected.items()
            )
        if isinstance(expected, list):
            if not isinstance(current, list):
                return False
            if all(isinstance(item, dict) and "outlet" in item for item in expected):
                current_by_outlet = {
                    item.get("outlet"): item
                    for item in current
                    if isinstance(item, dict) and "outlet" in item
                }
                return all(
                    item["outlet"] in current_by_outlet
                    and XRegistry._value_matches(
                        current_by_outlet[item["outlet"]], item
                    )
                    for item in expected
                )
            return current == expected
        return current == expected

    @staticmethod
    def _local_state_matches(device: XDevice, expected: dict) -> bool:
        return XRegistry._value_matches(device.get("params", {}), expected)

    def _switch_confirmed_since(
        self, device: XDevice, expected: dict, since: float
    ) -> bool:
        if (device.get("localrecv") or 0) < since:
            return False
        return self._local_state_matches(device, expected)

    async def _confirm_switch_via_mdns(
        self, device: XDevice, expected: dict, timeout_lan: int
    ) -> str | None:
        confirm_ts = time.time()
        device["localswitchpending"] = confirm_ts
        device.pop("localswitchnodata_at", None)
        self.dispatcher_send(device["deviceid"], None)

        deadline = confirm_ts + max(min(timeout_lan, LOCAL_SWITCH_WAIT_SECONDS), 0.001)

        while True:
            if device["deviceid"] not in self.devices:
                return "ack"
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            await self._pull_mdns_bounded(
                device,
                timeout_ms=max(1, min(LOCAL_MDNS_PULL_TIMEOUT_MS, int(remaining * 1000))),
            )
            if self._switch_confirmed_since(device, expected, confirm_ts):
                device.pop("localswitchpending", None)
                device["localswitchnodata"] = 0
                self.dispatcher_send(device["deviceid"], None)
                return "online"
            if time.time() >= deadline:
                break
            await asyncio.sleep(min(0.1, max(deadline - time.time(), 0)))

        ts = time.time()
        device["localswitchnodata_at"] = ts
        device["localswitchnodata"] = device.get("localswitchnodata", 0) + 1
        device.pop("localswitchpending", None)
        self.dispatcher_send(device["deviceid"], None)
        return "ack"

    async def _confirm_local_state(
        self,
        device: XDevice,
        expected: dict | None = None,
        timeout_lan: int = LOCAL_COMMAND_TIMEOUT,
    ) -> str | None:
        if expected:
            uiid = device.get("extra", {}).get("uiid")
            if uiid in LOCAL_NO_GETSTATE_UIIDS:
                return await self._confirm_switch_via_mdns(
                    device, expected, timeout_lan
                )
            confirm_ts = time.time()
            ok = await self.local.send(device, None, "getState", None, timeout_lan)
            if (
                ok == "online"
                and (device.get("localrecv") or 0) >= confirm_ts
                and self._local_state_matches(device, expected)
            ):
                return "online"
            return ok if ok != "online" else "ack"

        if "sledOnline" in device.get("params", {}):
            led = device["params"]["sledOnline"]
            return await self.local.send(
                device, {"sledOnline": led}, "sledonline", None, timeout_lan
            )
        return await self.local.send(device, None, "getState", None, timeout_lan)

    async def set_inching(self, device: XDevice, outlet: int, **changes):
        """Update one inching channel while preserving the complete pulses list."""
        if not isinstance(outlet, int):
            raise ValueError("Inching outlet must be an integer")
        if not changes or not changes.keys() <= {"pulse", "switch", "width"}:
            raise ValueError("Unsupported inching fields")
        if "pulse" in changes and changes["pulse"] not in ("on", "off"):
            raise ValueError("Inching pulse must be 'on' or 'off'")
        if "switch" in changes and changes["switch"] not in ("on", "off"):
            raise ValueError("Inching action must be 'on' or 'off'")
        if "width" in changes and (
            not isinstance(changes["width"], int)
            or not 500 <= changes["width"] <= 3_600_000
            or changes["width"] % 500
        ):
            raise ValueError("Inching width must be 500-3600000 ms in 500 ms steps")

        did = device["deviceid"]
        lock = self._inching_locks.setdefault(did, asyncio.Lock())
        async with lock:
            source = self._inching_pending.get(did)
            if source is None:
                source = device.get("params", {}).get("pulses", [])
            pulses = [dict(item) for item in source if isinstance(item, dict)]

            for item in pulses:
                if item.get("outlet") == outlet:
                    missing = changes.keys() - item.keys()
                    if missing:
                        raise ValueError(
                            f"Inching outlet {outlet} did not report fields: "
                            f"{', '.join(sorted(missing))}"
                        )
                    item.update(changes)
                    break
            else:
                raise ValueError(f"Inching outlet {outlet} was not reported by device")

            self._inching_pending[did] = pulses
            confirm = {"pulses": [{"outlet": outlet, **changes}]}
            result = await self.send(
                device,
                {"pulses": pulses},
                cmd_lan="pulses",
                timeout_lan=5,
                confirm_lan=confirm,
            )
            if result == "online":
                self._inching_pending.pop(did, None)
            return result

    @staticmethod
    def _params_have_telemetry(params: dict) -> bool:
        if not params:
            return False
        if params.keys() & LOCAL_TELEMETRY_KEYS:
            return True
        return any(k.startswith("actPow") for k in params)

    def _note_local_telemetry(self, device: XDevice, ts: float | None = None):
        ts = ts or time.time()
        device["localtelemetry_at"] = ts
        device["localsensorok"] = ts
        device["localsensorfail"] = 0
        device["localsensornodata"] = 0
        device.pop("localsensornodata_at", None)
        device.pop("localsensorpending", None)
        device.pop("localconnectfail", None)
        device.pop("localconnectfail_at", None)

    def _note_local_connect_fail(self, device: XDevice):
        ts = time.time()
        device["localconnectfail"] = device.get("localconnectfail", 0) + 1
        device["localconnectfail_at"] = ts
        if device["localconnectfail"] == 3:
            did = device["deviceid"]
            _LOGGER.debug(f"{did} !! Local4 | Host unreachable")
            self.dispatcher_send(did)
        self.dispatcher_send(device["deviceid"], None)

    @staticmethod
    def _sensor_update_interval(device: XDevice) -> float:
        try:
            return max(
                1.0,
                min(
                    float(
                        device.get(
                            "update_interval", LOCAL_SENSOR_DEFAULT_SECONDS
                        )
                    ),
                    300.0,
                ),
            )
        except (TypeError, ValueError):
            return float(LOCAL_SENSOR_DEFAULT_SECONDS)

    async def _pull_mdns_bounded(
        self, device: XDevice, timeout_ms: int = LOCAL_MDNS_PULL_TIMEOUT_MS
    ) -> bool:
        async with self._mdns_semaphore:
            if await self.local.pull_mdns(device, timeout_ms=timeout_ms):
                return True
            return await self.local.pull_mdns_direct(device, timeout_ms=timeout_ms)

    async def _await_sensor_telemetry(self, device: XDevice, poll_ts: float):
        try:
            if device["deviceid"] not in self.devices:
                return
            await self._pull_mdns_bounded(device)
            if (device.get("localtelemetry_at") or 0) >= poll_ts:
                device.pop("localsensorpending", None)
                self.dispatcher_send(device["deviceid"], None)
                return
            await self._verify_sensor_telemetry(device, poll_ts)
        finally:
            # A failed recovery task must not suppress every future sensor poll.
            # Only the task that owns this marker may release it.
            if device.get("localsensorpending") == poll_ts:
                device.pop("localsensorpending", None)
                if device["deviceid"] in self.devices:
                    interval = self._sensor_update_interval(device)
                    device["localsensorping"] = time.time() + min(interval, 5)
                    self.dispatcher_send(device["deviceid"], None)

    async def _verify_sensor_telemetry(
        self,
        device: XDevice,
        poll_ts: float,
        wait_seconds: float = LOCAL_TELEMETRY_WAIT_SECONDS,
    ):
        deadline = poll_ts + max(wait_seconds, 0.001)
        while time.time() < deadline:
            if device["deviceid"] not in self.devices:
                return
            if (device.get("localtelemetry_at") or 0) >= poll_ts:
                device.pop("localsensorpending", None)
                self.dispatcher_send(device["deviceid"], None)
                return
            await self._pull_mdns_bounded(device)
            if (device.get("localtelemetry_at") or 0) >= poll_ts:
                device.pop("localsensorpending", None)
                self.dispatcher_send(device["deviceid"], None)
                return
            await asyncio.sleep(LOCAL_TELEMETRY_MDNS_POLL_SECONDS)

        ts = time.time()
        misses = device.get("localsensornodata", 0) + 1
        device["localsensornodata_at"] = ts
        device["localsensornodata"] = misses
        device["localsensorfail_at"] = ts
        interval = self._sensor_update_interval(device)
        device["localsensorping"] = ts + min(
            interval * max(device["localsensornodata"], 1), 120
        )
        device.pop("localsensorpending", None)
        self.dispatcher_send(device["deviceid"], None)

    async def refresh_cache_metadata(self, data: dict, options: dict):
        """Reconcile cloud metadata without enabling cloud control."""
        if not LAN_ONLY or not data.get("password"):
            return
        try:
            await self.cloud.login(**data)
            fresh = await self.cloud.get_devices(options.get("homes"))
        except Exception as e:
            _LOGGER.debug("Can't refresh LAN device metadata from cloud", exc_info=e)
            return
        finally:
            await self.cloud.stop()

        for src in fresh:
            did = src.get("deviceid")
            if (
                not did
                or not src.get("name")
                or not isinstance(src.get("params"), dict)
            ):
                continue
            if src.get("extra", {}).get("uiid") is None:
                continue

            device = self.devices.get(did)
            if device and device.get("extra", {}).get("uiid") is not None:
                runtime = {
                    key: device[key]
                    for key in LOCAL_RUNTIME_DEVICE_KEYS
                    if key in device
                }
                host = device.get("host")
                params = {**src.get("params", {}), **device.get("params", {})}
                device.update(src)
                device["params"] = params
                device.update(runtime)
                if host and not device.get("host"):
                    device["host"] = host
                continue

            # Replace an incomplete LAN-discovery shell, or add a newly paired
            # cloud device, with the complete metadata required by get_spec().
            candidate = dict(src)
            if device and device.get("host") and not candidate.get("host"):
                candidate["host"] = device["host"]
            self.devices.pop(did, None)
            entities = self.setup_devices([candidate])
            if entities:
                self.dispatcher_send(SIGNAL_ADD_ENTITIES, entities)

        # Persist the complete reconciled inventory so the next startup does
        # not depend on the timing of cloud refresh versus mDNS discovery.
        self.schedule_store_save()

    def cloud_connected(self):
        for deviceid in self.devices.keys():
            self.dispatcher_send(deviceid)

        # if not self.task:
        #     self.task = asyncio.create_task(self.run_forever())

    def local_connected(self):
        task_alive = False
        if self.task:
            done = getattr(self.task, "done", None)
            task_alive = not done() if callable(done) else True
        if not task_alive:
            self.task = asyncio.create_task(self.run_forever())
        for deviceid in self.devices:
            self.dispatcher_send(deviceid)

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
                    # Wait for complete cloud metadata instead of poisoning the
                    # persistent cache with a record that setup_devices rejects.
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

        elif "devicekey" in device and not LAN_ONLY:
            # unencripted device with devicekey in config, this means that the
            # DIY device is still connected to the ewelink account
            device.pop("devicekey")

        # realid can be different from mainid for SPM-4RELAY
        realid = msg.get("subdevid", mainid)
        if not device.get("parent") and "parentid" not in device.get("params", {}):
            realid = mainid
        tag = "Local3" if "host" in msg else "Local0"
        host = msg.get("host", "^^^")
        device["local_seq"] = seq = msg.get("seq")

        _LOGGER.debug(f"{realid} <= {tag} | {host} | %s | {seq}", params)

        if "params" in device:
            device["params"].update(params)
        else:
            device["params"] = params

        # we can get data from device, but without host
        host_changed = "host" in msg and device.get("host") != msg["host"]
        if host_changed:
            # params for custom sensor
            device["host"] = params["host"] = msg["host"]
            device["localtype"] = msg["localtype"]

        if mdns_service := msg.get("mdns_service"):
            device["mdns_service"] = mdns_service

        ts = time.time()
        device["local"] = True
        device["localfail"] = 0
        device["localping"] = ts + self._sensor_update_interval(device)
        device["localrecv"] = ts

        if "pulses" in params and (pending := self._inching_pending.get(mainid)):
            if self._value_matches(params["pulses"], pending):
                self._inching_pending.pop(mainid, None)

        if self._params_have_telemetry(params):
            self._note_local_telemetry(device, ts)

        if "switch" in params or "switches" in params:
            device["localswitch_at"] = ts

        device.pop("localconnectfail", None)
        device.pop("localconnectfail_at", None)

        self.dispatcher_send(realid, params)
        if host_changed:
            self.schedule_store_save()

        # send empty msg to main device for updating available flag
        if realid != mainid:
            self.dispatcher_send(mainid, None)

    def _schedule_update_local(self, device: XDevice, ts: float):
        did = device["deviceid"]
        task = self._local_poll_tasks.get(did)
        if task and not task.done():
            return
        self._local_poll_tasks[did] = asyncio.create_task(
            self._update_local_guarded(device, ts)
        )

    async def _await_local_poll_tasks(self, timeout: float = 2.0):
        tasks = [t for t in self._local_poll_tasks.values() if t and not t.done()]
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)

    async def _update_local_guarded(self, device: XDevice, ts: float):
        try:
            await self.update_local(device, ts)
        except Exception as e:
            _LOGGER.warning(
                "update_local %s", device.get("deviceid"), exc_info=e
            )

    async def run_forever(self):
        while True:
            ts = time.time()
            for device in self.devices.values():
                try:
                    if "local" in device:
                        self._schedule_update_local(device, ts)
                    elif parent := device.get("parent"):
                        # Support childrens only for SPM-Main (128)
                        if parent.get("localtype") == "meter":
                            self.update_local_child(parent, device)
                except Exception as e:
                    _LOGGER.warning("run_forever", exc_info=e)
            await asyncio.sleep(LOCAL_POLL_LOOP_SECONDS)

    async def update_local(self, device: XDevice, ts: float):
        uiid = device["extra"]["uiid"]

        # 1. Poll realtime sensors when telemetry is stale (not on every LAN message).
        last_telemetry = device.get("localtelemetry_at") or 0
        interval = self._sensor_update_interval(device)
        # LAN pushes remain authoritative. Prompt a fresh mDNS publication only
        # after the device-specific callback interval has elapsed.
        telemetry_due = not last_telemetry or ts >= last_telemetry + interval
        if (
            telemetry_due
            and not device.get("localsensorpending")
            and ts >= device.get("localsensorping", 0)
        ):
            # TH10R2 (15) and THR316D/THR320D (181) shouldn't be here, but anyway
            if uiid in (15, 32, 181, 182, 190, 262, 277):
                if "sledOnline" in device["params"]:
                    params = {"sledOnline": device["params"]["sledOnline"]}
                    gap = (
                        2
                        if device.get("localfail", 0) >= 3
                        else interval
                    )
                    device["localsensorping"] = ts + gap
                    await self.send_local(device, "sledonline", params)
                    return
            elif uiid == 126:
                gap = (
                    2
                    if device.get("localfail", 0) >= 3
                    else interval
                )
                device["localsensorping"] = ts + gap
                await self.send_local(device, "statistics")
                return

        # 2. Availability ping (some devices use sledonline instead of getState).
        if ts >= device.get("localping", 0):
            if device.get("localgetstate") is False:
                if not await self._pull_mdns_bounded(device):
                    device["localping"] = ts + interval
            elif uiid in LOCAL_NO_GETSTATE_UIIDS:
                if "sledOnline" in device["params"]:
                    await self.send_local(
                        device,
                        "sledonline",
                        {"sledOnline": device["params"]["sledOnline"]},
                    )
                else:
                    device["localping"] = ts + interval
            else:
                await self.send_local(device)

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
        self._track_telemetry_task(self.send_local(parent, "uiActive", params))

    def can_cloud(self, device: XDevice) -> bool:
        if LAN_ONLY:
            return False
        if not self.cloud.online:
            return False
        return device.get("online")

    def can_local(self, device: XDevice) -> bool:
        """Return whether this device has a usable LAN control path."""
        if not self.local.online:
            return False
        if parent := device.get("parent"):
            # Known local parents - SPM-Main, RFBridge and ZBBridge-P
            # But ZBBridge-P can't control local devices
            if parent.get("localtype") in ("meter", "rf"):
                if LAN_ONLY and parent.get("host"):
                    return True
                return parent.get("local")
        if LAN_ONLY and device.get("host"):
            return True
        return device.get("local")

    def local_available(self, device: XDevice) -> bool:
        """Return whether the LAN path is currently responding."""
        if not self.can_local(device):
            return False
        target = device.get("parent", device)
        if LAN_ONLY and target.get("host"):
            return target.get("localconnectfail", 0) < 3
        return bool(target.get("local"))

    async def send_local(
        self, device: XDevice, command: str = None, params: dict = None
    ):
        poll_ts = time.time() if command in LOCAL_SENSOR_COMMANDS else None
        ok = await self.local.send(device, params, command)
        if ok in ("online", "online_no_data", "ack"):
            was_local = device["local"]
            device["local"] = True
            device["localfail"] = 0
            device["localping"] = time.time() + self._sensor_update_interval(
                device
            )
            device.pop("localconnectfail", None)
            device.pop("localconnectfail_at", None)
            did = device["deviceid"]
            if not was_local:
                _LOGGER.debug(f"{did} !! Local4 | Device online")
            # A device may remain LAN-capable while its entities are unavailable
            # after transport failures. Refresh them after every successful probe.
            self.dispatcher_send(did)
            if command is None and ok == "online_no_data":
                device["localgetstate"] = False
                await self._pull_mdns_bounded(device)
            if poll_ts is not None:
                device["localsensorack_at"] = time.time()
                if (device.get("localtelemetry_at") or 0) >= poll_ts:
                    device["localsensorfail"] = 0
                    device["localsensornodata"] = 0
                else:
                    device["localsensorpending"] = poll_ts
                    self.dispatcher_send(device["deviceid"], None)
                    self._track_telemetry_task(
                        self._await_sensor_telemetry(device, poll_ts)
                    )
            return

        if command in LOCAL_SENSOR_COMMANDS:
            fails = device.get("localsensorfail", 0) + 1
            device["localsensorfail"] = fails
            device["localsensorfail_at"] = time.time()
            interval = self._sensor_update_interval(device)
            device["localsensorping"] = time.time() + min(interval * fails, 120)
            device.pop("localsensorpending", None)
            if ok in LOCAL_CONNECT_FAIL_CODES:
                self._note_local_connect_fail(device)
            else:
                self.dispatcher_send(device["deviceid"], None)
            return

        # requests with command can't fail device to offline
        if command:
            if ok in LOCAL_CONNECT_FAIL_CODES:
                self._note_local_connect_fail(device)
            return

        if ok in LOCAL_CONNECT_FAIL_CODES:
            self._note_local_connect_fail(device)

        device["localfail"] = device.get("localfail", 0) + 1

        if device["localfail"] < 3:
            return

        device["localping"] = time.time() + min(
            LOCAL_RETRY_SECONDS, self._sensor_update_interval(device)
        )
