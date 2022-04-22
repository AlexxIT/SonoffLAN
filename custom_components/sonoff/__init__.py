import asyncio
import logging

import voluptuous as vol
from homeassistant.components import zeroconf
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import *
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .core import backward
from .core.const import *
from .core.ewelink import XRegistry, XRegistryCloud, XRegistryLocal
from .core.ewelink.camera import XCameras
from .core.ewelink.cloud import AuthError

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    "binary_sensor", "button", "cover", "fan", "light", "remote", "sensor",
    "switch"
]

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional(CONF_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_MODE, default='auto'): vol.In(CONF_MODES),
        vol.Optional(CONF_DEFAULT_CLASS): cv.string,
        # vol.Optional(CONF_DEBUG, default=False): cv.boolean,
        vol.Optional(CONF_RFBRIDGE): {
            cv.string: vol.Schema({
                vol.Optional(CONF_NAME): cv.string,
                vol.Optional(CONF_DEVICE_CLASS): cv.string,
                vol.Optional(CONF_TIMEOUT, default=120): cv.positive_int,
                vol.Optional(CONF_PAYLOAD_OFF): cv.string
            }, extra=vol.ALLOW_EXTRA),
        },
        vol.Optional(CONF_DEVICES): {
            cv.string: vol.Schema({
                vol.Optional(CONF_NAME): cv.string,
                vol.Optional(CONF_DEVICE_CLASS): vol.Any(str, list),
                vol.Optional(CONF_DEVICEKEY): cv.string,
            }, extra=vol.ALLOW_EXTRA),
        },
    }, extra=vol.ALLOW_EXTRA),
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    if not backward.hass_version_supported:
        return False

    # init storage for registries
    hass.data[DOMAIN] = {}

    # load optional global registry config
    XRegistry.config = config.get(DOMAIN)

    # cameras starts only on first command to it
    cameras = XCameras()

    async def send_command(call: ServiceCall):
        """Service for send raw command to device.
        :param call: `device` - required param, all other params - optional
        """
        data = dict(call.data)
        deviceid = str(data.pop('device'))

        if len(deviceid) == 10:
            registry = next(
                r for r in hass.data[DOMAIN].values() if deviceid in r.devices
            )
            device = registry.devices[deviceid]

            await registry.send(device, data)

        elif len(deviceid) == 6:
            await cameras.send(deviceid, data['cmd'])

        else:
            _LOGGER.error(f"Wrong deviceid {deviceid}")

    hass.services.async_register(DOMAIN, 'send_command', send_command)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """
    AUTO mode. If there is a login error to the cloud - it starts in LOCAL
    mode with devices list from cache. Trying to reconnect to the cloud.

    CLOUD mode. If there is a login error to the cloud - trying to reconnect to
    the cloud.

    LOCAL mode. If there is a login error to the cloud - it starts  with
    devices list from cache.
    """
    registry = hass.data[DOMAIN].get(entry.entry_id)
    if not registry:
        session = async_get_clientsession(hass)
        hass.data[DOMAIN][entry.entry_id] = registry = XRegistry(session)

    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)
    mode = entry.options.get(CONF_MODE, "auto")

    # retry only when can't login first time
    if entry.state == ConfigEntryState.SETUP_RETRY:
        assert mode in ("auto", "cloud")
        try:
            await registry.cloud.login(username, password)
        except Exception as e:
            _LOGGER.warning(f"Can't login: {e}. Mode: {mode}")
            raise ConfigEntryNotReady(e)
        if mode == "auto":
            registry.cloud.start()
        elif mode == "cloud":
            hass.async_create_task(internal_normal_setup(hass, entry))
        return True

    if registry.cloud.auth is None and username and password:
        try:
            await registry.cloud.login(username, password)
        except Exception as e:
            _LOGGER.warning(f"Can't login: {e}, mode: {mode}")
            if mode in ("auto", "local"):
                hass.async_create_task(internal_cache_setup(hass, entry))
            if mode in ("auto", "cloud"):
                if isinstance(e, AuthError):
                    raise ConfigEntryAuthFailed(e)
                raise ConfigEntryNotReady(e)
            assert mode == "local"
            return True

    hass.async_create_task(internal_normal_setup(hass, entry))
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    await asyncio.gather(*[
        hass.config_entries.async_forward_entry_unload(entry, domain)
        for domain in PLATFORMS
    ])

    registry: XRegistry = hass.data[DOMAIN][entry.entry_id]
    await registry.stop()

    return True


async def internal_normal_setup(hass: HomeAssistant, entry: ConfigEntry):
    registry: XRegistry = hass.data[DOMAIN][entry.entry_id]
    if registry.cloud.auth:
        devices = await registry.cloud.get_devices()
        _LOGGER.debug(f"Loaded {len(devices)} devices from cloud")

        store = Store(hass, 1, f"{DOMAIN}/{entry.data['username']}.json")
        await store.async_save(devices)
    else:
        devices = None

    await internal_cache_setup(hass, entry, devices)


async def internal_cache_setup(
        hass: HomeAssistant, entry: ConfigEntry, devices: list = None
):
    await asyncio.gather(*[
        hass.config_entries.async_forward_entry_setup(entry, domain)
        for domain in PLATFORMS
    ])

    if devices is None:
        store = Store(hass, 1, f"{DOMAIN}/{entry.data['username']}.json")
        devices = await store.async_load()
        if devices:
            _LOGGER.debug(f"Loaded {len(devices)} devices from cache")

    registry: XRegistry = hass.data[DOMAIN][entry.entry_id]
    if devices:
        registry.setup_devices(devices)

    mode = entry.options.get(CONF_MODE, "auto")
    if mode != "local" and registry.cloud.auth:
        registry.cloud.start()
    if mode != "cloud":
        zc = await zeroconf.async_get_instance(hass)
        registry.local.start(zc)

    if not entry.update_listeners:
        entry.add_update_listener(async_update_options)

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, registry.stop)
    )


async def async_remove_config_entry_device(
        hass: HomeAssistant, entry: ConfigEntry, device
) -> bool:
    return False
