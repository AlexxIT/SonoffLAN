import asyncio

from custom_components.sonoff.core.ewelink import XDevice, XRegistry, XRegistryLocal
from . import save_to


def test_bulk():
    registry_send = []

    device = XDevice()
    loop = asyncio.get_event_loop()
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


def test_issue_1160():
    payload = XRegistryLocal.decrypt_msg(
        {
            "iv": "MTA4MDc1MTQ5NzE5ODE2Ng==",
            "data": "D85ho6GLI5uFX2b1+vohUIb+Xt99f55wxsBsNhqpPQdQ/WNc3ZTlCi1UVFiFU5cnaCPjvXPG6pqfHqXdtCO2fA==",
        },
        "9b0810bc-557a-406c-8266-614767890531",
    )
    assert payload == {"switches": [{"outlet": 0, "switch": "off"}]}
