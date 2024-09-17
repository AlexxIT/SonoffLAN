import asyncio
import logging

import voluptuous as vol
from homeassistant.components import zeroconf
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_DEVICES,
    CONF_MODE,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PAYLOAD_OFF,
    CONF_SENSORS,
    CONF_TIMEOUT,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
    MAJOR_VERSION,
    MINOR_VERSION,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import async_get as device_registry
from homeassistant.helpers.storage import Store

from . import system_health
from .core import devices as core_devices
from .core.const import (
    CONF_APPID,
    CONF_APPSECRET,
    CONF_COUNTRY_CODE,
    CONF_DEFAULT_CLASS,
    CONF_DEVICEKEY,
    CONF_RFBRIDGE,
    DOMAIN,
)
from .core.ewelink import SIGNAL_ADD_ENTITIES, SIGNAL_CONNECTED, XRegistry
from .core.ewelink.camera import XCameras
from .core.ewelink.cloud import APP, AuthError

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    "binary_sensor",
    "button",
    "climate",
    "cover",
    "fan",
    "light",
    "remote",
    "sensor",
    "switch",
    "number",
]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_APPID): cv.string,
                vol.Optional(CONF_APPSECRET): cv.string,
                vol.Optional(CONF_USERNAME): cv.string,
                vol.Optional(CONF_PASSWORD): cv.string,
                vol.Optional(CONF_DEFAULT_CLASS): cv.string,
                vol.Optional(CONF_SENSORS): cv.ensure_list,
                vol.Optional(CONF_RFBRIDGE): {
                    cv.string: vol.Schema(
                        {
                            vol.Optional(CONF_NAME): cv.string,
                            vol.Optional(CONF_DEVICE_CLASS): cv.string,
                            vol.Optional(CONF_TIMEOUT, default=120): cv.positive_int,
                            vol.Optional(CONF_PAYLOAD_OFF): cv.string,
                        },
                        extra=vol.ALLOW_EXTRA,
                    ),
                },
                vol.Optional(CONF_DEVICES): {
                    cv.string: vol.Schema(
                        {
                            vol.Optional(CONF_NAME): cv.string,
                            vol.Optional(CONF_DEVICE_CLASS): vol.Any(str, list),
                            vol.Optional(CONF_DEVICEKEY): cv.string,
                        },
                        extra=vol.ALLOW_EXTRA,
                    ),
                },
            },
            extra=vol.ALLOW_EXTRA,
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

