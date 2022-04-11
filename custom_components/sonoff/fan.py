"""
Firmware   | LAN type  | uiid | Product Model
-----------|-----------|------|--------------
PSF-B04-GL | strip     | 34   | iFan02 (Sonoff iFan02)
PSF-BFB-GL | fan_light | 34   | iFan (Sonoff iFan03)

https://github.com/AlexxIT/SonoffLAN/issues/30
"""
from typing import List

from homeassistant.components.fan import FanEntity, SUPPORT_SET_SPEED

# noinspection PyUnresolvedReferences
from . import DOMAIN, SCAN_INTERVAL
from .sonoff_main import EWeLinkEntity
from .switch import EWeLinkToggle

SPEED_OFF = 0
SPEED_LOW = 33
SPEED_MEDIUM = 67
SPEED_HIGH = 100

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

    # iFan02 and iFan03 have the same uiid!
    uiid = registry.devices[deviceid].get('uiid')
    if uiid == 34 or uiid == 'fan_light':
        # only channel 2 is used for switching
        add_entities([SonoffFan02(registry, deviceid, [2])])
    elif uiid == 25:
        add_entities([SonoffDiffuserFan(registry, deviceid)])
    else:
        add_entities([SonoffSimpleFan(registry, deviceid, channels)])


class SonoffSimpleFan(EWeLinkToggle, FanEntity):
    @property
    def supported_features(self):
        return 0


class SonoffFanBase(EWeLinkEntity, FanEntity):
    _speed = 0

    @property
    def supported_features(self):
        return SUPPORT_SET_SPEED

    @property
    def percentage(self) -> int:
        return self._speed

    @property
    def speed_count(self) -> int:
        return 3

    async def async_turn_on(self, percentage: int = None, **kwargs):
        if percentage:
            await self.async_set_percentage(percentage)
        else:
            await self._turn_on()

    async def async_turn_off(self, **kwargs) -> None:
        await self._turn_off()


class SonoffFan02(SonoffFanBase):
    def _is_on_list(self, state: dict) -> List[bool]:
        # https://github.com/AlexxIT/SonoffLAN/issues/146
        switches = sorted(state['switches'], key=lambda i: i['outlet'])
        return [
            switches[channel - 1]['switch'] == 'on'
            for channel in IFAN02_CHANNELS
        ]

    def _update_handler(self, state: dict, attrs: dict):
        self._attrs.update(attrs)

        if 'switches' in state:
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

    async def async_set_percentage(self, percentage: int):
        percentage = int(round(
            round(percentage / self.percentage_step) * self.percentage_step
        ))
        channels = IFAN02_STATES.get(percentage)
        await self._turn_bulk(channels)


class SonoffDiffuserFan(SonoffFanBase):
    def _update_handler(self, state: dict, attrs: dict):
        self._attrs.update(attrs)

        if 'switch' in state:
            self._is_on = state['switch'] == 'on'

        if 'state' in state:
            if state['state'] == 1:
                self._speed = SPEED_LOW
            elif state['state'] == 2:
                self._speed = SPEED_HIGH

        self.schedule_update_ha_state()

    @property
    def percentage(self) -> int:
        return self._speed if self._is_on else SPEED_OFF

    async def async_set_percentage(self, percentage: int):
        percentage = int(round(
            round(percentage / self.percentage_step) * self.percentage_step
        ))
        if percentage in (SPEED_HIGH, SPEED_MEDIUM):
            await self.registry.send(self.deviceid,
                                     {'switch': 'on', 'state': 2})
        elif percentage == SPEED_LOW:
            await self.registry.send(self.deviceid,
                                     {'switch': 'on', 'state': 1})
        elif percentage == SPEED_OFF:
            await self._turn_off()
