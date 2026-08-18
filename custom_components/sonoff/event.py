import time
from typing import ClassVar

from homeassistant.components.event import EventEntity
from homeassistant.const import MAJOR_VERSION, MINOR_VERSION

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import SIGNAL_ADD_ENTITIES, SIGNAL_BUTTON_EVENT, XRegistry

if (MAJOR_VERSION, MINOR_VERSION) >= (2026, 8):
    from homeassistant.components.event import EventDeviceClass

PARALLEL_UPDATES = 0

BUTTON_EVENT_TYPES = ["press_end", "long_press_end", "multi_press_end"]
BUTTON_EVENTS = {
    "single": ("press_end", None),
    "double": ("multi_press_end", {"multi_press_count": 2}),
    "hold": ("long_press_end", None),
    "triple": ("multi_press_end", {"multi_press_count": 3}),
}

_DUPLICATE_WINDOW = 0.5


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, EventEntity)]),
    )


class XButtonEvent(XEntity, EventEntity):
    """One event stream for one physical button."""

    event = True
    channel: ClassVar[int]

    _attr_event_types = BUTTON_EVENT_TYPES

    if (MAJOR_VERSION, MINOR_VERSION) >= (2026, 8):
        _attr_device_class = EventDeviceClass.BUTTON

    def __init__(self, ewelink: XRegistry, device: dict):
        self.last_event_action = None
        self.last_event_at = 0.0
        super().__init__(ewelink, device)
        ewelink.dispatcher_connect(SIGNAL_BUTTON_EVENT, self.internal_button_event)

    def internal_button_event(
        self,
        deviceid: str,
        button: int | None,
        action: str,
    ):
        if deviceid != self.device["deviceid"] or button != self.channel:
            return

        event = BUTTON_EVENTS.get(action)
        if event is None:
            return

        now = time.monotonic()
        if (
            action == self.last_event_action
            and now - self.last_event_at < _DUPLICATE_WINDOW
        ):
            return

        self.last_event_action = action
        self.last_event_at = now
        self._trigger_event(*event)
        if self.hass:
            self._async_write_ha_state()
