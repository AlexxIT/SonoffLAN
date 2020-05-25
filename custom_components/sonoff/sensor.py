from typing import Optional

from homeassistant.const import DEVICE_CLASS_TEMPERATURE, TEMP_CELSIUS, \
    DEVICE_CLASS_HUMIDITY, DEVICE_CLASS_ILLUMINANCE
from homeassistant.helpers.entity import Entity

from . import DOMAIN, EWeLinkRegistry
from .sonoff_main import EWeLinkDevice

SONOFF_SC = {
    'temperature': [DEVICE_CLASS_TEMPERATURE, TEMP_CELSIUS, None],
    # UNIT_PERCENTAGE is not on old versions
    'humidity': [DEVICE_CLASS_HUMIDITY, "%", None],
    'dusty': [None, None, 'mdi:cloud'],
    'light': [DEVICE_CLASS_ILLUMINANCE, None, None],
    'noise': [None, None, 'mdi:bell-ring']
}


async def async_setup_platform(hass, config, add_entities,
                               discovery_info=None):
    if discovery_info is None:
        return

    deviceid = discovery_info['deviceid']
    registry = hass.data[DOMAIN]
    device = registry.devices[deviceid]
    if device.get('uiid') == 18:
        add_entities([SonoffSC(registry, deviceid, attr)
                      for attr in SONOFF_SC])


class SonoffSC(EWeLinkDevice, Entity):
    _state = None

    def __init__(self, registry: EWeLinkRegistry, deviceid: str, attr: str):
        super().__init__(registry, deviceid)
        self._attr = attr

    async def async_added_to_hass(self) -> None:
        self._init()

        if self._name:
            self._name += f" {self._attr.capitalize()}"

    def _update_handler(self, state: dict, attrs: dict):
        if self._attr in state:
            self._state = state[self._attr]

        self.schedule_update_ha_state()

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def unique_id(self) -> Optional[str]:
        return f"{self.deviceid}_{self._attr}"

    @property
    def name(self) -> Optional[str]:
        return self._name

    @property
    def state(self) -> str:
        return self._state

    @property
    def state_attributes(self):
        return self._attrs

    @property
    def available(self) -> bool:
        device: dict = self.registry.devices[self.deviceid]
        return device['available']

    @property
    def device_class(self):
        return SONOFF_SC[self._attr][0]

    @property
    def unit_of_measurement(self):
        return SONOFF_SC[self._attr][1]

    @property
    def icon(self):
        return SONOFF_SC[self._attr][2]
