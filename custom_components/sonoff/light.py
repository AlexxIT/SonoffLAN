from homeassistant.components.light import LightEntity

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import XRegistry, SIGNAL_ADD_ENTITIES


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, LightEntity)])
    )


# noinspection PyAbstractClass
class XFanLight(XEntity, LightEntity):
    params = {"switches"}

    def set_state(self, params: dict):
        params = next(i for i in params["switches"] if i["outlet"] == 0)
        self._attr_is_on = params["switch"] == "on"

    async def async_turn_on(self, **kwargs):
        params = {"switches": [{"outlet": 0, "switch": "on"}]}
        await self.ewelink.send(self.device, params)

    async def async_turn_off(self):
        params = {"switches": [{"outlet": 0, "switch": "off"}]}
        await self.ewelink.send(self.device, params)
