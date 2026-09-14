import asyncio
from collections import deque

from homeassistant.components.cover import CoverDeviceClass, CoverEntity
from homeassistant.exceptions import HomeAssistantError

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import (
    SIGNAL_ADD_ENTITIES,
    SIGNAL_CONNECTED,
    SIGNAL_DEVICE_EVENT,
    XRegistry,
)

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
class XCover216(XCover):
    params = {"switch", "doorState"}
    _attr_device_class = CoverDeviceClass.GATE
    _attr_is_closed = None

    def set_state(self, params: dict):
        # => command to cover from mobile app (ignore initial state)
        if len(params) == 1 and "switch" in params:
            # device receive command - on=open/off=close/pause=stop
            self._attr_is_opening = params["switch"] == "on"
            self._attr_is_closing = params["switch"] == "off"

        if "doorState" in params:
            self._attr_is_closing = self._attr_is_opening = False
            self._attr_is_closed = params["doorState"] == 0

    async def async_set_cover_position(self, position: int, **kwargs):
        return  # Device has no position control — no-op.


class XCover216Tracked(XCover216):
    """Opt-in tracking for gates which report doorState twice during opening."""

    event = True  # An initial snapshot is not a movement notification.
    _attr_assumed_state = True  # Allow resuming an opening after a partial stop.

    def __init__(self, ewelink: XRegistry, device: dict):
        self._operation = "unknown"
        self._fully_open: bool | None = None
        self._opening_reports: int | None = None
        self._revision = 0
        # Bounded replay history, retained across pauses and reconnects. d_seq is
        # opaque: compare equality only, never ordering or device/app clocks.
        self._seen = deque(maxlen=128)
        super().__init__(ewelink, device)
        door = device["params"].get("doorState")
        if type(door) is int and door in (0, 1):
            self._attr_is_closed = door == 0
            if door == 0:
                self._operation, self._fully_open = "closed", False
        self.async_on_remove(
            ewelink.dispatcher_connect(
                device["deviceid"] + SIGNAL_DEVICE_EVENT, self._handle_event
            )
        )
        self.async_on_remove(
            ewelink.cloud.dispatcher_connect(SIGNAL_CONNECTED, self._connection_changed)
        )

    @property
    def extra_state_attributes(self):
        return {"operation_state": self._operation, "fully_open": self._fully_open}

    def set_state(self, params: dict):
        # State-only callbacks include query replies and omit notification IDs.
        # Process these through _handle_event exactly once instead.
        pass

    def internal_update(self, params: dict | None = None):
        interrupted = not self.internal_available() or (
            params and params.get("online") is False
        )
        if interrupted:
            self._forget_movement()
        super().internal_update(params)
        if interrupted:
            self._write_state()

    def _write_state(self):
        if self.hass:
            self._async_write_ha_state()

    def _forget_movement(self):
        self._revision += 1
        self._operation = "unknown"
        self._fully_open = None
        self._opening_reports = None
        self._attr_is_opening = self._attr_is_closing = False
        self._attr_is_closed = None

    def _connection_changed(self):
        # Cloud observation can be interrupted even while LAN remains available.
        self._forget_movement()
        self._write_state()

    def _remember(self, key: tuple) -> bool:
        if key in self._seen:
            return False
        self._seen.append(key)
        return True

    @staticmethod
    def _identity(value) -> str | None:
        if type(value) in (int, str) and str(value):
            return str(value)
        return None

    def _command(self, command: str, sequence: str | None):
        if sequence and not self._remember(("command", sequence, command)):
            return
        self._revision += 1
        self._opening_reports = 0 if command == "on" and sequence else None
        self._attr_is_opening = command == "on"
        self._attr_is_closing = command == "off"
        if command == "pause":
            self._operation = "stopped"
        else:
            self._operation = "opening" if command == "on" else "closing"
            # A previous endstop value cannot establish position after a command.
            self._attr_is_closed = None
            self._fully_open = None
        self._write_state()

    def _handle_event(self, source: str, msg: dict):
        params = msg.get("params", {})
        if not self.available or params.get("online") is False:
            return
        if source != "cloud":
            if params.keys() & self.params:
                # The two-report protocol is only qualified for cloud pushes.
                # A LAN response may echo a cached endstop or command value.
                self._forget_movement()
                if type(params.get("doorState")) is int and params["doorState"] == 1:
                    self._attr_is_closed = False
                self._write_state()
            return
        if msg.get("action") != "update":
            return  # Initial state, queries and reconnect snapshots never count.
        command = params.get("switch")
        if msg.get("userAgent") == "app" and command in ("on", "off", "pause"):
            self._command(command, self._identity(msg.get("sequence")))
            return
        if msg.get("userAgent") != "device":
            return

        door = params.get("doorState")
        if type(door) is not int or door not in (0, 1):
            return
        identity = self._identity(msg.get("d_seq"))
        if identity and not self._remember((source, identity, door)):
            return
        self._revision += 1
        if door == 0:
            self._attr_is_closed = True
            self._attr_is_opening = self._attr_is_closing = False
            self._operation, self._fully_open = "closed", False
            self._opening_reports = None
        else:
            if identity is None:
                # No validated notification identity: position is non-closed,
                # but this report must not complete an opening sequence.
                self._forget_movement()
            self._attr_is_closed = False
            if self._operation == "opening" and self._opening_reports is not None:
                self._opening_reports += 1
                if self._opening_reports == 2:
                    self._attr_is_opening = False
                    self._operation, self._fully_open = "open", True
                    self._opening_reports = None
            elif self._operation == "closed":
                # Movement without an observed command has no known direction.
                self._operation, self._fully_open = "unknown", None
        self._write_state()

    async def _async_command(self, command: str):
        sequence = await self.ewelink.sequence()
        self._command(command, sequence)
        revision = self._revision
        try:
            result = await self.ewelink.send(
                self.device,
                {"switch": command},
                query_cloud=False,
                sequence=sequence,
                return_status=True,
            )
            if result != "online":
                raise HomeAssistantError("Gate command was not acknowledged")
        except (Exception, asyncio.CancelledError):
            if self._revision == revision:
                self._forget_movement()
                self._write_state()
            raise

    async def async_open_cover(self, **kwargs):
        await self._async_command("on")

    async def async_close_cover(self, **kwargs):
        await self._async_command("off")

    async def async_stop_cover(self, **kwargs):
        await self._async_command("pause")
