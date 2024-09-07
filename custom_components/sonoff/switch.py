from homeassistant.components.switch import SwitchEntity

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import SIGNAL_ADD_ENTITIES, XRegistry

PARALLEL_UPDATES = 0  # fix entity_platform parallel_updates Semaphore


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, SwitchEntity)]),
    )


# noinspection PyAbstractClass
class XSwitch(XEntity, SwitchEntity):
    params = {"switch"}

    def set_state(self, params: dict):
        self._attr_is_on = params["switch"] == "on"

    async def async_turn_on(self, *args, **kwargs):
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
            self._attr_name = device["tags"]["ck_channel_name"][str(self.channel)]
        except KeyError:
            pass
        # backward compatibility
        self._attr_unique_id = f"{device['deviceid']}_{self.channel + 1}"

    def set_state(self, params: dict):
        try:
            params = next(i for i in params["switches"] if i["outlet"] == self.channel)
            self._attr_is_on = params["switch"] == "on"
        except StopIteration:
            pass

    async def async_turn_on(self, *args, **kwargs):
        params = {"switches": [{"outlet": self.channel, "switch": "on"}]}
        await self.ewelink.send_bulk(self.device, params)

    async def async_turn_off(self):
        params = {"switches": [{"outlet": self.channel, "switch": "off"}]}
        await self.ewelink.send_bulk(self.device, params)


# noinspection PyAbstractClass
class XSwitchTH(XSwitch):
    async def async_turn_on(self):
        params = {"switch": "on", "mainSwitch": "on", "deviceType": "normal"}
        await self.ewelink.send(self.device, params)

    async def async_turn_off(self):
        params = {"switch": "off", "mainSwitch": "off", "deviceType": "normal"}
        await self.ewelink.send(self.device, params)


# noinspection PyAbstractClass
class XSwitchPOWR3(XSwitches):
    async def async_turn_on(self):
        params = {"switches": [{"outlet": 0, "switch": "on"}], "operSide": 1}
        await self.ewelink.send(self.device, params)

    async def async_turn_off(self):
        params = {"switches": [{"outlet": 0, "switch": "off"}], "operSide": 1}
        await self.ewelink.send(self.device, params)


# noinspection PyAbstractClass
class XZigbeeSwitches(XSwitches):
    async def async_turn_on(self, **kwargs):
        # zigbee switch should send all channels at once
        # https://github.com/AlexxIT/SonoffLAN/issues/714
        switches = [
            {"outlet": self.channel, "switch": "on"}
            if switch["outlet"] == self.channel
            else switch
            for switch in self.device["params"]["switches"]
        ]
        await self.ewelink.send(self.device, {"switches": switches})

    async def async_turn_off(self):
        switches = [
            {"outlet": self.channel, "switch": "off"}
            if switch["outlet"] == self.channel
            else switch
            for switch in self.device["params"]["switches"]
        ]
        await self.ewelink.send(self.device, {"switches": switches})


# noinspection PyAbstractClass
class XToggle(XEntity, SwitchEntity):
    def set_state(self, params: dict):
        self.device["params"][self.param] = params[self.param]
        self._attr_is_on = params[self.param] == "on"

    async def async_turn_on(self):
        await self.ewelink.send(self.device, {self.param: "on"})

    async def async_turn_off(self):
        await self.ewelink.send(self.device, {self.param: "off"})


# noinspection PyAbstractClass
class XDetach(XEntity, SwitchEntity):
    param = "relaySeparation"
    uid = "detach"

    _attr_entity_registry_enabled_default = False

    def set_state(self, params: dict):
        self._attr_is_on = params["relaySeparation"] == 1

    async def async_turn_on(self, **kwargs):
        await self.ewelink.send_cloud(self.device, {"relaySeparation": 1})

    async def async_turn_off(self):
        await self.ewelink.send_cloud(self.device, {"relaySeparation": 0})


class XBoolSwitch(XEntity, SwitchEntity):
    params = {"switch"}

    def set_state(self, params: dict):
        self._attr_is_on = params["switch"]

    async def async_turn_on(self, *args, **kwargs):
        await self.ewelink.send(self.device, {"switch": True})

    async def async_turn_off(self):
        await self.ewelink.send(self.device, {"switch": False})
