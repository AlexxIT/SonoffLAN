import asyncio
from types import SimpleNamespace

from custom_components.sonoff.core.const import DOMAIN
from custom_components.sonoff.core.ewelink import XRegistry
from custom_components.sonoff.diagnostics import async_get_config_entry_diagnostics


class FakeHass:
    def __init__(self):
        self.data = {}

    async def async_add_executor_job(self, func, *args):
        return func(*args)


def test_diagnostics_does_not_mutate_config():
    entry = SimpleNamespace(
        entry_id="entry1",
        options={},
    )

    # noinspection PyTypeChecker
    registry = XRegistry(None)
    registry.devices = {}
    registry.cloud.auth = None

    hass = FakeHass()
    hass.data[DOMAIN] = {
        entry.entry_id: registry,
    }

    original_config = XRegistry.config

    try:
        XRegistry.config = {
            "username": "user@example.com",
            "password": "secret-password",
            "devices": {
                "1000123456": {
                    "devicekey": "real-device-key",
                }
            },
        }

        result = asyncio.run(async_get_config_entry_diagnostics(hass, entry))

        assert result["config"]["username"] == "***"
        assert result["config"]["password"] == "***"
        assert result["config"]["devices"]["1000123456"]["devicekey"] == "***"

        assert XRegistry.config["username"] == "user@example.com"
        assert XRegistry.config["password"] == "secret-password"
        assert (
                XRegistry.config["devices"]["1000123456"]["devicekey"]
                == "real-device-key"
        )
    finally:
        XRegistry.config = original_config