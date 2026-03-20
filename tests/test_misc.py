import asyncio
import json

from custom_components.sonoff.core.devices import spec
from custom_components.sonoff.core.ewelink import XDevice, XRegistry, XRegistryLocal
from custom_components.sonoff.core.ewelink.local import decrypt, encrypt
from custom_components.sonoff.fan import XFan
from custom_components.sonoff.light import XLightL1
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
