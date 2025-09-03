from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
)
from homeassistant.const import MAJOR_VERSION, MINOR_VERSION

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import SIGNAL_ADD_ENTITIES, XRegistry

PARALLEL_UPDATES = 0  # fix entity_platform parallel_updates Semaphore


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities(
            [e for e in x if isinstance(e, AlarmControlPanelEntity)]
        ),
    )


if (MAJOR_VERSION, MINOR_VERSION) >= (2024, 11):
    from homeassistant.components.alarm_control_panel import AlarmControlPanelState

    STATES = {
        0: AlarmControlPanelState.DISARMED,
        1: AlarmControlPanelState.ARMED_HOME,
        2: AlarmControlPanelState.ARMED_AWAY,
        3: AlarmControlPanelState.ARMED_NIGHT,
    }

    class XAlarmControlBase(XEntity, AlarmControlPanelEntity):
        def set_state(self, params: dict):
            if self.param in params:
                self._attr_alarm_state = STATES.get(params[self.param])

else:
    STATES = {0: "disarmed", 1: "armed_home", 2: "armed_away", 3: "armed_night"}

    class XAlarmControlBase(XEntity, AlarmControlPanelEntity):
        def set_state(self, params: dict):
            if self.param in params:
                self._attr_state = STATES.get(params[self.param])


class XPanelAlarm(XAlarmControlBase):
    param = "securityType"
    uid = "alarm"

    _attr_code_arm_required = False
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_NIGHT
    )

    async def async_alarm_disarm(self, code=None):
        await self.ewelink.send(self.device, {self.param: 0})

    async def async_alarm_arm_home(self, code=None):
        await self.ewelink.send(self.device, {self.param: 1, "currentType": 1})

    async def async_alarm_arm_away(self, code=None):
        await self.ewelink.send(self.device, {self.param: 2, "currentType": 2})

    async def async_alarm_arm_night(self, code=None):
        await self.ewelink.send(self.device, {self.param: 3, "currentType": 3})
