import asyncio
import threading
from typing import List

from homeassistant.components.alarm_control_panel import AlarmControlPanelEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.button import ButtonEntity
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.cover import CoverEntity
from homeassistant.components.fan import FanEntity
from homeassistant.components.light import LightEntity
from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.number import NumberEntity
from homeassistant.components.remote import RemoteEntity
from homeassistant.components.select import SelectEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import HomeAssistant  # fix circular import
from homeassistant.helpers.entity import Entity

from custom_components.sonoff.core.entity import XEntity
from custom_components.sonoff.core.ewelink import SIGNAL_ADD_ENTITIES, XRegistry

DEVICEID = "1000123abc"

# Mirror EntityPlatform: platform domain prepended to suggested_object_id when
# building entity_id. Tests bypass EntityPlatform, so resolve manually.
PLATFORM_DOMAINS = (
    (SensorEntity, "sensor"),
    (SwitchEntity, "switch"),
    (BinarySensorEntity, "binary_sensor"),
    (ButtonEntity, "button"),
    (ClimateEntity, "climate"),
    (CoverEntity, "cover"),
    (FanEntity, "fan"),
    (LightEntity, "light"),
    (MediaPlayerEntity, "media_player"),
    (NumberEntity, "number"),
    (SelectEntity, "select"),
    (RemoteEntity, "remote"),
    (AlarmControlPanelEntity, "alarm_control_panel"),
)


def _resolve_entity_id(entity: Entity) -> None:
    if entity.entity_id:
        return
    if not entity.unique_id:
        return
    object_id = entity.suggested_object_id or entity.unique_id
    # Walk MRO directly instead of isinstance so ABC's subclass cache stays
    # untouched. set_default_class() rewrites XSwitch.__bases__ in
    # test_default_class; isinstance here would freeze the cached result and
    # break that test.
    mro = type(entity).__mro__
    for cls, domain in PLATFORM_DOMAINS:
        if cls in mro:
            entity.entity_id = f"{domain}.{object_id}"
            return


class DummyRegistry(XRegistry):
    def __init__(self):
        # noinspection PyTypeChecker
        super().__init__(None)
        self.send_args = None

    async def send(self, *args, **kwargs):
        self.send_args = args

    async def send_cloud(self, *args, **kwargs):
        self.send_args = args

    def call(self, coro):
        loop = asyncio.new_event_loop()
        loop.run_until_complete(coro)
        loop.close()
        return self.send_args


# noinspection PyTypeChecker
def init(device: dict, config: dict = None) -> (XRegistry, List[XEntity]):
    devices = [device] if isinstance(device, dict) else device
    for device in devices:
        device.setdefault("name", "Device1")
        device.setdefault("deviceid", DEVICEID)
        device.setdefault("online", True)
        device.setdefault("extra", {"uiid": 0})
        params = device.setdefault("params", {})
        params.setdefault("staMac", "FF:FF:FF:FF:FF:FF")

    asyncio.create_task = lambda coro: coro.close()
    asyncio.get_running_loop = lambda: type("", (), {"_thread_id": threading.get_ident()})

    entities = []

    reg = DummyRegistry()
    reg.cloud.online = True
    reg.config = config
    reg.dispatcher_connect(SIGNAL_ADD_ENTITIES, lambda x: entities.extend(x))
    entities += reg.setup_devices(devices)

    try:
        hass = HomeAssistant("")  # new Hass
    except TypeError:
        hass = HomeAssistant()  # old Hass

    hass.data["integrations"] = {}

    for entity in entities:
        if not isinstance(entity, Entity):
            continue
        _resolve_entity_id(entity)
        entity.hass = hass
        entity.async_write_ha_state()

    return reg, entities


def save_to(store: list):
    return lambda *args, **kwargs: store.append({**dict(enumerate(args)), **kwargs})
