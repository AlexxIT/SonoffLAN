import asyncio
import json
import time
from types import SimpleNamespace

import aiohttp
import pytest
from zeroconf import DNSQuestionType

from custom_components.sonoff.core.devices import spec
from custom_components.sonoff.core.ewelink import (
    SIGNAL_ADD_ENTITIES,
    SIGNAL_UPDATE,
    XDevice,
    XRegistry,
    XRegistryLocal,
)
from custom_components.sonoff.core.ewelink.local import (
    decrypt,
    encrypt,
    parse_deviceid_from_service_name,
)
from custom_components.sonoff.fan import XFan
from custom_components.sonoff.light import XLightL1
from custom_components.sonoff.sensor import XCloudEnergy
from . import DEVICEID, _REAL_CREATE_TASK, save_to


def test_bulk():
    registry_send = []

    device = XDevice()
    loop = asyncio.new_event_loop()
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    registry.send = save_to(registry_send)

    loop.create_task(
        registry.send_bulk(device, {"switches": [{"outlet": 1, "switch": "off"}]})
    )
    loop.create_task(
        registry.send_bulk(device, {"switches": [{"outlet": 2, "switch": "off"}]})
    )
    loop.run_until_complete(asyncio.sleep(0))
    assert device["params_bulk"]["switches"] == [
        {"outlet": 1, "switch": "off"},
        {"outlet": 2, "switch": "off"},
    ]

    loop.create_task(
        registry.send_bulk(device, {"switches": [{"outlet": 2, "switch": "off"}]})
    )
    loop.create_task(
        registry.send_bulk(device, {"switches": [{"outlet": 1, "switch": "on"}]})
    )

    loop.run_until_complete(asyncio.sleep(0.1))
    assert registry_send[0][1] == {
        "switches": [{"outlet": 1, "switch": "on"}, {"outlet": 2, "switch": "off"}]
    }

    loop.close()


def test_send_prefers_known_local_without_cloud_fallback():
    calls = []
    loop = asyncio.new_event_loop()
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    registry.local.online = True
    registry.cloud.online = True

    device = XDevice(deviceid=DEVICEID, local=True, online=True)

    async def local_send(*args):
        calls.append(("local", args))
        return "timeout"

    async def cloud_send(*args, **kwargs):
        calls.append(("cloud", args, kwargs))
        return "online"

    registry.local.send = local_send
    registry.cloud.send = cloud_send

    ok = loop.run_until_complete(
        registry.send(device, {"hundredDaysKwh": "get"}, query_cloud=False)
    )
    loop.close()

    assert ok == "timeout"
    assert [call[0] for call in calls] == ["local"]


def test_send_uses_cached_host_before_mdns_marks_device_local():
    calls = []
    loop = asyncio.new_event_loop()
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    registry.local.online = True
    registry.cloud.online = False

    device = XDevice(
        deviceid=DEVICEID,
        host="192.0.2.88:8081",
        local=False,
        localfail=0,
        localping=0,
        params={"switch": "off"},
    )

    async def local_send(*args):
        calls.append(args)
        return "online"

    registry.local.send = local_send

    ok = loop.run_until_complete(
        registry.send(device, {"switch": "on"}, timeout_lan=7)
    )
    loop.close()

    assert ok == "online"
    assert len(calls) == 1
    assert calls[0][0] is device
    assert calls[0][1] == {"switch": "on"}
    assert calls[0][2] is None
    assert calls[0][4] == 7


def test_cloud_energy_uses_normal_send_without_cloud_query():
    loop = asyncio.new_event_loop()
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(deviceid=DEVICEID, name="Device1", params={})
    entity_cls = spec(
        XCloudEnergy,
        param="hundredDaysKwhData",
        get_params={"hundredDaysKwh": "get"},
    )

    async def send(*args, **kwargs):
        registry.send_args = args, kwargs
        asyncio.get_running_loop().call_soon(
            entity.set_state, {"hundredDaysKwhData": "000009"}
        )
        return "online"

    registry.send = send
    entity = entity_cls(registry, device)

    ok = loop.run_until_complete(entity.get_update())
    loop.close()

    assert ok is True
    assert registry.send_args == (
        (device, {"hundredDaysKwh": "get"}),
        {"query_cloud": False, "timeout_lan": 5},
    )


def test_cloud_energy_initializes_reporting_before_cached_state():
    registry = XRegistry(None)
    device = XDevice(
        deviceid=DEVICEID,
        name="Device1",
        reporting={"hundredDaysKwhData": (120, 2)},
        params={"config": {"hundredDaysKwhData": "000009000108"}},
    )
    entity_cls = spec(XCloudEnergy, param="hundredDaysKwhData")

    entity = entity_cls(registry, device)

    assert entity.report_dt == 120
    assert entity.report_history == 2
    assert entity.native_value == 0.09
    assert entity.extra_state_attributes == {"history": [0.09, 0.18]}


def test_cloud_energy_does_not_throttle_after_ack_without_payload():
    loop = asyncio.new_event_loop()
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(deviceid=DEVICEID, name="Device1", params={})
    entity_cls = spec(
        XCloudEnergy,
        param="hundredDaysKwhData",
        get_params={"hundredDaysKwh": "get"},
        response_timeout=0.001,
    )

    async def send(*args, **kwargs):
        return "online"

    registry.send = send
    entity = entity_cls(registry, device)

    ok = loop.run_until_complete(entity.get_update())
    loop.close()

    assert ok is False
    assert entity.next_ts == 0


def test_local_update_dispatches_plaintext_energy_data():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(deviceid=DEVICEID, params={})
    registry.devices = {DEVICEID: device}

    updates = []
    registry.dispatcher_connect(DEVICEID, updates.append)
    registry.local.dispatcher_send(
        SIGNAL_UPDATE,
        {
            "deviceid": DEVICEID,
            "seq": 1,
            "params": {"config": {"hundredDaysKwhData": "000009"}},
        },
    )

    # Device cache keeps the nested shape; energy entity unwraps config.
    assert device["params"] == {"config": {"hundredDaysKwhData": "000009"}}
    assert updates == [{"config": {"hundredDaysKwhData": "000009"}}]


