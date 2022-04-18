from homeassistant.components.cover import CoverEntity, ATTR_POSITION

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import XRegistry, SIGNAL_ADD_ENTITIES


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, CoverEntity)])
    )


# noinspection PyAbstractClass
class XCover(XEntity, CoverEntity):
    params = {"switch", "setclose"}

    def set_state(self, params: dict):
        # skip any full state update except first one
        if self._attr_current_cover_position and len(params) > 2:
            return

        if "setclose" in params:
            newposition = 100 - params["setclose"]
            # finished the movement (on - opening, off - closing)
            if "switch" in params:
                # reversed position: HA closed at 0, eWeLink closed at 100
                self._attr_current_cover_position = newposition
                self._attr_is_closed = self._attr_current_cover_position == 0
            elif newposition > self._attr_current_cover_position:
                self._attr_is_opening = True
                self._attr_is_closing = False
            elif newposition < self._attr_current_cover_position:
                self._attr_is_opening = False
                self._attr_is_closing = True

        # full open or full close command
        elif "switch" in params:
            if params["switch"] == "on":
                self._attr_is_opening = True
                self._attr_is_closing = False
            elif params["switch"] == "off":
                self._attr_is_opening = False
                self._attr_is_closing = True
            elif params["switch"] == "pause":
                self._attr_is_opening = False
                self._attr_is_closing = False

    async def async_stop_cover(self, **kwargs):
        params = {"switch": "pause"}
        self.set_state(params)
        await self.ewelink.send(self.device, params)

    async def async_open_cover(self, **kwargs):
        params = {"switch": "on"}
        self.set_state(params)
        await self.ewelink.send(self.device, params)

    async def async_close_cover(self, **kwargs):
        params = {"switch": "off"}
        self.set_state(params)
        await self.ewelink.send(self.device, params)

    async def async_set_cover_position(self, position: int, **kwargs):
        params = {"setclose": 100 - position}
        self.set_state(params)
        await self.ewelink.send(self.device, params)


# noinspection PyAbstractClass
class XCoverDualR3(XEntity, CoverEntity):
    params = {"currLocation", "motorTurn"}

    def set_state(self, params: dict):
        if "currLocation" in params:
            # 0 - closed, 100 - opened
            self._attr_current_cover_position = params["currLocation"]
            self._attr_is_closed = self._attr_current_cover_position == 0

        if "motorTurn" in params:
            if params["motorTurn"] == 0:  # stop
                self._attr_is_opening = False
                self._attr_is_closing = False
            elif params["motorTurn"] == 1:
                self._attr_is_opening = True
                self._attr_is_closing = False
            elif params["motorTurn"] == 2:
                self._attr_is_opening = False
                self._attr_is_closing = True

    async def async_stop_cover(self, **kwargs):
        await self.ewelink.send(self.device, {"motorTurn": 0})

    async def async_open_cover(self, **kwargs):
        await self.ewelink.send(self.device, {"motorTurn": 1})

    async def async_close_cover(self, **kwargs):
        await self.ewelink.send(self.device, {"motorTurn": 2})

    async def async_set_cover_position(self, **kwargs):
        position = kwargs.get(ATTR_POSITION)
        await self.ewelink.send(self.device, {"location": position})
