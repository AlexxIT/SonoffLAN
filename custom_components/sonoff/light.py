from homeassistant.components.light import SUPPORT_BRIGHTNESS, \
    ATTR_BRIGHTNESS

from . import DOMAIN, EWeLinkDevice
from .toggle import ATTRS, EWeLinkToggle


def setup_platform(hass, config, add_entities, discovery_info=None):
    if discovery_info is None:
        return

    deviceid = discovery_info['deviceid']
    channels = discovery_info['channels']
    device = hass.data[DOMAIN][deviceid]
    if channels and len(channels) >= 2:
        add_entities([EWeLinkLight(device, channels)])
    else:
        add_entities([EWeLinkToggle(device, channels)])


class EWeLinkLight(EWeLinkToggle):
    """Отличается от обычного переключателя настройкой яркости. Логично
    использовать только для двух и более каналов. Умеет запоминать яркость на
    момент выключения.

    Последовательность каналов важна. Первые каналы будут включены при низкой
    яркости.
    """

    def __init__(self, device: EWeLinkDevice, channels: list):
        assert channels and len(channels) >= 2, channels

        super().__init__(device, channels)

        self._brightness = 0

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

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        return self._brightness

    @property
    def supported_features(self):
        """Flag supported features."""
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