def test_local_command_failure_does_not_increment_localfail():
    loop = asyncio.new_event_loop()
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(deviceid=DEVICEID, local=True, localfail=2, localping=0)

    async def local_send(*args, **kwargs):
        return "timeout"

    registry.local.send = local_send

    loop.run_until_complete(registry.send_local(device, "sledonline", {"sledOnline": "on"}))
    loop.close()

    assert device["local"] is True
    assert device["localfail"] == 2
    assert device["localping"] == 0


def test_local_sensor_refresh_uses_separate_retry_gate(monkeypatch):
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(
        deviceid=DEVICEID,
        extra={"uiid": 32},
        local=True,
        localfail=3,
        localping=9999,
        localtelemetry_at=10,
        localsensorping=0,
        params={"sledOnline": "on"},
    )
    calls = []

    async def send_local(*args):
        calls.append(args)

    def create_task(coro):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()

    registry.send_local = send_local

    asyncio.run(registry.update_local(device, 40))

    assert calls == [(device, "sledonline", {"sledOnline": "on"})]
    assert device["localsensorping"] == 42


def test_send_local_records_sensor_ack_without_telemetry(monkeypatch):
    monkeypatch.setattr(asyncio, "create_task", _REAL_CREATE_TASK)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(deviceid=DEVICEID, local=True, localfail=0, localping=0)
    registry.devices = {DEVICEID: device}
    scheduled = []

    def track_telemetry(coro):
        scheduled.append(True)
        coro.close()

    async def local_send(*args, **kwargs):
        return "ack"

    registry.local.send = local_send
    registry._track_telemetry_task = track_telemetry

    async def run():
        await registry.send_local(device, "sledonline", {"sledOnline": "on"})

    loop.run_until_complete(run())
    loop.close()

    assert device["localsensorack_at"] > 0
    assert device.get("localtelemetry_at") is None
    assert device.get("localsensorok") is None
    assert device.get("localsensorfail", 0) == 0
    assert scheduled == [True]


def test_local_update_telemetry_clears_nodata_state():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(
        deviceid=DEVICEID,
        params={},
        localsensornodata=2,
        localsensornodata_at=100.0,
    )
    registry.devices = {DEVICEID: device}
    registry.local_update(
        {
            "deviceid": DEVICEID,
            "subdevid": "different-id",
            "params": {"power": "10.0", "current": "0.1", "voltage": "120.0"},
        }
    )
    assert device["localtelemetry_at"] > 0
    assert device["localsensorok"] == device["localtelemetry_at"]
    assert device["localsensorfail"] == 0
    assert device["localsensornodata"] == 0
    assert "localsensornodata_at" not in device


def test_refresh_cache_replaces_incomplete_device_and_adds_entities():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    registry.config = None
    registry.devices = {
        DEVICEID: XDevice(deviceid=DEVICEID, host="192.0.2.88:8081")
    }
    fresh = {
        "deviceid": DEVICEID,
        "name": "Garage Door Motor",
        "productModel": "S40TPB",
        "devicekey": "0123456789abcdef",
        "extra": {"uiid": 182},
        "params": {
            "switch": "off",
            "sledOnline": "on",
            "staMac": "AA:BB:CC:DD:EE:FF",
        },
    }
    added = []
    saves = []

    async def login(**kwargs):
        return True

    async def get_devices(homes=None):
        return [fresh]

    async def stop():
        return None

    registry.cloud.login = login
    registry.cloud.get_devices = get_devices
    registry.cloud.stop = stop
    registry.schedule_store_save = lambda: saves.append(True)
    registry.dispatcher_connect(SIGNAL_ADD_ENTITIES, added.extend)

    asyncio.run(
        registry.refresh_cache_metadata(
            {"password": "secret", "username": "user"}, {}
        )
    )

    device = registry.devices[DEVICEID]
    assert device["name"] == "Garage Door Motor"
    assert device["extra"]["uiid"] == 182
    assert device["host"] == "192.0.2.88:8081"
    assert any(entity.uid == "1" for entity in added)
    assert saves == [True]


def test_unknown_encrypted_lan_device_is_not_cached_as_incomplete():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    registry.config = {"devices": {}}

    registry.local_update(
        {
            "deviceid": DEVICEID,
            "host": "192.0.2.88:8081",
            "data": "not-decryptable",
            "iv": "not-decryptable",
        }
    )

    assert DEVICEID not in registry.devices


def test_device_specific_sensor_update_interval():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)

    assert registry._sensor_update_interval(XDevice()) == 30
    assert registry._sensor_update_interval(XDevice(update_interval=15)) == 15
    assert registry._sensor_update_interval(XDevice(update_interval=1)) == 1
    assert registry._sensor_update_interval(XDevice(update_interval=0)) == 1
    assert registry._sensor_update_interval(XDevice(update_interval=999)) == 300


def test_local_update_switch_sets_switch_timestamp_and_resets_watchdog(monkeypatch):
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    monkeypatch.setattr(time, "time", lambda: 100.0)
    device = XDevice(
        deviceid=DEVICEID,
        params={"switch": "off"},
        update_interval=15,
    )
    registry.devices = {DEVICEID: device}
    registry.local_update(
        {"deviceid": DEVICEID, "params": {"switch": "on", "power": "10.0"}}
    )
    assert device["localswitch_at"] == 100.0
    assert device["localping"] == 115.0
    assert device["params"]["switch"] == "on"


def test_general_device_refreshes_only_after_callback_interval():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(
        deviceid=DEVICEID,
        extra={"uiid": 1},
        local=True,
        localping=115,
        update_interval=15,
        params={"switch": "on"},
    )
    calls = []

    async def send_local(*args, **kwargs):
        calls.append(args)

    registry.send_local = send_local

    asyncio.run(registry.update_local(device, 114))
    assert calls == []

    asyncio.run(registry.update_local(device, 115))
    assert calls == [(device,)]


