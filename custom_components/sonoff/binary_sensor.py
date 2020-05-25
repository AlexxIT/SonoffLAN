import json
from typing import Optional

from homeassistant.components.binary_sensor import DEVICE_CLASS_DOOR

from . import DOMAIN
from .sonoff_main import EWeLinkDevice
from .utils import BinarySensorEntity


async def async_setup_platform(hass, config, add_entities,
                               discovery_info=None):
    if discovery_info is None:
        return

    deviceid = discovery_info['deviceid']
    registry = hass.data[DOMAIN]
    device = registry.devices[deviceid]
    if device.get('uiid') == 102:
        add_entities([DoorWindowSensor(registry, deviceid)])
    else:
        add_entities([EWeLinkBinarySensor(registry, deviceid)])


class EWeLinkBinarySensor(BinarySensorEntity, EWeLinkDevice):
    async def async_added_to_hass(self) -> None:
        self._init()

    def _update_handler(self, state: dict, attrs: dict):
        state = {k: json.dumps(v) for k, v in state.items()}
        self._attrs.update(state)
        self.schedule_update_ha_state()

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def unique_id(self) -> Optional[str]:
        return self.deviceid

    @property
    def name(self) -> Optional[str]:
        return self._name

    @property
    def state_attributes(self):
        return self._attrs

    @property
    def supported_features(self):
        return 0

    @property
    def is_on(self):
        return self._is_on


class DoorWindowSensor(EWeLinkBinarySensor):
    _device_class = None

    async def async_added_to_hass(self) -> None:
        device: dict = self.registry.devices[self.deviceid]
        self._device_class = device.get('device_class', DEVICE_CLASS_DOOR)

        self._init()

    def _update_handler(self, state: dict, attrs: dict):
        self._attrs.update(attrs)

        if 'switch' in state:
            self._is_on = state['switch'] == 'on'

        self.schedule_update_ha_state()

    @property
    def available(self) -> bool:
        device: dict = self.registry.devices[self.deviceid]
        return device['available']

    @property
    def device_class(self):
        return self._device_class
