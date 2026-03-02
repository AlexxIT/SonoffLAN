import asyncio

from custom_components.sonoff.core.devices import spec
from custom_components.sonoff.core.ewelink import XDevice, XRegistry, XRegistryLocal
from custom_components.sonoff.fan import XFan
from custom_components.sonoff.light import XLightL1
from . import save_to


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


def test_ui_active_refresh_task_dedup():
    class DummyTask:
        def __init__(self, coro):
            self._done = False
            self._callbacks = []
            # avoid "coroutine was never awaited" warnings in tests
            coro.close()

        def done(self):
            return self._done

        def add_done_callback(self, cb):
            self._callbacks.append(cb)

        def complete(self):
            self._done = True
            for cb in list(self._callbacks):
                cb(self)

    tasks = []

    async def dummy_send(*args, **kwargs):
        return None

    def fake_create_task(coro):
        task = DummyTask(coro)
        tasks.append(task)
        return task

    # noinspection PyTypeChecker
    registry = XRegistry(None)
    registry.cloud.online = True
    registry.cloud.send = dummy_send

    device = XDevice(
        deviceid="sonoff_100000abc1", online=True, extra={"uiid": 181}, params={}
    )

    original_create_task = asyncio.create_task
    asyncio.create_task = fake_create_task
    try:
        registry.update_device(device)
        assert len(tasks) == 1
        assert device["ui_active_task"] is tasks[0]

        # second periodic refresh for same device is skipped while task pending
        registry.update_device(device)
        assert len(tasks) == 1

        # once task completes, next refresh can be scheduled again
        tasks[0].complete()
        assert device["ui_active_task"].done()

        registry.update_device(device)
        assert len(tasks) == 2
        assert device["ui_active_task"] is tasks[1]
    finally:
        asyncio.create_task = original_create_task