def test_update_local_skips_getstate_for_s40_uiids():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    now = time.time()
    device = XDevice(
        deviceid=DEVICEID,
        extra={"uiid": 182},
        local=True,
        localping=0,
        localtelemetry_at=now,
        params={"sledOnline": "on"},
    )
    calls = []

    async def send_local(*args, **kwargs):
        calls.append(args)

    registry.send_local = send_local

    asyncio.run(registry.update_local(device, now))
    assert calls == [(device, "sledonline", {"sledOnline": "on"})]


@pytest.mark.parametrize("uiid", [32, 182])
def test_standalone_power_devices_use_sledonline_at_update_interval(uiid):
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(
        deviceid=DEVICEID,
        extra={"uiid": uiid},
        local=True,
        localping=9999,
        localtelemetry_at=100,
        localsensorping=0,
        update_interval=60,
        params={"sledOnline": "on"},
    )
    calls = []

    async def send_local(*args, **kwargs):
        calls.append(args)

    registry.send_local = send_local

    asyncio.run(registry.update_local(device, 149))
    assert calls == []

    asyncio.run(registry.update_local(device, 160))
    assert calls == [(device, "sledonline", {"sledOnline": "on"})]
    assert device["localsensorping"] == 220


def test_s40_poll_preserves_disabled_sledonline_value():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(
        deviceid=DEVICEID,
        extra={"uiid": 182},
        local=True,
        localping=9999,
        localtelemetry_at=99,
        localsensorping=0,
        update_interval=1,
        params={"sledOnline": "off"},
    )
    calls = []

    async def send_local(*args, **kwargs):
        calls.append(args)

    registry.send_local = send_local

    asyncio.run(registry.update_local(device, 100))

    assert calls == [(device, "sledonline", {"sledOnline": "off"})]
    assert device["localsensorping"] == 101


def test_update_local_does_not_overlap_pending_telemetry_watchdog():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    now = time.time()
    device = XDevice(
        deviceid=DEVICEID,
        extra={"uiid": 182},
        local=True,
        localping=now + 60,
        localsensorpending=now - 1,
        localsensorping=0,
        update_interval=1,
        params={"sledOnline": "on"},
    )
    calls = []

    async def send_local(*args, **kwargs):
        calls.append(args)

    registry.send_local = send_local

    asyncio.run(registry.update_local(device, now))
    assert calls == []


def test_update_local_accepts_false_sledonline_value():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    now = time.time()
    device = XDevice(
        deviceid=DEVICEID,
        extra={"uiid": 181},
        local=True,
        localping=now + 60,
        localsensorping=0,
        update_interval=1,
        params={"sledOnline": 0},
    )
    calls = []

    async def send_local(*args, **kwargs):
        calls.append(args)

    registry.send_local = send_local

    asyncio.run(registry.update_local(device, now))
    assert calls == [(device, "sledonline", {"sledOnline": 0})]


def test_send_local_marks_telemetry_when_payload_arrives_inline():
    loop = asyncio.new_event_loop()
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(
        deviceid=DEVICEID,
        local=True,
        localfail=0,
        localping=0,
        params={"sledOnline": "on"},
    )
    registry.devices = {DEVICEID: device}

    async def local_send(*args, **kwargs):
        registry.local_update(
            {
                "deviceid": DEVICEID,
                "params": {"power": "12.34", "current": "0.10", "voltage": "120.0"},
            }
        )
        return "online"

    registry.local.send = local_send
    loop.run_until_complete(
        registry.send_local(device, "sledonline", {"sledOnline": "on"})
    )
    loop.close()

    assert device["localtelemetry_at"] > 0
    assert device["localsensorok"] == device["localtelemetry_at"]
    assert device["localsensorfail"] == 0


def test_verify_sensor_telemetry_marks_nodata_when_payload_missing():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)

    async def pull_mdns(device, **kwargs):
        return False

    registry._pull_mdns_bounded = pull_mdns
    device = XDevice(deviceid=DEVICEID, local=True)
    registry.devices = {DEVICEID: device}
    poll_ts = time.time()
    loop.run_until_complete(
        registry._verify_sensor_telemetry(device, poll_ts, wait_seconds=0)
    )
    loop.close()

    assert device["localsensornodata_at"] > 0
    assert device["localsensornodata"] == 1
    assert device.get("localsensorfail", 0) == 0


def test_verify_sensor_telemetry_records_consecutive_misses():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(
        deviceid=DEVICEID, local=True, localsensornodata=2
    )
    registry.devices = {DEVICEID: device}
    async def pull_mdns(dev, **kwargs):
        return False

    registry._pull_mdns_bounded = pull_mdns
    loop.run_until_complete(
        registry._verify_sensor_telemetry(device, time.time(), wait_seconds=0)
    )
    loop.close()

    assert device["localsensornodata"] == 3


def test_verify_sensor_telemetry_pulls_mdns_until_payload_arrives(monkeypatch):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(deviceid=DEVICEID, local=True)
    poll_ts = time.time()
    calls = {"n": 0}

    async def pull_mdns(dev, **kwargs):
        calls["n"] += 1
        registry._note_local_telemetry(dev, time.time())
        return True

    registry._pull_mdns_bounded = pull_mdns
    registry.devices = {DEVICEID: device}
    loop.run_until_complete(registry._verify_sensor_telemetry(device, poll_ts))
    loop.close()

    assert calls["n"] >= 1
    assert device["localtelemetry_at"] > 0
    assert device.get("localsensornodata") in (None, 0)


