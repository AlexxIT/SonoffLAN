"""
Firmware   | LAN type  | uiid | Product Model
-----------|-----------|------|--------------
PSF-B04-GL | strip     | 34   | iFan02 (Sonoff iFan02)
PSF-BFB-GL | fan_light | 34   | iFan (Sonoff iFan03)

https://github.com/AlexxIT/SonoffLAN/issues/30
"""
from typing import Optional, List

from homeassistant.components.fan import FanEntity, SUPPORT_SET_SPEED, \
    SPEED_LOW, SPEED_MEDIUM, SPEED_HIGH, SPEED_OFF

# noinspection PyUnresolvedReferences
from . import DOMAIN, SCAN_INTERVAL
from .sonoff_main import EWeLinkDevice
from .switch import EWeLinkToggle

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
    registry = hass.data[DOMAIN]
    device = registry.devices[deviceid]
    uiid = device.get('uiid')
    # iFan02 and iFan03 have the same uiid!
    if uiid == 'fan_light' or device.get('productModel') == 'iFan':
        add_entities([SonoffFan03(registry, deviceid)])
    elif channels == IFAN02_CHANNELS:
        # only channel 2 is used for switching
        add_entities([SonoffFan02(registry, deviceid, [2])])
    else:
        add_entities([EWeLinkToggle(registry, deviceid, channels)])


class SonoffFanBase(FanEntity, EWeLinkDevice):
    _speed = None

    async def async_added_to_hass(self) -> None:
        self._init()

    @property
    def should_poll(self) -> bool:
        # The device itself sends an update of its status
        return False

    @property
    def unique_id(self) -> Optional[str]:
        return self.deviceid

    @property
    def name(self) -> Optional[str]:
        return self._name

    @property
    def available(self) -> bool:
        device: dict = self.registry.devices[self.deviceid]
        return device['available']

    @property
    def supported_features(self):
        return SUPPORT_SET_SPEED

    @property
    def speed(self) -> Optional[str]:
        return self._speed

    @property
    def speed_list(self) -> list:
        return [SPEED_OFF, SPEED_LOW, SPEED_MEDIUM, SPEED_HIGH]


class SonoffFan02(SonoffFanBase):
    def _is_on_list(self, state: dict) -> List[bool]:
        switches = state['switches']
        return [
            switches[channel - 1]['switch'] == 'on'
            for channel in IFAN02_CHANNELS
        ]

    def _update_handler(self, state: dict, attrs: dict):
        self._attrs.update(attrs)

        if state and 'switches' in state:
            mask = self._is_on_list(state)
            if mask[0]:
                if not mask[1] and not mask[2]:
                    self._speed = SPEED_LOW
                elif mask[1] and not mask[2]:
                    self._speed = SPEED_MEDIUM
                elif not mask[1] and mask[2]:
                    self._speed = SPEED_HIGH
                else:
                    raise Exception("Wrong iFan02 state")
            else:
                self._speed = SPEED_OFF

        self.schedule_update_ha_state()

    async def async_set_speed(self, speed: str) -> None:
        channels = IFAN02_STATES.get(speed)
        await self._turn_bulk(channels)

    async def async_turn_on(self, speed: Optional[str] = None, **kwargs):
        if speed:
            await self.async_set_speed(speed)
        else:
            await self._turn_on()

    async def async_turn_off(self, **kwargs) -> None:
        await self._turn_off()


class SonoffFan03(SonoffFanBase):
    def _update_handler(self, state: dict, attrs: dict):
        self._attrs.update(attrs)

        if 'fan' in state:
            if state['fan'] == 'on':
                speed = state.get('speed', 1)
                self._speed = self.speed_list[speed]
            else:
                self._speed = SPEED_OFF

        self.schedule_update_ha_state()

    async def async_set_speed(self, speed: str) -> None:
        speed = self.speed_list.index(speed)
        await self.registry.send(self.deviceid, {'fan': 'on', 'speed': speed})

    async def async_turn_on(self, speed: Optional[str] = None, **kwargs):
        if speed:
            await self.async_set_speed(speed)
        else:
            await self.registry.send(self.deviceid, {'fan': 'on'})

    async def async_turn_off(self, **kwargs) -> None:
        await self.registry.send(self.deviceid, {'fan': 'off'})
