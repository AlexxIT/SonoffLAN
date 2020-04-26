import logging
from typing import Optional

from homeassistant.helpers.entity import ToggleEntity

from . import EWeLinkDevice

_LOGGER = logging.getLogger(__name__)

ATTRS = ('rssi', 'humidity', 'temperature', 'power', 'current', 'voltage')


class EWeLinkToggle(ToggleEntity):
    def __init__(self, device: EWeLinkDevice, channels: list = None):
        """
        :param device: Устройство через которое принимаются и передаются
            команды
        :param channels: Список каналов или None для одноканальных устройств
        """
        self.device = device
        self.channels = channels
        self._attrs = {}
        self._name = None
        self._is_on = False

        self._update(device)

        device.listen(self._update)

    async def async_added_to_hass(self) -> None:
        # Присваиваем имя устройства только на этом этапе, чтоб в `entity_id`
        # было "sonoff_{unique_id}". Если имя присвоить в конструкторе - в
        # `entity_id` попадёт имя в латинице.
        self._name = self.device.name(self.channels)

    def _update(self, device: EWeLinkDevice):
        """Обновление от устройства.

        :param device: Устройство в котором произошло обновление
        """
        for k in ATTRS:
            if k in device.state:
                self._attrs[k] = device.state[k]

        is_on = device.is_on(self.channels)
        self._is_on = any(is_on) if self.channels else is_on

        if self.hass:
            self.schedule_update_ha_state()

    @property
    def should_poll(self) -> bool:
        # Устройство само присылает обновление своего состояния по Multicast.
        return False

    @property
    def unique_id(self) -> Optional[str]:
        if self.channels:
            chid = ''.join(str(ch) for ch in self.channels)
            return f'{self.device.deviceid}_{chid}'
        else:
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
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs) -> None:
        await self.device.turn_on(self.channels)

    async def async_turn_off(self, **kwargs) -> None:
        await self.device.turn_off(self.channels)
