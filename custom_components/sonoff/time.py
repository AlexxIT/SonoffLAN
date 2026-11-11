from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.helpers.entity import EntityCategory

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import SIGNAL_ADD_ENTITIES, XRegistry
from .switch import _auto_upgrade, _send_auto_upgrade

PARALLEL_UPDATES = 0  # fix entity_platform parallel_updates Semaphore


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, TimeEntity)]),
    )


# noinspection PyAbstractClass
class XAutoUpgradeStart(XEntity, TimeEntity):
    """MINI-RBS (uiid 258) - start of the firmware auto update window.

    Writing works only via Cloud: requires `auto` mode (does nothing in `local`).
    """

    params = {"autoUpgrade"}
    uid = "auto_upgrade_start"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:clock-start"
    _index = 0

    def set_state(self, params: dict):
        rng = params["autoUpgrade"].get("range") or []
        try:
            h, m = rng[self._index].split(":")
            self._attr_native_value = time(int(h), int(m))
        except (IndexError, ValueError, AttributeError):
            self._attr_native_value = None

    async def async_set_value(self, value: time):
        au = _auto_upgrade(self.device)
        au["range"][self._index] = value.strftime("%H:%M")
        await _send_auto_upgrade(self, au)
        self._attr_native_value = time(value.hour, value.minute)
        self._async_write_ha_state()


# noinspection PyAbstractClass
class XAutoUpgradeEnd(XAutoUpgradeStart):
    uid = "auto_upgrade_end"
    _attr_icon = "mdi:clock-end"
    _index = 1