def test_await_sensor_telemetry_releases_pending_after_failure():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    poll_ts = time.time()
    device = XDevice(
        deviceid=DEVICEID,
        local=True,
        update_interval=30,
        localsensorpending=poll_ts,
    )
    registry.devices = {DEVICEID: device}

    async def pull_mdns(dev, **kwargs):
        raise RuntimeError("mDNS pull failed")

    registry._pull_mdns_bounded = pull_mdns
    before = time.time()
    with pytest.raises(RuntimeError, match="mDNS pull failed"):
        loop.run_until_complete(registry._await_sensor_telemetry(device, poll_ts))
    loop.close()

    assert "localsensorpending" not in device
    assert before < device["localsensorping"] <= before + 5.1


def test_await_sensor_telemetry_does_not_release_newer_pending_poll():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    poll_ts = time.time()
    newer_poll_ts = poll_ts + 1
    device = XDevice(
        deviceid=DEVICEID,
        local=True,
        localsensorpending=poll_ts,
    )
    registry.devices = {DEVICEID: device}

    async def pull_mdns(dev, **kwargs):
        dev["localsensorpending"] = newer_poll_ts
        raise RuntimeError("older task failed")

    registry._pull_mdns_bounded = pull_mdns
    with pytest.raises(RuntimeError, match="older task failed"):
        loop.run_until_complete(registry._await_sensor_telemetry(device, poll_ts))
    loop.close()

    assert device["localsensorpending"] == newer_poll_ts
    assert "localsensorping" not in device


def test_send_local_records_sensor_command_failure():
    loop = asyncio.new_event_loop()
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(deviceid=DEVICEID, local=True, localfail=0, localping=0)
    updates = []
    registry.dispatcher_connect(DEVICEID, lambda p: updates.append(p))

    async def local_send_fail(*args, **kwargs):
        return "timeout"

    registry.local.send = local_send_fail
    loop.run_until_complete(
        registry.send_local(device, "sledonline", {"sledOnline": "on"})
    )
    loop.close()

    assert device["localsensorfail"] == 1
    assert device["localsensorfail_at"] > 0
    assert updates == [None]


def test_run_forever_schedules_parallel_device_polls(monkeypatch):
    monkeypatch.setattr(asyncio, "create_task", _REAL_CREATE_TASK)
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    slow = XDevice(
        deviceid="1000000001",
        extra={"uiid": 1},
        local=True,
        localping=0,
        params={},
    )
    fast = XDevice(
        deviceid="1000000002",
        extra={"uiid": 1},
        local=True,
        localping=0,
        params={},
    )
    registry.devices = {"1000000001": slow, "1000000002": fast}
    started = []

    async def update_local(device, ts):
        started.append(device["deviceid"])
        if device["deviceid"] == "1000000001":
            await asyncio.sleep(0.05)

    registry.update_local = update_local

    async def run_once():
        ts = time.time()
        for device in registry.devices.values():
            registry._schedule_update_local(device, ts)
        await registry._await_local_poll_tasks()

    asyncio.run(run_once())

    assert set(started) == {"1000000001", "1000000002"}


def test_run_forever_skips_overlapping_poll_for_same_device(monkeypatch):
    monkeypatch.setattr(asyncio, "create_task", _REAL_CREATE_TASK)
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(
        deviceid=DEVICEID,
        extra={"uiid": 1},
        local=True,
        localping=0,
        params={},
    )
    registry.devices = {DEVICEID: device}
    calls = {"n": 0}

    async def update_local(dev, ts):
        calls["n"] += 1
        await asyncio.sleep(0.05)

    registry.update_local = update_local

    async def run_twice():
        ts = time.time()
        registry._schedule_update_local(device, ts)
        registry._schedule_update_local(device, ts)
        await registry._await_local_poll_tasks()

    asyncio.run(run_twice())

    assert calls["n"] == 1


def test_send_local_connect_fail_marks_path_unavailable_not_incapable():
    loop = asyncio.new_event_loop()
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    registry.local.online = True
    device = XDevice(
        deviceid=DEVICEID,
        host="192.0.2.88:8081",
        local=True,
        localfail=0,
        localping=0,
        params={"sledOnline": "on"},
    )
    updates = []
    registry.dispatcher_connect(DEVICEID, lambda *args: updates.append(args))

    async def local_send(*args, **kwargs):
        return "E#CON"

    registry.local.send = local_send
    for _ in range(3):
        loop.run_until_complete(
            registry.send_local(device, "sledonline", {"sledOnline": "on"})
        )
    loop.close()

    assert device["localconnectfail"] == 3
    assert device["localconnectfail_at"] > 0
    assert device["local"] is True
    assert registry.can_local(device)
    assert not registry.local_available(device)
    assert device["localsensorfail"] == 3


def test_sensor_protocol_error_does_not_mark_lan_path_unavailable():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    registry.local.online = True
    device = XDevice(
        deviceid=DEVICEID,
        host="192.0.2.88:8081",
        local=True,
        localfail=0,
        localping=0,
        params={"sledOnline": "on"},
    )

    async def local_send(*args, **kwargs):
        return "error"

    registry.local.send = local_send
    asyncio.run(
        registry.send_local(device, "uiActive", {"uiActive": 60, "NO_SAVE_DB": True})
    )

    assert device["localsensorfail"] == 1
    assert "localconnectfail" not in device
    assert registry.local_available(device)


def test_lan_control_retries_after_transport_availability_failure():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    registry.local.online = True
    device = XDevice(
        deviceid=DEVICEID,
        host="192.0.2.88:8081",
        local=True,
        localconnectfail=3,
        params={"switch": "on"},
    )
    calls = []

    async def local_send(*args, **kwargs):
        calls.append((args, kwargs))
        return "online"

    registry.local.send = local_send
    result = asyncio.run(registry.send(device, {"switch": "off"}))

    assert result == "online"
    assert len(calls) == 1


