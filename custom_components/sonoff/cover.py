from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import SIGNAL_ADD_ENTITIES, XRegistry

PARALLEL_UPDATES = 0  # fix entity_platform parallel_updates Semaphore


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, CoverEntity)]),
    )


# noinspection PyUnresolvedReferences
DEVICE_CLASSES = {cls.value: cls for cls in CoverDeviceClass}


# noinspection PyAbstractClass
class XCover(XEntity, CoverEntity):
    params = {"switch", "setclose"}

    def __init__(self, ewelink: XRegistry, device: dict):
        XEntity.__init__(self, ewelink, device)
        # Fix device_class for multi-channel device UIID 211
        # https://github.com/AlexxIT/SonoffLAN/pull/1785
        if (v := device.get("device_class")) and isinstance(v, str):
            self._attr_device_class = DEVICE_CLASSES.get(v)

    def set_state(self, params: dict):
        # => command to cover from mobile app
        if len(params) == 1:
            if "switch" in params:
                # device receive command - on=open/off=close/pause=stop
                self._attr_is_opening = params["switch"] == "on"
                self._attr_is_closing = params["switch"] == "off"
            elif "setclose" in params:
                # device receive command - mode to position
                pos = 100 - params["setclose"]
                self._attr_is_closing = pos < self.current_cover_position
                self._attr_is_opening = pos > self.current_cover_position

        # BINTHEN BCM Series payload:
        #   {"sequence":"1652428259464","setclose":38}
        # KingArt KING-Q4 payloads:
        #   {"switch":"off","setclose":21} or {"switch":"on","setclose":0}
        elif "setclose" in params:
            # the device has finished the action
            # reversed position: HA closed at 0, eWeLink closed at 100
            self._attr_current_cover_position = 100 - params["setclose"]
            self._attr_is_closed = self.current_cover_position == 0
            self._attr_is_closing = False
            self._attr_is_opening = False

    async def async_stop_cover(self, **kwargs):
        params = {"switch": "pause"}
        self.set_state(params)
        self._async_write_ha_state()
        await self.ewelink.send(self.device, params, query_cloud=False)

    async def async_open_cover(self, **kwargs):
        params = {"switch": "on"}
        self.set_state(params)
        self._async_write_ha_state()
        await self.ewelink.send(self.device, params, query_cloud=False)

    async def async_close_cover(self, **kwargs):
        params = {"switch": "off"}
        self.set_state(params)
        self._async_write_ha_state()
        await self.ewelink.send(self.device, params, query_cloud=False)

    async def async_set_cover_position(self, position: int, **kwargs):
        params = {"setclose": 100 - position}
        self.set_state(params)
        self._async_write_ha_state()
        await self.ewelink.send(self.device, params, query_cloud=False)


class XZBCover(XCover):
    def internal_set_position(self, value: int):
        self._attr_current_cover_position = 100 - value
        self._attr_is_closed = self.current_cover_position == 0
        self._attr_is_closing = self._attr_is_opening = False

    def internal_set_motion(self, value: str):
        self._attr_is_closing = value == "off"
        self._attr_is_opening = value == "on"

    def set_state(self, params: dict):
        # device init
        if "setclose" in params and "switch" in params:
            self.internal_set_position(params["setclose"])
            return

        # check if this is command from mobile app
        if self.device.get("cloud_seq"):
            return

        if "setclose" in params:
            self.internal_set_position(params["setclose"])
        elif "switch" in params:
            self.internal_set_motion(params["switch"])

    async def async_stop_cover(self, **kwargs):
        await self.ewelink.send(self.device, {"switch": "pause"}, query_cloud=False)

    async def async_open_cover(self, **kwargs):
        await self.ewelink.send(self.device, {"switch": "on"}, query_cloud=False)

    async def async_close_cover(self, **kwargs):
        await self.ewelink.send(self.device, {"switch": "off"}, query_cloud=False)

    async def async_set_cover_position(self, position: int, **kwargs):
        params = {"setclose": 100 - position}
        await self.ewelink.send(self.device, params, query_cloud=False)


# noinspection PyAbstractClass
class XCoverDualR3(XCover):
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

    async def async_set_cover_position(self, position: int, **kwargs):
        await self.ewelink.send(self.device, {"location": position})


# noinspection PyAbstractClass
class XZigbeeCover(XCover):
    params = {"curPercent", "curtainAction"}

    def set_state(self, params: dict):
        if "curPercent" in params:
            # reversed position: HA closed at 0, eWeLink closed at 100
            self._attr_current_cover_position = 100 - params["curPercent"]
            self._attr_is_closed = self._attr_current_cover_position == 0

    async def async_stop_cover(self, **kwargs):
        await self.ewelink.send(self.device, {"curtainAction": "pause"})

    async def async_open_cover(self, **kwargs):
        await self.ewelink.send(self.device, {"curtainAction": "open"})

    async def async_close_cover(self, **kwargs):
        await self.ewelink.send(self.device, {"curtainAction": "close"})

    async def async_set_cover_position(self, position: int, **kwargs):
        await self.ewelink.send(self.device, {"openPercent": 100 - position})


