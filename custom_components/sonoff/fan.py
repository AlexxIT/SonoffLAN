from typing import Optional

from homeassistant.components.fan import FanEntity, SUPPORT_SET_SPEED, \
    SPEED_LOW, SPEED_MEDIUM, SPEED_HIGH, SPEED_OFF

from . import DOMAIN, EWeLinkDevice
from .toggle import EWeLinkToggle

IFAN02_CHANNELS = [2, 3, 4]
IFAN02_STATES = {
    SPEED_OFF: {2: False},
    SPEED_LOW: {2: True, 3: False, 4: False},
    SPEED_MEDIUM: {2: True, 3: True, 4: False},
    SPEED_HIGH: {2: True, 3: False, 4: True}
}


async def async_setup_platform(hass, config, add_entities,
                               discovery_info=None):
    if discovery_info is None:
        return

    deviceid = discovery_info['deviceid']
    channels = discovery_info['channels']
    device = hass.data[DOMAIN][deviceid]
    if device.config['type'] == 'fan_light':
        add_entities([SonoffFan03(device)])
    elif channels == IFAN02_CHANNELS:
        add_entities([SonoffFan02(device)])
    else:
        add_entities([EWeLinkToggle(device, channels)])


class SonoffFanBase(FanEntity):
    def __init__(self, device: EWeLinkDevice):
        self.device = device
        self._attrs = {}
        self._name = None
        self._speed = None

        self._update(device)

        device.listen(self._update)

    async def async_added_to_hass(self) -> None:
        # Присваиваем имя устройства только на этом этапе, чтоб в `entity_id`
        # было "sonoff_{unique_id}". Если имя присвоить в конструкторе - в
        # `entity_id` попадёт имя в латинице.
        self._name = self.device.name()

    def _update(self, device: EWeLinkDevice):
        """Обновление от устройства.

        :param device: Устройство в котором произошло обновление
        """
        pass

    @property
    def should_poll(self) -> bool:
        # Устройство само присылает обновление своего состояния по Multicast.
        return False

    @property
    def unique_id(self) -> Optional[str]:
        return self.device.deviceid

    @property
    def name(self) -> Optional[str]:
        return self._name

    @property
    def speed(self) -> Optional[str]:
        return self._speed

    @property
    def speed_list(self) -> list:
        return [SPEED_OFF, SPEED_LOW, SPEED_MEDIUM, SPEED_HIGH]

    @property
    def supported_features(self):
        return SUPPORT_SET_SPEED


class SonoffFan02(SonoffFanBase):
    def _update(self, device: EWeLinkDevice):
        state = device.is_on(IFAN02_CHANNELS)

        if state[0]:
            if not state[1] and not state[2]:
                self._speed = SPEED_LOW
            elif state[1] and not state[2]:
                self._speed = SPEED_MEDIUM
            elif not state[1] and state[2]:
                self._speed = SPEED_HIGH
            else:
                raise Exception("Wrong iFan02 state")
        else:
            self._speed = SPEED_OFF

        if self.hass:
            self.schedule_update_ha_state()

    async def async_set_speed(self, speed: str) -> None:
        channels = IFAN02_STATES.get(speed)
        await self.device.turn_bulk(channels)

    async def async_turn_on(self, speed: Optional[str] = None, **kwargs):
        if speed:
            await self.async_set_speed(speed)
        else:
            await self.device.turn_on([2])

    async def async_turn_off(self, **kwargs) -> None:
        await self.device.turn_off([2])


class SonoffFan03(SonoffFanBase):
    def _update(self, device: EWeLinkDevice):
        if 'fan' not in device.state:
            return

        if device.state['fan'] == 'on':
            speed = device.state.get('speed', 1)
            self._speed = self.speed_list[speed]
        else:
            self._speed = SPEED_OFF

        if self.hass:
            self.schedule_update_ha_state()

    async def async_set_speed(self, speed: str) -> None:
        speed = self.speed_list.index(speed)
        await self.device.send('fan', {'fan': 'on', 'speed': speed})

    async def async_turn_on(self, speed: Optional[str] = None, **kwargs):
        if speed:
            await self.async_set_speed(speed)
        else:
            await self.device.send('fan', {'fan': 'on'})

    async def async_turn_off(self, **kwargs) -> None:
        await self.device.send('fan', {'fan': 'off'})
