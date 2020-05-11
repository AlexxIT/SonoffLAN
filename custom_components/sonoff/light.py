"""
Firmware   | LAN type  | uiid | Product Model
-----------|-----------|------|--------------
PSF-BLD-GL | light     | 44   | D1 (Sonoff D1)
PSF-BFB-GL | fan_light | 34   | iFan (Sonoff iFan03)
"""
import logging

from homeassistant.components.light import SUPPORT_BRIGHTNESS, ATTR_BRIGHTNESS

from . import DOMAIN
from .switch import EWeLinkToggle

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, add_entities,
                               discovery_info=None):
    if discovery_info is None:
        return

    deviceid = discovery_info['deviceid']
    channels = discovery_info['channels']
    registry = hass.data[DOMAIN]
    device = registry.devices[deviceid]

    if device['type'] == 'fan_light' or device.get('productModel') == 'iFan':
        add_entities([SonoffFan03Light(registry, deviceid)])
    elif device['type'] == 'light' or device.get('uiid') == 44:
        add_entities([SonoffD1(registry, deviceid)])
    elif channels and len(channels) >= 2:
        add_entities([EWeLinkLightGroup(registry, deviceid, channels)])
    else:
        add_entities([EWeLinkToggle(registry, deviceid, channels)])


class SonoffFan03Light(EWeLinkToggle):
    def _update_handler(self, state: dict, attrs: dict):
        self._attrs.update(attrs)

        if 'light' in state:
            self._is_on = state['light'] == 'on'

        self.schedule_update_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        await self.registry.send(self.deviceid, {'light': 'on'})

    async def async_turn_off(self, **kwargs) -> None:
        await self.registry.send(self.deviceid, {'light': 'off'})


class SonoffD1(EWeLinkToggle):
    """Sonoff D1"""
    _brightness = 0

    def _update_handler(self, state: dict, attrs: dict):
        self._attrs.update(attrs)

        # if 'online' in state:
        #     self._available = state['online']

        if 'brightness' in state:
            self._brightness = max(round(state['brightness'] * 2.55), 1)

        if 'switch' in state:
            self._is_on = any(self._is_on_list(state))

        self.schedule_update_ha_state()

    @property
    def brightness(self):
        return self._brightness

    @property
    def supported_features(self):
        return SUPPORT_BRIGHTNESS

    @property
    def state_attributes(self):
        return {
            **self._attrs,
            ATTR_BRIGHTNESS: self.brightness
        }

    async def async_turn_on(self, **kwargs) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[ATTR_BRIGHTNESS]

        br = max(round(self._brightness / 2.55), 1)
        # cmd param only for local mode, no need for cloud
        await self.registry.send(self.deviceid, {
            'cmd': 'dimmable', 'switch': 'on', 'brightness': br, 'mode': 0})


class EWeLinkLightGroup(SonoffD1):
    """Differs from the usual switch by brightness adjustment. Is logical
    use only for two or more channels. Able to remember brightness on moment
    off.

    The sequence of channels is important. The first channels will be turned on
    at low brightness.
    """

    def _update_handler(self, state: dict, attrs: dict):
        self._attrs.update(attrs)

        if 'switches' in state:
            # number of active channels
            cnt = sum(self._is_on_list(state))
            if cnt:
                # if at least something is on - remember the new brightness
                self._brightness = round(cnt / len(self.channels) * 255)
                self._is_on = True
            else:
                self._is_on = False

        self.schedule_update_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[ATTR_BRIGHTNESS]

        # how much light should burn at such brightness
        cnt = round(self._brightness / 255 * len(self.channels))

        # if tried to turn it on at zero brightness - turn on all the light
        if cnt == 0 and ATTR_BRIGHTNESS not in kwargs:
            await self._turn_on()
            return

        # the first part of the lights - turn on, the second - turn off
        channels = {
            channel: i < cnt
            for i, channel in enumerate(self.channels)
        }
        await self._turn_bulk(channels)
