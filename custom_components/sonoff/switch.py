from homeassistant.components.switch import SwitchEntity

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import XRegistry, SIGNAL_ADD_ENTITIES


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, SwitchEntity)])
    )


# noinspection PyAbstractClass
class XSwitch(XEntity, SwitchEntity):
    params = {"switch"}

    def set_state(self, params: dict):
        self._attr_is_on = params["switch"] == "on"

    async def async_turn_on(self):
        await self.ewelink.send(self.device, {"switch": "on"})

    async def async_turn_off(self):
        await self.ewelink.send(self.device, {"switch": "off"})


# noinspection PyAbstractClass
class XSwitches(XEntity, SwitchEntity):
    params = {"switches"}
    channel: int = 0

    def __init__(self, ewelink: XRegistry, device: dict):
        XEntity.__init__(self, ewelink, device)

        try:
            self._attr_name = \
                device["tags"]["ck_channel_name"][str(self.channel)]
        except KeyError:
            pass
        self._attr_unique_id = f"{device['deviceid']}_{self.channel + 1}"

    def set_state(self, params: dict):
        params = next(
            i for i in params["switches"] if i["outlet"] == self.channel
        )
        self._attr_is_on = params["switch"] == "on"

    async def async_turn_on(self):
        params = {"switches": [{"outlet": self.channel, "switch": "on"}]}
        await self.ewelink.send(self.device, params)

    async def async_turn_off(self):
        params = {"switches": [{"outlet": self.channel, "switch": "off"}]}
        await self.ewelink.send(self.device, params)


# noinspection PyAbstractClass
class XSwitchTH(XEntity, SwitchEntity):
    params = {"switch"}

    def set_state(self, params: dict):
        self._attr_is_on = params["switch"] == "on"

    async def async_turn_on(self):
        params = {"switch": "on", "mainSwitch": "on", "deviceType": "normal"}
        await self.ewelink.send(self.device, params)

    async def async_turn_off(self):
        params = {"switch": "off", "mainSwitch": "off", "deviceType": "normal"}
        await self.ewelink.send(self.device, params)


# noinspection PyAbstractClass
class XToggle(XEntity, SwitchEntity):
    def set_state(self, params: dict):
        self._attr_is_on = params[self.param] == "on"

    async def async_turn_on(self):
        await self.ewelink.send(self.device, {self.param: "on"})

    async def async_turn_off(self):
        await self.ewelink.send(self.device, {self.param: "off"})
