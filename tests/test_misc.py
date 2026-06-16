import asyncio
import json

from custom_components.sonoff.core.devices import spec
from custom_components.sonoff.core.ewelink import (
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
from . import DEVICEID, save_to


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


def test_send_returns_fallback_result():
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

    assert ok == "online"
    assert [call[0] for call in calls] == ["local", "cloud"]


def test_local_update_flattens_config_params():
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

    assert device["params"] == {"hundredDaysKwhData": "000009"}
    assert updates == [{"hundredDaysKwhData": "000009"}]


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


def test_issue_1160():
    payload = XRegistryLocal.decrypt_msg(
        {
            "iv": "MTA4MDc1MTQ5NzE5ODE2Ng==",
            "data": "D85ho6GLI5uFX2b1+vohUIb+Xt99f55wxsBsNhqpPQdQ/WNc3ZTlCi1UVFiFU5cnaCPjvXPG6pqfHqXdtCO2fA==",
        },
        "9b0810bc-557a-406c-8266-614767890531",
    )
    assert payload == {"switches": [{"outlet": 0, "switch": "off"}]}


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


def test_parse_deviceid_from_service_name():
    assert (
        parse_deviceid_from_service_name("eWeLink_100175e200._ewelink._tcp.local.")
        == "100175e200"
    )
    assert (
        parse_deviceid_from_service_name("eWeLink-100175e200._ewelink._tcp.local.")
        == "100175e200"
    )
    assert (
        parse_deviceid_from_service_name("ewelink100175e200._ewelink._tcp.local.")
        == "100175e200"
    )
    assert (
        parse_deviceid_from_service_name("zbbridgeu-100175e200._ewelink._tcp.local.")
        is None
    )


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
