from typing import Optional
import json
from homeassistant.components.binary_sensor import BinarySensorDevice

from . import DOMAIN, EWeLinkDevice


async def async_setup_platform(hass, config, add_entities,
                               discovery_info=None):
    if discovery_info is None:
        return

    deviceid = discovery_info['deviceid']
    device = hass.data[DOMAIN][deviceid]
    add_entities([EWeLinkBinarySensor(device)])


class EWeLinkBinarySensor(BinarySensorDevice):
    def __init__(self, device: EWeLinkDevice):
        self.device = device
        self._attrs = {}
        self._name = None

        self._update(device)

        device.listen(self._update)

    async def async_added_to_hass(self) -> None:
        self._name = self.device.name()

    def _update(self, device: EWeLinkDevice):
        state = {k: json.dumps(v) for k, v in device.state.items()}
        self._attrs.update(state)

        if self.hass:
            self.schedule_update_ha_state()

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def unique_id(self) -> Optional[str]:
        return self.device.deviceid

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
