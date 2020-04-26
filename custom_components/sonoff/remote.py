import asyncio
import logging
from typing import Optional

from homeassistant.components.remote import RemoteDevice, ATTR_DELAY_SECS, \
    ATTR_COMMAND, SUPPORT_LEARN_COMMAND, DEFAULT_DELAY_SECS

from . import DOMAIN, EWeLinkDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, add_entities,
                               discovery_info=None):
    if discovery_info is None:
        return

    deviceid = discovery_info['deviceid']
    device = hass.data[DOMAIN][deviceid]
    add_entities([EWeLinkRemote(device)])


class EWeLinkRemote(RemoteDevice):
    def __init__(self, device: EWeLinkDevice):
        self.device = device
        self._attrs = {}
        self._name = None
        self._state = True

        device.listen(self._update)

        # init button names
        self._buttons = {}
        for remote in self.device.config.get('tags', {}).get('zyx_info', []):
            buttons = remote['buttonName']
            if len(buttons) > 1:
                for button in buttons:
                    self._buttons.update(button)
            else:
                k = next(iter(buttons[0]))
                self._buttons.update({k: remote['name']})

    async def async_added_to_hass(self) -> None:
        # Присваиваем имя устройства только на этом этапе, чтоб в `entity_id`
        # было "sonoff_{unique_id}". Если имя присвоить в конструкторе - в
        # `entity_id` попадёт имя в латинице.
        self._name = self.device.name()

    def _update(self, device: EWeLinkDevice):
        for k, v in device.state.items():
            if k.startswith('rfTrig'):
                channel = k[6:]
                self._attrs = {'command': int(channel), 'ts': v,
                               'name': self._buttons.get(channel)}
                self.hass.bus.fire('sonoff.remote', {
                    'entity_id': self.entity_id, **self._attrs})

                if self.hass:
                    self.schedule_update_ha_state()

            elif k.startswith('rfChl'):
                channel = int(k[5:])
                _LOGGER.info(f"Learn command {channel}: {v}")

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

    @property
    def supported_features(self):
        return SUPPORT_LEARN_COMMAND

    @property
    def state_attributes(self):
        return self._attrs

    async def async_turn_on(self, **kwargs):
        self._state = True
        self.schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        self._state = False
        self.schedule_update_ha_state()

    async def async_send_command(self, command, **kwargs):
        if not self._state:
            return

        delay = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)
        for i, channel in enumerate(command):
            if i:
                await asyncio.sleep(delay)

            if not channel.isdigit():
                channel = next((k for k, v in self._buttons.items()
                                if v == channel), None)

            if channel is None:
                _LOGGER.error(f"Not found RF button for {command}")
                return

            await self.device.transmit(int(channel))

    async def async_learn_command(self, **kwargs):
        if not self._state:
            return

        command = kwargs[ATTR_COMMAND]
        await self.device.learn(int(command[0]))
