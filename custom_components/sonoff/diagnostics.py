"""Diagnostics with explicit redaction for data that may be shared publicly."""

from copy import deepcopy
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .core import xutils
from .core.const import DOMAIN, PRIVATE_KEYS
from .core.ewelink import XRegistry

# Diagnostics can be attached to public issues. Do not expose credentials,
# network addresses, stable device identifiers or a user's device names.
DIAGNOSTIC_REDACT_KEYS = frozenset(
    {
        CONF_USERNAME,
        CONF_PASSWORD,
        "appid",
        "appsecret",
        "apikey",
        "uid",
        "deviceid",
        "parentid",
        "devicekey",
        "host",
        "ip",
        "mac",
        "name",
        "sequence",
        "timestamp",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
    }
).union(key.casefold() for key in PRIVATE_KEYS)


def redact_diagnostics_data(value: Any, secret_values: tuple[str, ...] = ()) -> Any:
    """Return a recursively redacted diagnostics value.

    ``secret_values`` is used for formatted log messages, where the sensitive
    item is part of a string rather than the name of a mapping key.
    """
    if isinstance(value, dict):
        return {
            key: "***"
            if str(key).casefold() in DIAGNOSTIC_REDACT_KEYS
            else redact_diagnostics_data(item, secret_values)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_diagnostics_data(item, secret_values) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_diagnostics_data(item, secret_values) for item in value)
    if isinstance(value, str):
        for secret in secret_values:
            if secret:
                value = value.replace(secret, "***")
    return value


def diagnostic_secret_values(registry: XRegistry) -> tuple[str, ...]:
    """Collect identifiers and names only for redacting formatted log strings."""
    values = set()
    for device in registry.devices.values():
        for key in ("deviceid", "apikey", "devicekey", "host", "name"):
            if value := device.get(key):
                values.add(str(value))
        if parent := device.get("parent"):
            for key in ("deviceid", "apikey", "devicekey", "host", "name"):
                if value := parent.get(key):
                    values.add(str(value))

    if config := XRegistry.config:
        for key in ("appid", "appsecret", CONF_USERNAME, CONF_PASSWORD):
            if value := config.get(key):
                values.add(str(value))

    return tuple(sorted(values, key=len, reverse=True))


def device_diagnostics(device: dict, secret_values: tuple[str, ...]) -> dict:
    """Return only useful, non-identifying device diagnostics."""
    if "params" not in device:
        return {"localtype": device.get("localtype")}

    data = {
        "uiid": device["extra"]["uiid"],
        "params": device["params"],
        "model": device.get("productModel"),
        "online": device.get("online"),
        "local": device.get("local"),
        "localtype": device.get("localtype"),
        "last_cloud_command": device.get("last_cloud_command"),
        "last_cloud_error": device.get("last_cloud_error"),
    }
    return redact_diagnostics_data(data, secret_values)


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry):
    """Return redacted diagnostics for a config entry."""
    registry: XRegistry = hass.data[DOMAIN][entry.entry_id]
    secret_values = diagnostic_secret_values(registry)

    try:
        config = deepcopy(XRegistry.config) if XRegistry.config else None
        if config and config.get("devices"):
            # Device IDs are mapping keys in this structure, so replace it with
            # a count before applying the normal key/value redactor.
            config["devices"] = {"count": len(config["devices"])}
        config = redact_diagnostics_data(config, secret_values)
    except Exception as err:
        config = repr(err)

    options = {key: len(value) if key == "homes" else value for key, value in entry.options.items()}

    try:
        devices = [
            device_diagnostics(device, secret_values)
            for device in registry.devices.values()
        ]
    except Exception as err:
        devices = repr(err)

    return {
        "version": await hass.async_add_executor_job(xutils.source_hash),
        "cloud_auth": registry.cloud.auth is not None,
        "config": config,
        "options": options,
        "errors": redact_diagnostics_data(
            xutils.system_log_records(hass, DOMAIN), secret_values
        ),
        "cloud_command_errors": redact_diagnostics_data(
            list(registry.cloud_errors), secret_values
        ),
        "devices": devices,
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
):
    """Return redacted diagnostics for one device without returning its ID."""
    did = next(identifier[1] for identifier in device.identifiers if identifier[0] == DOMAIN)
    info = await async_get_config_entry_diagnostics(hass, entry)
    registry: XRegistry = hass.data[DOMAIN][entry.entry_id]
    info.pop("devices")
    info["device"] = device_diagnostics(
        registry.devices.get(did, {}), diagnostic_secret_values(registry)
    )
    return info
