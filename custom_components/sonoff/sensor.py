import time
from typing import Optional

from homeassistant.const import DEVICE_CLASS_TEMPERATURE, \
    DEVICE_CLASS_HUMIDITY, DEVICE_CLASS_ILLUMINANCE, DEVICE_CLASS_POWER, \
    DEVICE_CLASS_SIGNAL_STRENGTH, ATTR_BATTERY_LEVEL, DEVICE_CLASS_CURRENT, \
    DEVICE_CLASS_VOLTAGE

from . import DOMAIN, EWeLinkRegistry
from .sonoff_main import EWeLinkEntity

try:  # support old Home Assistant version
    from homeassistant.components.sensor import SensorEntity
except:
    from homeassistant.helpers.entity import Entity as SensorEntity

SENSORS = {
    'temperature': [DEVICE_CLASS_TEMPERATURE, '°C', None],
    # UNIT_PERCENTAGE is not on old versions
    'humidity': [DEVICE_CLASS_HUMIDITY, '%', None],
    'dusty': [None, None, 'mdi:cloud'],
    'light': [DEVICE_CLASS_ILLUMINANCE, None, None],
    'noise': [None, None, 'mdi:bell-ring'],
    'power': [DEVICE_CLASS_POWER, 'W', None],
    'current': [DEVICE_CLASS_CURRENT, 'A', None],
    'voltage': [DEVICE_CLASS_VOLTAGE, 'V', None],
    'rssi': [DEVICE_CLASS_SIGNAL_STRENGTH, 'dBm', None]
}

SONOFF_SC = {'temperature', 'humidity', 'dusty', 'light', 'noise'}

GLOBAL_ATTRS = ('local', 'cloud', 'rssi', ATTR_BATTERY_LEVEL)


async def async_setup_platform(hass, config, add_entities,
                               discovery_info=None):
    if discovery_info is None:
        return

    deviceid = discovery_info['deviceid']
    registry = hass.data[DOMAIN]

    attr = discovery_info.get('attribute')
    uiid = registry.devices[deviceid].get('uiid')

    # skip duplicate attribute
    if uiid in (18, 1770) and attr in SONOFF_SC:
        return

    elif attr:
        add_entities([EWeLinkSensor(registry, deviceid, attr)])

    elif uiid == 18:
        add_entities([EWeLinkSensor(registry, deviceid, attr)
                      for attr in SONOFF_SC])

    elif uiid == 1000:
        add_entities([ZigBeeButtonSensor(registry, deviceid)])

    elif uiid == 1770:
        add_entities([EWeLinkSensor(registry, deviceid, 'temperature'),
                      EWeLinkSensor(registry, deviceid, 'humidity')])


class EWeLinkSensor(EWeLinkEntity, SensorEntity):
    _state = None
    # support old Home Assistant version
    _attr_device_class = None
    _attr_unit_of_measurement = None
    _attr_icon = None

    # https://developers.home-assistant.io/docs/core/entity/sensor/#long-term-statistics
    _attr_state_class = "measurement"

    def __init__(self, registry: EWeLinkRegistry, deviceid: str, attr: str):
        super().__init__(registry, deviceid)
        self._attr = attr

        # DUALR3 fix
        strip_attr = self._attr.rstrip('_12')
        if strip_attr in SENSORS:
            self._attr_device_class = SENSORS[strip_attr][0]
            self._attr_unit_of_measurement = SENSORS[strip_attr][1]
            self._attr_icon = SENSORS[strip_attr][2]

    async def async_added_to_hass(self) -> None:
        self._init()

        if self._name:
            self._name += f" {self._attr.replace('_', ' ').capitalize()}"

    def _update_handler(self, state: dict, attrs: dict):
        self._attrs.update({k: attrs[k] for k in GLOBAL_ATTRS if k in attrs})

        if self._attr not in state:
            return

        self._state = state[self._attr]

        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> Optional[str]:
        return f"{self.deviceid}_{self._attr}"

    @property
    def state(self) -> str:
        return self._state

    @property
    def device_class(self):
        return self._attr_device_class

    @property
    def unit_of_measurement(self):
        return self._attr_unit_of_measurement

    @property
    def icon(self):
        return self._attr_icon


BUTTON_STATES = ['single', 'double', 'hold']


class ZigBeeButtonSensor(EWeLinkEntity, SensorEntity):
    _state = ''

    async def async_added_to_hass(self) -> None:
        # don't call update at startup
        self._init(force_refresh=False)

    def _update_handler(self, state: dict, attrs: dict):
        self._attrs.update(attrs)

        if 'key' in state:
            self._state = BUTTON_STATES[state['key']]
            self.async_write_ha_state()
            time.sleep(.5)
            self._state = ''

        self.schedule_update_ha_state()

    @property
    def state(self) -> str:
        return self._state
