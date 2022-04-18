from homeassistant.components.fan import FanEntity

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import XRegistry, SIGNAL_ADD_ENTITIES


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, FanEntity)])
    )


# noinspection PyAbstractClass
class XFan(XEntity, FanEntity):
    params = {"switches"}
    _attr_speed_count = 3

    def set_state(self, params: dict):
        s = {i["outlet"]: i["switch"] for i in params["switches"]}

        if s[1] == "off":
            self._attr_percentage = 0
        elif s[2] == "off" and s[3] == "off":
            self._attr_percentage = 33
        elif s[2] == "on" and s[3] == "off":
            self._attr_percentage = 67
        elif s[2] == "off" and s[3] == "on":
            self._attr_percentage = 100

    async def async_set_percentage(self, percentage: int):
        if percentage > 67:
            param = {1: "on", 2: "off", 3: "on"}
        elif percentage > 33:
            param = {1: "on", 2: "on", 3: "off"}
        elif percentage > 0:
            param = {1: "on", 2: "off", 3: "off"}
        else:
            param = {1: "off"}
        param = [{"outlet": k, "switch": v} for k, v in param.items()]
        await self.ewelink.send(self.device, {"switches": param})

    async def async_turn_on(self, percentage=None, **kwargs):
        await self.async_set_percentage(percentage)

    async def async_turn_off(self):
        await self.async_set_percentage(0)


# noinspection PyAbstractClass
class XDiffuserFan(XFan):
    params = {"state", "switch"}
    _attr_speed_count = 2

    def set_state(self, params: dict):
        if params["switch"] == "off":
            self._attr_percentage = 0
        elif params["state"] == 1:
            self._attr_percentage = 50
        elif params["state"] == 2:
            self._attr_percentage = 100

    async def async_set_percentage(self, percentage: int):
        if percentage > 50:
            param = {"switch": "on", "state": 2}
        elif percentage > 0:
            param = {"switch": "on", "state": 1}
        else:
            param = {"switch": "off"}
        await self.ewelink.send(self.device, param)
