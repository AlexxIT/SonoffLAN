import logging

from homeassistant.components.light import SUPPORT_BRIGHTNESS, \
    ATTR_BRIGHTNESS

from . import DOMAIN, EWeLinkDevice, utils
from .toggle import ATTRS, EWeLinkToggle

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    if discovery_info is None:
        return

    deviceid = discovery_info['deviceid']
    channels = discovery_info['channels']
    device = hass.data[DOMAIN][deviceid]
    if channels and len(channels) >= 2:
        add_entities([EWeLinkLightGroup(device, channels)])
    elif utils.guess_device_class(device.config) == 'light':
        add_entities([EWeLinkLight(device)])
    else:
        add_entities([EWeLinkToggle(device, channels)])


class EWeLinkLight(EWeLinkToggle):
    """Sonoff D1"""

    def __init__(self, device: EWeLinkDevice, channels: list = None):
        self._brightness = 0

        super().__init__(device, channels)

    def _update(self, device: EWeLinkDevice, schedule_update: bool = True):
        # яркость прилетает не всегда
        if 'brightness' in device.state:
            self._brightness = round(device.state['brightness'] * 2.55)

        self._is_on = device.is_on(None)

        if schedule_update:
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

    def turn_on(self, **kwargs) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[ATTR_BRIGHTNESS]

        br = round(self._brightness / 2.55)
        self.device.send('dimmable', {'switch': 'on', 'brightness': br,
                                      'mode': 0})


class EWeLinkLightGroup(EWeLinkLight):
    """Отличается от обычного переключателя настройкой яркости. Логично
    использовать только для двух и более каналов. Умеет запоминать яркость на
    момент выключения.

    Последовательность каналов важна. Первые каналы будут включены при низкой
    яркости.
    """

    def _update(self, device: EWeLinkDevice, schedule_update: bool = True):
        for k in ATTRS:
            if k in device.state:
                self._attrs[k] = device.state[k]

        # количество включенных каналов
        cnt = sum(device.is_on(self.channels))
        if cnt:
            # если хоть что-то включено - запоминаем новую яркость
            self._brightness = round(cnt / len(self.channels) * 255)
            self._is_on = True
        else:
            self._is_on = False

        if schedule_update:
            self.schedule_update_ha_state()

    def turn_on(self, **kwargs) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[ATTR_BRIGHTNESS]

        # сколько света должно гореть при такой яркости
        cnt = round(self._brightness / 255 * len(self.channels))

        # если попытались включить при нулевой яркости - включаем весь свет
        if cnt == 0 and ATTR_BRIGHTNESS not in kwargs:
            self.device.turn_on(self.channels)
            return

        # первую часть света включаем, вторую - выключаем
        channels = {
            channel: i < cnt
            for i, channel in enumerate(self.channels)
        }
        self.device.turn_bulk(channels)