def test_successful_retry_clears_failure_latch_before_availability_dispatch():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    registry.local.online = True
    device = XDevice(
        deviceid=DEVICEID,
        host="192.0.2.36:8081",
        local=True,
        localfail=3,
        localping=0,
        localconnectfail=3,
        localconnectfail_at=100.0,
        params={"switch": "on"},
    )
    registry.devices = {DEVICEID: device}
    availability_at_dispatch = []
    registry.dispatcher_connect(
        DEVICEID,
        lambda *args: availability_at_dispatch.append(
            registry.local_available(device)
        ),
    )

    async def local_send(*args, **kwargs):
        return "online"

    registry.local.send = local_send

    assert registry.local_available(device) is False
    asyncio.run(registry.send_local(device))

    assert availability_at_dispatch == [True]
    assert device["local"] is True
    assert device["localfail"] == 0
    assert "localconnectfail" not in device
    assert "localconnectfail_at" not in device


def test_local_switches_disconnect_confirms_with_sledonline():
    class Response:
        headers = {}

        async def json(self):
            return {"error": 0, "seq": 2, "data": {"power": "10.00"}}

    class Session:
        calls = []

        async def post(self, url, **kwargs):
            self.calls.append(url)
            if url.endswith("/zeroconf/switches"):
                raise aiohttp.ServerDisconnectedError()
            return Response()

    loop = asyncio.new_event_loop()
    registry = XRegistryLocal(Session())
    device = XDevice(
        deviceid=DEVICEID,
        host="192.0.2.88:8081",
        localtype="plug",
        params={"sledOnline": "on"},
    )
    updates = []
    registry.dispatcher_connect(SIGNAL_UPDATE, updates.append)

    ok = loop.run_until_complete(
        registry.send(device, {"switches": [{"outlet": 0, "switch": "on"}]})
    )
    loop.close()

    assert ok == "E#COS"
    assert registry.session.calls == [
        "http://192.0.2.88:8081/zeroconf/switches",
    ]
    assert updates == []


def test_local_connected_dispatches_each_device_once():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    registry.devices = {
        "1000000001": XDevice(deviceid="1000000001"),
        "1000000002": XDevice(deviceid="1000000002"),
    }
    calls = []
    registry.dispatcher_send = calls.append
    registry.task = object()

    registry.local_connected()

    assert calls == ["1000000001", "1000000002"]


def test_local_connected_keeps_live_poll_loop(monkeypatch):
    registry: XRegistry = XRegistry(None)
    registry.task = SimpleNamespace(done=lambda: False)

    def unexpected_create(coro):
        coro.close()
        raise AssertionError("live polling loop was replaced")

    monkeypatch.setattr(asyncio, "create_task", unexpected_create)
    registry.local_connected()


def test_local_connected_restarts_finished_poll_loop(monkeypatch):
    registry: XRegistry = XRegistry(None)
    old_task = SimpleNamespace(done=lambda: True)
    new_task = object()
    registry.task = old_task

    def create(coro):
        coro.close()
        return new_task

    monkeypatch.setattr(asyncio, "create_task", create)
    registry.local_connected()

    assert registry.task is new_task


def test_local_stop_cancels_pending_mdns_handlers(monkeypatch):
    monkeypatch.setattr(asyncio, "create_task", _REAL_CREATE_TASK)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    registry = XRegistryLocal(None)
    started = asyncio.Event()

    async def handler(*args):
        started.set()
        await asyncio.sleep(3600)

    registry._handler2 = handler

    async def run():
        registry._handler1(
            None,
            "_ewelink._tcp.local.",
            f"eWeLink_{DEVICEID}._ewelink._tcp.local.",
            object(),
        )
        await asyncio.sleep(0)
        assert started.is_set()
        assert registry._handler_tasks
        await registry.stop()

    loop.run_until_complete(run())
    loop.close()

    assert not registry._handler_tasks


def test_s40_plural_inching_ack_requires_matching_mdns_state():
    loop = asyncio.new_event_loop()
    registry: XRegistry = XRegistry(None)
    registry.local.online = True
    device = XDevice(
        deviceid=DEVICEID,
        extra={"uiid": 182},
        host="192.0.2.88:8081",
        local=True,
        params={
            "sledOnline": "off",
            "pulses": [
                {"outlet": 0, "pulse": "off", "switch": "off", "width": 500}
            ],
        },
    )
    registry.devices = {DEVICEID: device}
    calls = []

    async def local_send(dev, params=None, command=None, sequence=None, timeout=5):
        calls.append((command, params))
        return "ack" if command == "pulses" else "error"

    async def pull_mdns(dev, **kwargs):
        registry.local_update(
            {
                "deviceid": DEVICEID,
                "params": {
                    "pulses": [
                        {
                            "outlet": 0,
                            "pulse": "on",
                            "switch": "off",
                            "width": 500,
                        }
                    ]
                },
            }
        )
        return True

    registry.local.send = local_send
    registry.local.pull_mdns = pull_mdns

    ok = loop.run_until_complete(registry.set_inching(device, 0, pulse="on"))
    loop.close()

    assert ok == "online"
    assert calls == [
        (
            "pulses",
            {
                "pulses": [
                    {
                        "outlet": 0,
                        "pulse": "on",
                        "switch": "off",
                        "width": 500,
                    }
                ]
            },
        )
    ]
    assert DEVICEID not in registry._inching_pending


def test_plural_inching_rejects_unreported_outlet_and_fields():
    loop = asyncio.new_event_loop()
    registry: XRegistry = XRegistry(None)
    device = XDevice(
        deviceid=DEVICEID,
        extra={"uiid": 182},
        params={"pulses": [{"outlet": 0, "pulse": "off", "width": 500}]},
    )

    async def run():
        with pytest.raises(ValueError, match="outlet 1 was not reported"):
            await registry.set_inching(device, 1, pulse="on")
        with pytest.raises(ValueError, match="did not report fields: switch"):
            await registry.set_inching(device, 0, switch="on")
        with pytest.raises(ValueError, match="500-3600000"):
            await registry.set_inching(device, 0, width=501)

    loop.run_until_complete(run())
    loop.close()


