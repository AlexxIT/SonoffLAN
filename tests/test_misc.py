import asyncio

from custom_components.sonoff.core.ewelink import XRegistry, XDevice

from . import save_to


def test_bulk():
    registry_send = []

    device = XDevice()
    loop = asyncio.get_event_loop()
    # noinspection PyTypeChecker
    registry: XRegistry = XRegistry(None)
    registry.send = save_to(registry_send)

    loop.create_task(registry.send_bulk(device, {
        "switches": [{"outlet": 1, "switch": "off"}]
    }))
    loop.create_task(registry.send_bulk(device, {
        "switches": [{"outlet": 2, "switch": "off"}]
    }))
    loop.run_until_complete(asyncio.sleep(0))
    assert device["params_bulk"]["switches"] == [
        {"outlet": 1, "switch": "off"}, {"outlet": 2, "switch": "off"}
    ]

    loop.create_task(registry.send_bulk(device, {
        "switches": [{"outlet": 2, "switch": "off"}]
    }))
    loop.create_task(registry.send_bulk(device, {
        "switches": [{"outlet": 1, "switch": "on"}]
    }))

    loop.run_until_complete(asyncio.sleep(.1))
    assert registry_send[0][1] == {"switches": [
        {"outlet": 1, "switch": "on"}, {"outlet": 2, "switch": "off"}
    ]}
