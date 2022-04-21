import asyncio
import time

from homeassistant.components.sensor import SensorEntity, \
    STATE_CLASS_MEASUREMENT
from homeassistant.const import *
from homeassistant.util import dt

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import XRegistry, SIGNAL_ADD_ENTITIES


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, SensorEntity)])
    )


UNITS = {
    "battery": PERCENTAGE,
    "current": ELECTRIC_CURRENT_AMPERE,
    "humidity": PERCENTAGE,
    "power": POWER_WATT,
    "rssi": SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    "temperature": TEMP_CELSIUS,
    "voltage": ELECTRIC_POTENTIAL_VOLT,
}


class XSensor(XEntity, SensorEntity):
    """Class can convert string sensor value to float, multiply it and round if
    needed. Also class can filter incoming values using zigbee-like reporting
    logic: min report interval, max report interval, reportable change value.
    """
    multiply = None
    round = None

    report_ts = None
    report_mint = None
    report_maxt = None
    report_delta = None
    report_value = None

    def __init__(self, ewelink: XRegistry, device: dict):
        super().__init__(ewelink, device)

        if self.uid in UNITS:
            # by default all sensors with units is measurement sensors
            self._attr_state_class = STATE_CLASS_MEASUREMENT
            self._attr_native_unit_of_measurement = UNITS[self.uid]

        reporting = device.get("reporting", {}).get(self.uid)
        if reporting:
            self.report_mint, self.report_maxt, self.report_delta = reporting
            self.report_ts = time.time()
            self._attr_force_update = True

    def set_state(self, params: dict = None):
        try:
            value = float(params[self.param])
            if self.multiply:
                value *= self.multiply
            if self.round is not None:
                # convert to int when round is zero
                value = round(value, self.round or None)
        except (TypeError, ValueError):
            value = self.report_value

        if self.report_ts is not None:
            ts = time.time()

            if (ts - self.report_ts < self.report_mint) or (
                    ts - self.report_ts < self.report_maxt and
                    value is not None and
                    self._attr_native_value is not None and
                    abs(value - self._attr_native_value) <= self.report_delta
            ):
                self.report_value = value
                return

            self.report_value = None
            self.report_ts = ts

        self._attr_native_value = value

    async def async_update(self):
        if self.report_value is not None:
            self.set_state()


BUTTON_STATES = ["single", "double", "hold"]


class XZigbeeButton(XEntity, SensorEntity):
    def __init__(self, ewelink: XRegistry, device: dict):
        super().__init__(ewelink, device)
        self.params = {"key"}
        self._attr_native_value = ""

    def set_state(self, params: dict):
        self._attr_native_value = BUTTON_STATES[params["key"]]
        asyncio.create_task(self.clear_state())

    async def clear_state(self):
        await asyncio.sleep(.5)
        self._attr_native_value = ""
        self._async_write_ha_state()


class XUnknown(XEntity, SensorEntity):
    _attr_device_class = DEVICE_CLASS_TIMESTAMP

    def internal_update(self, params: dict = None):
        self._attr_native_value = dt.utcnow()

        if params is not None:
            params.pop("bindInfos", None)
            self._attr_extra_state_attributes = params

        if self.hass:
            self._async_write_ha_state()