def test_plural_inching_confirms_only_changed_field():
    loop = asyncio.new_event_loop()
    registry: XRegistry = XRegistry(None)
    registry.local.online = True
    device = XDevice(
        deviceid=DEVICEID,
        extra={"uiid": 182},
        host="192.0.2.88:8081",
        local=True,
        params={
            "pulses": [
                {
                    "outlet": 0,
                    "pulse": "off",
                    "switch": "off",
                    "width": 500,
                    "futureField": 7,
                }
            ]
        },
    )

    async def local_send(dev, params=None, command=None, sequence=None, timeout=5):
        return "ack"

    async def pull_mdns(dev, **kwargs):
        registry.local_update(
            {
                "deviceid": DEVICEID,
                "params": {"pulses": [{"outlet": 0, "pulse": "on"}]},
            }
        )
        return True

    registry.devices = {DEVICEID: device}
    registry.local.send = local_send
    registry.local.pull_mdns = pull_mdns

    ok = loop.run_until_complete(registry.set_inching(device, 0, pulse="on"))
    loop.close()

    assert ok == "online"
    assert DEVICEID not in registry._inching_pending


def test_switch_ack_returns_without_blocking_getstate():
    loop = asyncio.new_event_loop()
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    registry.local.online = True
    device = XDevice(
        deviceid=DEVICEID,
        extra={"uiid": 1},
        host="192.0.2.88:8081",
        local=True,
        params={"switches": [{"outlet": 0, "switch": "off"}]},
    )
    registry.devices = {DEVICEID: device}
    calls = []
    scheduled = []

    def track_confirmation(coro):
        scheduled.append(coro)
        coro.close()

    async def local_send(dev, params=None, command=None, sequence=None, timeout=5):
        if command is None and params:
            command = next(iter(params))
        calls.append((command, params, timeout))
        if command == "switches":
            return "ack"
        if command == "getState":
            registry.local_update(
                {
                    "deviceid": DEVICEID,
                    "params": {"power": "10.00"},
                }
            )
            return "online"
        return "error"

    registry.local.send = local_send
    registry._track_telemetry_task = track_confirmation

    ok = loop.run_until_complete(
        registry.send(device, {"switches": [{"outlet": 0, "switch": "on"}]})
    )
    loop.close()

    assert ok == "ack"
    assert calls == [
        ("switches", {"switches": [{"outlet": 0, "switch": "on"}]}, 1)
    ]
    assert len(scheduled) == 1
    assert device["params"]["switches"][0]["switch"] == "off"


def test_explicit_switch_confirmation_uses_getstate():
    loop = asyncio.new_event_loop()
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    registry.local.online = True
    device = XDevice(
        deviceid=DEVICEID,
        extra={"uiid": 1},
        host="192.0.2.88:8081",
        local=True,
        params={"switches": [{"outlet": 0, "switch": "off"}]},
    )
    registry.devices = {DEVICEID: device}

    async def local_send(dev, params=None, command=None, sequence=None, timeout=5):
        if command is None and params:
            command = next(iter(params))
        if command == "switches":
            return "ack"
        if command == "getState":
            registry.local_update(
                {
                    "deviceid": DEVICEID,
                    "params": {"switches": [{"outlet": 0, "switch": "on"}]},
                }
            )
            return "online"
        return "error"

    registry.local.send = local_send

    ok = loop.run_until_complete(
        registry.send(
            device,
            {"switches": [{"outlet": 0, "switch": "on"}]},
            confirm_lan={"switches": [{"outlet": 0, "switch": "on"}]},
        )
    )
    loop.close()

    assert ok == "online"
    assert device["params"]["switches"][0]["switch"] == "on"