class XCoverOP(XEntity, CoverEntity):
    param = "op"

    _attr_is_closed = None  # unknown state

    def set_state(self, params: dict):
        if "per" in params:
            # UIID 67: {'op': 3, 'per': 0, 'statu': 6} - CLOSED
            # UIID 67: {'op': 1, 'per': 100, 'statu': 5} - OPEN
            self._attr_is_closed = params["per"] == 0
            self._attr_is_closing = self._attr_is_opening = False
        elif "op" in params:
            if params["op"] == 1:
                # UIID 67: {"op": 1} - OPENING
                self._attr_is_closing = False
                self._attr_is_opening = True
            elif params["op"] == 2:
                self._attr_is_closed = None
                self._attr_is_closing = self._attr_is_opening = False
            elif params["op"] == 3:
                # UIID 67: {"op": 3} - CLOSING
                self._attr_is_closing = True
                self._attr_is_opening = False

    async def async_stop_cover(self, **kwargs):
        await self.ewelink.send(self.device, {self.param: 2})

    async def async_open_cover(self, **kwargs):
        await self.ewelink.send(self.device, {self.param: 1})

    async def async_close_cover(self, **kwargs):
        await self.ewelink.send(self.device, {self.param: 3})


# noinspection PyAbstractClass
class XCoverT5(XCover):
    params = {"electromotor", "percentageControl"}

    _attr_entity_registry_enabled_default = False

    _attr_is_closed = None  # unknown state

    def set_state(self, params: dict):
        if "percentageControl" in params and params.get("calibState") is True:
            self._attr_current_cover_position = 100 - params["percentageControl"]
            self._attr_is_closed = self._attr_current_cover_position == 0

        if "electromotor" in params:
            if params["electromotor"] == 1:  # stop
                self._attr_is_opening = False
                self._attr_is_closing = False
            elif params["electromotor"] == 0:  # open
                self._attr_is_opening = True
                self._attr_is_closing = False
            elif params["electromotor"] == 2:  # close
                self._attr_is_opening = False
                self._attr_is_closing = True

    async def async_stop_cover(self, **kwargs):
        await self.ewelink.send(self.device, {"electromotor": 1})

    async def async_open_cover(self, **kwargs):
        await self.ewelink.send(self.device, {"electromotor": 0})

    async def async_close_cover(self, **kwargs):
        await self.ewelink.send(self.device, {"electromotor": 2})

    async def async_set_cover_position(self, position: int, **kwargs):
        await self.ewelink.send(self.device, {"percentageControl": 100 - position})


# noinspection PyAbstractClass
class XCoverBL602Door(XCover):
    # CoolKit CK-BL602-TC-01 (uiid 216) — VEVOR MD370/MD750 sliding gate motor.
    # Only a bottom endstop is reported: doorState 0=fully closed, 1=not-fully-closed.
    # There is no reliable "fully open" or motion signal from the device, so we only
    # expose closed/open and closing (whose end we know from doorState=0). We do not
    # expose "opening" — it would just be a guess.
    params = {"switch", "doorState"}
    event = True  # skip initial set_state; seed from device["params"] in __init__
    _attr_device_class = CoverDeviceClass.GATE
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )
    _attr_is_closed = None
    # Only bottom endstop is known — "open" really means "not fully closed".
    # Keep all controls active so the user can re-issue open/close/stop from any state.
    _attr_assumed_state = True

    def __init__(self, ewelink: XRegistry, device: dict):
        super().__init__(ewelink, device)
        ds = device["params"].get("doorState")
        if ds is not None:
            self._attr_is_closed = ds == 0

    def set_state(self, params: dict):
        # Only lone doorState pushes reflect real endstop transitions. Command echoes
        # and full state dumps also contain doorState but with pre-command values.
        if "doorState" not in params or "switch" in params:
            return
        state = params["doorState"]
        self._attr_is_closed = state == 0
        if state == 0:
            # Bottom endstop reached → gate is fully closed, closing done.
            self._attr_is_closing = False

    async def async_open_cover(self, **kwargs):
        self._attr_is_closing = False
        self._attr_is_closed = False
        self._async_write_ha_state()
        await self.ewelink.send(self.device, {"switch": "on"}, query_cloud=False)

    async def async_close_cover(self, **kwargs):
        self._attr_is_closing = True
        self._async_write_ha_state()
        await self.ewelink.send(self.device, {"switch": "off"}, query_cloud=False)

    async def async_stop_cover(self, **kwargs):
        self._attr_is_closing = False
        self._async_write_ha_state()
        await self.ewelink.send(self.device, {"switch": "pause"}, query_cloud=False)

    async def async_set_cover_position(self, position: int, **kwargs):
        # Device has no position control — no-op.
        return