UNIQUE_DEVICES = {}


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    if (MAJOR_VERSION, MINOR_VERSION) < (2023, 2):
        raise Exception("unsupported hass version")

    # init storage for registries
    hass.data[DOMAIN] = {}

    # load optional global registry config
    if DOMAIN in config:
        XRegistry.config = conf = config[DOMAIN]
        if CONF_APPID in conf and CONF_APPSECRET in conf:
            APP[0] = (conf[CONF_APPID], conf[CONF_APPSECRET])
        if CONF_DEFAULT_CLASS in conf:
            core_devices.set_default_class(conf.get(CONF_DEFAULT_CLASS))
        if CONF_SENSORS in conf:
            core_devices.get_spec = core_devices.get_spec_wrapper(
                core_devices.get_spec, conf.get(CONF_SENSORS)
            )

    # cameras starts only on first command to it
    cameras = XCameras()

    try:
        # import ewelink account from YAML (first time)
        data = {
            CONF_USERNAME: XRegistry.config[CONF_USERNAME],
            CONF_PASSWORD: XRegistry.config[CONF_PASSWORD],
        }
        if not hass.config_entries.async_entries(DOMAIN):
            coro = hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=data
            )
            hass.async_create_task(coro)
    except Exception:
        pass

    async def send_command(call: ServiceCall):
        """Service for send raw command to device.
        :param call: `device` - required param, all other params - optional
        """
        params = dict(call.data)
        deviceid = str(params.pop("device"))

        if len(deviceid) == 10:
            registry: XRegistry = next(
                r for r in hass.data[DOMAIN].values() if deviceid in r.devices
            )
            device = registry.devices[deviceid]

            # for debugging purposes
            if v := params.get("set_device"):
                device.update(v)
                return

            params_lan = params.pop("params_lan", None)
            command_lan = params.pop("command_lan", None)

            await registry.send(device, params, params_lan, command_lan)

        elif len(deviceid) == 6:
            await cameras.send(deviceid, params["cmd"])

        else:
            _LOGGER.error(f"Wrong deviceid {deviceid}")

    hass.services.async_register(DOMAIN, "send_command", send_command)

    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    if config_entry.options.get("debug") and not _LOGGER.handlers:
        await system_health.setup_debug(hass, _LOGGER)

    registry: XRegistry = hass.data[DOMAIN].get(config_entry.entry_id)
    if not registry:
        session = async_get_clientsession(hass)
        hass.data[DOMAIN][config_entry.entry_id] = registry = XRegistry(session)

    mode = config_entry.options.get(CONF_MODE, "auto")
    data = config_entry.data

    # if has cloud password and not auth
    if not registry.cloud.auth and data.get(CONF_PASSWORD):
        try:
            await registry.cloud.login(**data)
            # store country_code for future requests optimisation
            if not data.get(CONF_COUNTRY_CODE):
                hass.config_entries.async_update_entry(
                    config_entry,
                    data={**data, CONF_COUNTRY_CODE: registry.cloud.country_code},
                )
        except Exception as e:
            _LOGGER.warning(f"Can't login in {mode} mode: {repr(e)}")
            if mode == "cloud":
                # can't continue in cloud mode
                if isinstance(e, AuthError):
                    raise ConfigEntryAuthFailed(e)
                raise ConfigEntryNotReady(e)

    if not config_entry.update_listeners:
        config_entry.add_update_listener(async_update_options)

    config_entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, registry.stop)
    )

    # important to run before registry.setup_devices (for remote childs)
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    devices: list[dict] | None = None
    store = Store(hass, 1, f"{DOMAIN}/{config_entry.data['username']}.json")

    # if auth OK - load devices from cloud
    if registry.cloud.auth:
        try:
            homes = config_entry.options.get("homes")
            devices = await registry.cloud.get_devices(homes)
            _LOGGER.debug(f"{len(devices)} devices loaded from Cloud")

            # store devices to cache
            await store.async_save(devices)

        except Exception as e:
            _LOGGER.warning("Can't load devices", exc_info=e)

    if not devices:
        if devices := await store.async_load():
            _LOGGER.debug(f"{len(devices)} devices loaded from Cache")

    if devices:
        # we need to setup_devices before local.start
        devices = internal_unique_devices(config_entry.entry_id, devices)
        entities = registry.setup_devices(devices)
    else:
        entities = None

    if mode in ("auto", "cloud") and config_entry.data.get(CONF_PASSWORD):
        registry.cloud.start(**config_entry.data)

    if mode in ("auto", "local"):
        registry.local.start(await zeroconf.async_get_instance(hass))

    _LOGGER.debug(mode.upper() + " mode start")

    # at this moment we hold EVENT_HOMEASSISTANT_START event
    if registry.cloud.task:
        # we get cloud connected signal even with a cloud error, so we won't
        # hold Hass start event forever
        await registry.cloud.dispatcher_wait(SIGNAL_CONNECTED)
    elif registry.local.online:
        # we hope that most of local devices will be discovered in 3 seconds
        await asyncio.sleep(3)

    # 1. We need add_entities after cloud or local init, so they won't be
    #    unavailable at init state
    # 2. We need add_entities before Hass start event, so Hass won't push
    #    unavailable state with restored=True attribute to history
    if entities:
        _LOGGER.debug(f"Add {len(entities)} entities")
        registry.dispatcher_send(SIGNAL_ADD_ENTITIES, entities)

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    registry: XRegistry = hass.data[DOMAIN][entry.entry_id]
    await registry.stop()

    return ok


def internal_unique_devices(uid: str, devices: list) -> list:
    """For support multiple integrations - bind each device to one integraion.
    To avoid duplicates.
    """
    return [
        device
        for device in devices
        if UNIQUE_DEVICES.setdefault(device["deviceid"], uid) == uid
    ]


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device
) -> bool:
    device_registry(hass).async_remove_device(device.id)
    return True