def test_s40_switch_ack_schedules_background_mdns_confirmation(monkeypatch):
    monkeypatch.setattr(
        "custom_components.sonoff.core.ewelink.LOCAL_SWITCH_WAIT_SECONDS", 0
    )
    monkeypatch.setattr(
        "custom_components.sonoff.core.ewelink.LOCAL_TELEMETRY_MDNS_POLL_SECONDS", 0
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    registry.local.online = True
    device = XDevice(
        deviceid=DEVICEID,
        extra={"uiid": 182},
        host="192.0.2.88:8081",
        local=True,
        params={"switch": "off", "sledOnline": "on"},
    )
    registry.devices = {DEVICEID: device}
    calls = []
    scheduled = []

    def track_confirmation(coro):
        scheduled.append(coro)
        coro.close()

    async def local_send(dev, params=None, command=None, sequence=None, timeout=5):
        if command is None and params:
            command = next(iter(params))
        calls.append((command, params))
        if command == "switch":
            return "ack"
        return "error"

    registry.local.send = local_send
    registry._track_telemetry_task = track_confirmation

    ok = loop.run_until_complete(registry.send(device, {"switch": "on"}))
    loop.close()

    assert ok == "ack"
    assert ("getState", None) not in calls
    assert any(call[0] == "switch" for call in calls)
    assert device["params"]["switch"] == "off"
    assert len(scheduled) == 1
    assert device.get("localswitchnodata", 0) == 0


def test_s40_switch_confirmation_succeeds_when_mdns_reports_target_state(monkeypatch):
    monkeypatch.setattr(
        "custom_components.sonoff.core.ewelink.LOCAL_SWITCH_WAIT_SECONDS", 0
    )
    monkeypatch.setattr(
        "custom_components.sonoff.core.ewelink.LOCAL_TELEMETRY_MDNS_POLL_SECONDS", 0
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    registry.local.online = True
    device = XDevice(
        deviceid=DEVICEID,
        extra={"uiid": 182},
        host="192.0.2.88:8081",
        local=True,
        params={"switch": "off", "sledOnline": "on"},
    )
    registry.devices = {DEVICEID: device}
    calls = []

    async def local_send(dev, params=None, command=None, sequence=None, timeout=5):
        if command is None and params:
            command = next(iter(params))
        calls.append(command)
        if command == "switch":
            return "ack"
        return "error"

    async def pull_mdns(dev, **kwargs):
        registry.local_update(
            {"deviceid": DEVICEID, "params": {"switch": "on", "power": "10.0"}}
        )
        return True

    registry.local.send = local_send
    registry.local.pull_mdns = pull_mdns

    ok = loop.run_until_complete(
        registry.send(device, {"switch": "on"}, confirm_lan={"switch": "on"})
    )
    loop.close()

    assert ok == "online"
    assert "getState" not in calls
    assert device["params"]["switch"] == "on"
    assert device.get("localswitch_at", 0) > 0


def test_stop_cancels_tracked_telemetry_tasks(monkeypatch):
    monkeypatch.setattr(asyncio, "create_task", _REAL_CREATE_TASK)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(deviceid=DEVICEID, local=True)
    registry.devices = {DEVICEID: device}
    started = asyncio.Event()

    async def slow_telemetry(*args):
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise

    registry._await_sensor_telemetry = slow_telemetry

    async def run():
        registry._track_telemetry_task(registry._await_sensor_telemetry(device, 0))
        await asyncio.sleep(0)
        assert started.is_set()
        assert registry._local_telemetry_tasks
        await registry.stop()

    loop.run_until_complete(run())
    loop.close()

    assert not registry._local_telemetry_tasks


def test_stop_cancels_per_device_poll_tasks(monkeypatch):
    monkeypatch.setattr(asyncio, "create_task", _REAL_CREATE_TASK)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(deviceid=DEVICEID, local=True)
    registry.devices = {DEVICEID: device}
    started = asyncio.Event()

    async def slow_update(*args):
        started.set()
        await asyncio.sleep(3600)

    registry.update_local = slow_update

    async def run():
        registry._schedule_update_local(device, time.time())
        await asyncio.sleep(0)
        assert started.is_set()
        assert registry._local_poll_tasks
        await registry.stop()

    loop.run_until_complete(run())
    loop.close()

    assert not registry._local_poll_tasks


def test_local_send_reraises_cancelled_error():
    class Session:
        async def post(self, *args, **kwargs):
            raise asyncio.CancelledError()

    loop = asyncio.new_event_loop()
    registry = XRegistryLocal(Session())
    device = XDevice(deviceid=DEVICEID, host="192.0.2.88:8081")

    with pytest.raises(asyncio.CancelledError):
        loop.run_until_complete(registry.send(device, {"switch": "on"}))
    loop.close()


def test_active_mdns_pull_uses_home_assistant_shared_zeroconf():
    registry = XRegistryLocal(None)
    shared = object()
    registry.zeroconf = shared
    calls = []

    async def pull(zeroconf, device, timeout_ms):
        calls.append((zeroconf, device, timeout_ms))
        return True

    registry._pull_mdns_from = pull
    device = XDevice(deviceid=DEVICEID)

    assert asyncio.run(registry.pull_mdns(device, timeout_ms=750))
    assert calls == [(shared, device, 750)]


def test_bounded_mdns_pull_uses_direct_capture_after_shared_failure():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(deviceid=DEVICEID)
    calls = []

    async def shared(dev, **kwargs):
        calls.append(("shared", dev, kwargs))
        return False

    async def direct(dev, **kwargs):
        calls.append(("direct", dev, kwargs))
        return True

    registry.local.pull_mdns = shared
    registry.local.pull_mdns_direct = direct

    assert asyncio.run(registry._pull_mdns_bounded(device, timeout_ms=750))
    assert calls == [
        ("shared", device, {"timeout_ms": 750}),
        ("direct", device, {"timeout_ms": 750}),
    ]


def test_bounded_mdns_pull_skips_direct_capture_when_shared_succeeds():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(deviceid=DEVICEID)
    calls = []

    async def shared(dev, **kwargs):
        calls.append(("shared", dev, kwargs))
        return True

    async def direct(dev, **kwargs):
        calls.append(("direct", dev, kwargs))
        return True

    registry.local.pull_mdns = shared
    registry.local.pull_mdns_direct = direct

    assert asyncio.run(registry._pull_mdns_bounded(device, timeout_ms=750))
    assert calls == [("shared", device, {"timeout_ms": 750})]


def test_active_mdns_pull_evicts_cached_record_and_forces_query(monkeypatch):
    removed = []
    requests = []

    class Cache:
        @staticmethod
        def async_entries_with_name(name):
            return ["stale-record"]

        @staticmethod
        def async_remove_records(records):
            removed.extend(records)

    class Zeroconf:
        cache = Cache()

    class Info:
        properties = {b"data1": b'{"switch":"on"}'}
        addresses = []
        server = None
        port = 0

        def __init__(self, service_type, name):
            self.name = name

        async def async_request(self, zeroconf, timeout, question_type=None):
            requests.append((timeout, question_type))
            return True

    monkeypatch.setattr(
        "custom_components.sonoff.core.ewelink.local.AsyncServiceInfo", Info
    )
    registry = XRegistryLocal(None)
    updates = []
    registry.dispatcher_connect(SIGNAL_UPDATE, updates.append)
    device = XDevice(
        deviceid=DEVICEID,
        mdns_service=f"eWeLink_{DEVICEID}._ewelink._tcp.local.",
    )

    found = asyncio.run(registry._pull_mdns_from(Zeroconf(), device, 750))

    assert found
    assert removed == ["stale-record"]
    assert requests == [(750, DNSQuestionType.QU)]
    assert updates[0]["params"] == {"switch": "on"}


def test_getstate_protocol_rejection_reports_reachable_without_state():
    class Response:
        headers = {}

        async def json(self):
            return {"error": 400, "seq": 1}

    class Session:
        async def post(self, *args, **kwargs):
            return Response()

    registry = XRegistryLocal(Session())
    device = XDevice(deviceid=DEVICEID, host="192.0.2.88:8081", params={})

    result = asyncio.run(registry.send(device, command="getState"))

    assert result == "online_no_data"


def test_getstate_rejection_switches_future_polls_to_fresh_mdns():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    registry.local.online = True
    device = XDevice(
        deviceid=DEVICEID,
        extra={"uiid": 162},
        host="192.0.2.88:8081",
        local=True,
        localping=0,
        update_interval=5,
        params={"switches": [{"outlet": 0, "switch": "off"}]},
    )
    registry.devices = {DEVICEID: device}
    http_calls = []
    mdns_calls = []

    async def local_send(*args, **kwargs):
        http_calls.append((args, kwargs))
        return "online_no_data"

    async def pull_mdns(dev, **kwargs):
        mdns_calls.append(dev)
        registry.local_update(
            {
                "deviceid": DEVICEID,
                "params": {"switches": [{"outlet": 0, "switch": "on"}]},
            }
        )
        return True

    registry.local.send = local_send
    registry._pull_mdns_bounded = pull_mdns

    asyncio.run(registry.update_local(device, time.time()))
    assert device["localgetstate"] is False
    assert len(http_calls) == 1
    assert len(mdns_calls) == 1
    assert device["params"]["switches"][0]["switch"] == "on"

    device["localping"] = 0
    asyncio.run(registry.update_local(device, time.time()))
    assert len(http_calls) == 1
    assert len(mdns_calls) == 2


def test_local_ack_only_command_does_not_fake_switch_state():
    class Response:
        headers = {}

        async def json(self):
            return {"error": 0, "seq": 1}

    class Session:
        async def post(self, *args, **kwargs):
            return Response()

    loop = asyncio.new_event_loop()
    registry = XRegistryLocal(Session())
    device = XDevice(
        deviceid=DEVICEID,
        host="192.0.2.88:8081",
        localtype="plug",
        params={},
    )
    updates = []
    registry.dispatcher_connect(SIGNAL_UPDATE, updates.append)

    ok = loop.run_until_complete(
        registry.send(device, {"switches": [{"outlet": 0, "switch": "on"}]})
    )
    loop.close()

    assert ok == "ack"
    assert updates == []


def test_lan_only_keeps_devicekey_after_plaintext_local_update():
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    device = XDevice(
        deviceid=DEVICEID,
        devicekey="secret",
        params={"switches": [{"outlet": 0, "switch": "off"}]},
    )
    registry.devices = {DEVICEID: device}

    registry.local.dispatcher_send(
        SIGNAL_UPDATE,
        {
            "deviceid": DEVICEID,
            "seq": 1,
            "params": {"power": "10.00"},
        },
    )

    assert device["devicekey"] == "secret"


def test_parse_deviceid_from_service_name():
    assert (
        parse_deviceid_from_service_name("eWeLink_1000123abc._ewelink._tcp.local.")
        == "1000123abc"
    )
    assert (
        parse_deviceid_from_service_name("eWeLink-1000123abc._ewelink._tcp.local.")
        == "1000123abc"
    )
    assert (
        parse_deviceid_from_service_name("ewelink1000123abc._ewelink._tcp.local.")
        == "1000123abc"
    )
    assert (
        parse_deviceid_from_service_name("zbbridgeu-1000123abc._ewelink._tcp.local.")
        is None
    )


def test_issue_1160():
    payload = XRegistryLocal.decrypt_msg(
        {
            "iv": "MTA4MDc1MTQ5NzE5ODE2Ng==",
            "data": "D85ho6GLI5uFX2b1+vohUIb+Xt99f55wxsBsNhqpPQdQ/WNc3ZTlCi1UVFiFU5cnaCPjvXPG6pqfHqXdtCO2fA==",
        },
        "9b0810bc-557a-406c-8266-614767890531",
    )
    assert payload == {"switches": [{"outlet": 0, "switch": "off"}]}


def test_issue_1885():
    updates = []
    registry = XRegistryLocal(None)
    registry.dispatcher_connect(SIGNAL_UPDATE, updates.append)

    for encrypted in (False, "false"):
        registry._handler3(
            DEVICEID,
            "192.168.1.2:8081",
            {
                "id": DEVICEID,
                "type": "plug",
                "encrypt": encrypted,
                "data1": '{"temperature":"25.6","humidity":"54.8","co2":520}',
            },
        )

    assert updates[0]["params"] == updates[1]["params"] == {
        "temperature": "25.6",
        "humidity": "54.8",
        "co2": 520,
    }


def test_encrypt_uses_compact_json():
    with pytest.MonkeyPatch.context() as monkeypatch:
        captured = {}

        def dumps(data, **kwargs):
            captured.update(kwargs)
            return json.dumps(data, **kwargs)

        monkeypatch.setattr(
            "custom_components.sonoff.core.ewelink.local.json.dumps", dumps
        )
        encrypt({"data": {"switches": [{"outlet": 0, "switch": "off"}]}}, "abc")

    assert captured["separators"] == (",", ":")


def test_issue_1333():
    assert spec(XLightL1, base="light")


def test_issus_1313():
    assert spec(XFan, base="fan")


def test_cryptography():
    params = {"switch": "on"}
    key = "9b0810bc-557a-406c-8266-614767890531"

    payload = encrypt({"data": params}, key)
    assert payload["encrypt"] and payload["data"] and payload["iv"]

    raw = decrypt(payload, key)
    assert json.loads(raw) == params


def test_cloud_zigbee_offline():
    device: XDevice = {
        "online": False,
    }

    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    registry.devices = {DEVICEID: device}

    registry.cloud_update({"deviceid": DEVICEID, "params": {"subDevRssi": 127}})
    assert registry.devices[DEVICEID]["online"] is False

    registry.cloud_update({"deviceid": DEVICEID, "params": {"temperature": 0}})
    assert registry.devices[DEVICEID]["online"] is True
