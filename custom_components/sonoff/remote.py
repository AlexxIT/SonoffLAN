import asyncio
import logging
from typing import Optional

from homeassistant.components.remote import RemoteDevice, ATTR_DELAY_SECS, \
    ATTR_COMMAND, SUPPORT_LEARN_COMMAND, DEFAULT_DELAY_SECS

from . import DOMAIN, EWeLinkDevice

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    if discovery_info is None:
        return

    deviceid = discovery_info['deviceid']
    device = hass.data[DOMAIN][deviceid]
    add_entities([EWeLinkRemote(device)])


class EWeLinkRemote(RemoteDevice):
    def __init__(self, device: EWeLinkDevice):
        self.device = device
        self._name = None
        self._state = True

        device.listen(self._update)

    async def async_added_to_hass(self) -> None:
        # Присваиваем имя устройства только на этом этапе, чтоб в `entity_id`
        # было "sonoff_{unique_id}". Если имя присвоить в конструкторе - в
        # `entity_id` попадёт имя в латинице.
        self._name = self.device.name

    def _update(self, device: EWeLinkDevice, schedule_update: bool = True):
        for k, v in device.state.items():
            if k.startswith('rfTrig'):
                channel = int(k[6:])
                self.hass.bus.fire('sonoff.remote', {
                    'entity_id': self.entity_id, 'command': channel, 'ts': v})
            elif k.startswith('rfChl'):
                channel = int(k[5:])
                _LOGGER.info(f"Learn command {channel}: {v}")
            else:
                break

    @property
    def should_poll(self) -> bool:
        # Устройство само присылает обновление своего состояния по Multicast.
        return False

    @property
    def unique_id(self) -> Optional[str]:
        return self.device.deviceid

    @property
    def is_on(self) -> bool:
        return self._state

    def turn_on(self, **kwargs):
        self._state = True
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        self._state = False
        self.schedule_update_ha_state()

    @property
    def supported_features(self):
        return SUPPORT_LEARN_COMMAND

    async def async_send_command(self, command, **kwargs):
        if not self._state:
            return

        delay = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)
        for i, channel in enumerate(command):
            if i:
                await asyncio.sleep(delay)

            self.device.transmit(int(channel))

    def learn_command(self, **kwargs):
        if not self._state:
            return

        command = kwargs[ATTR_COMMAND]
        self.device.learn(int(command[0]))
