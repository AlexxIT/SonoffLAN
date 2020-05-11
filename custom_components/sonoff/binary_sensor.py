import json
from typing import Optional

from homeassistant.components.binary_sensor import BinarySensorDevice

from . import DOMAIN
from .sonoff_main import EWeLinkRegistry, EWeLinkDevice


async def async_setup_platform(hass, config, add_entities,
                               discovery_info=None):
    if discovery_info is None:
        return

    deviceid = discovery_info['deviceid']
    registry = hass.data[DOMAIN]
    add_entities([EWeLinkBinarySensor(registry, deviceid)])


class EWeLinkBinarySensor(BinarySensorDevice, EWeLinkDevice):
    def __init__(self, registry: EWeLinkRegistry, deviceid: str):
        self.registry = registry
        self.deviceid = deviceid

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
    def supported_features(self):
        return 0

    @property
    def state_attributes(self):
        return self._attrs

    @property
    def is_on(self):
        return False
