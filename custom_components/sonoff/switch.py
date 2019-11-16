import logging
from typing import Optional

from homeassistant.components.switch import SwitchDevice

from . import EWeLinkDevice

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    # We only want this platform to be set up via discovery.
    if discovery_info is None:
        return

    # TODO: переписать грамотнее
    device: EWeLinkDevice = discovery_info['device']
    data = discovery_info['data']
    if 'switch' in data:
        add_entities([SonoffSwitch(device, 0, data)])
    else:
        channels = device.config.get('channels') or len(data['switches'])
        for channel in range(1, channels + 1):
            add_entities([SonoffSwitch(device, channel, data)])


class SonoffSwitch(SwitchDevice):
    def __init__(self, device: EWeLinkDevice, channel: int = 0,
                 initdata: dict = None):
        self.device = device
        self.channel = channel
        self._state = None

        if initdata:
            self._update(initdata, False)

        device.listen(self._update)

    def _update(self, data: dict, schedule_update: bool = True):
        self._state = data['switches'][self.channel - 1]['switch'] \
            if self.channel else data['switch']

        if schedule_update:
            self.schedule_update_ha_state()

    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state.

        False if entity pushes its state to HA.
        """
        return False

    @property
    def unique_id(self) -> Optional[str]:
        """Return a unique ID."""
        return f'{self.device.deviceid}_{self.channel}' \
            if self.channel else self.device.deviceid

    @property
    def state(self):
        """Return the state of the switch."""
        return self._state

    def turn_on(self, **kwargs) -> None:
        """Turn the entity on."""
        if self.channel:
            payload = {'switches': [{'outlet': self.channel - 1,
                                     'switch': 'on'}]}
            self.device.send('switches', payload)
        else:
            payload = {'switch': 'on'}
            self.device.send('switch', payload)

    def turn_off(self, **kwargs) -> None:
        """Turn the entity off."""
        if self.channel:
            payload = {'switches': [{'outlet': self.channel - 1,
                                     'switch': 'off'}]}
            self.device.send('switches', payload)
        else:
            payload = {'switch': 'off'}
            self.device.send('switch', payload)
