from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .core import xutils
from .core.const import DOMAIN, PRIVATE_KEYS
from .core.ewelink import XRegistry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry):
    try:
        if XRegistry.config:
            config = XRegistry.config.copy()
            for k in (CONF_USERNAME, CONF_PASSWORD):
                if config.get(k):
                    config[k] = "***"
            if config.get("devices"):
                for device in config["devices"].values():
                    if device.get("devicekey"):
                        device["devicekey"] = "***"
        else:
            config = None
    except Exception as e:
        config = repr(e)

    options = {k: len(v) if k == "homes" else v for k, v in entry.options.items()}

    registry: XRegistry = hass.data[DOMAIN][entry.entry_id]
    try:
        devices = {
            did: (
                {
                    "uiid": device["extra"]["uiid"],
                    "params": {
                        k: "***" if k in PRIVATE_KEYS else v
                        for k, v in device["params"].items()
                    },
                    "model": device.get("productModel"),
                    "online": device.get("online"),
                    "local": device.get("local"),
                    "localtype": device.get("localtype"),
                    "host": device.get("host"),
                }
                if "params" in device
                else {
                    "localtype": device.get("localtype"),
                }
            )
            for did, device in registry.devices.items()
        }
    except Exception as e:
        devices = repr(e)

    return {
        "version": await hass.async_add_executor_job(xutils.source_hash),
        "cloud_auth": registry.cloud.auth is not None,
        "config": config,
        "options": options,
        "errors": xutils.system_log_records(hass, DOMAIN),
        "devices": devices,
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
):
    did = next(i[1] for i in device.identifiers if i[0] == DOMAIN)
    info = await async_get_config_entry_diagnostics(hass, entry)
    info["device"] = info.pop("devices").get(did, {})
    info["device"]["deviceid"] = did
    return info
