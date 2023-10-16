import asyncio
import time
from typing import Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    ELECTRIC_CURRENT_AMPERE,
    ELECTRIC_POTENTIAL_VOLT,
    ENERGY_KILO_WATT_HOUR,
    PERCENTAGE,
    POWER_WATT,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    TEMP_CELSIUS,
)
from homeassistant.util import dt

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import SIGNAL_ADD_ENTITIES, XRegistry

PARALLEL_UPDATES = 0  # fix entity_platform parallel_updates Semaphore


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, SensorEntity)]),
    )


DEVICE_CLASSES = {
    "battery": SensorDeviceClass.BATTERY,
    "battery_voltage": SensorDeviceClass.VOLTAGE,
    "current": SensorDeviceClass.CURRENT,
    "humidity": SensorDeviceClass.HUMIDITY,
    "outdoor_temp": SensorDeviceClass.TEMPERATURE,
    "power": SensorDeviceClass.POWER,
    "rssi": SensorDeviceClass.SIGNAL_STRENGTH,
    "temperature": SensorDeviceClass.TEMPERATURE,
    "voltage": SensorDeviceClass.VOLTAGE,
}

UNITS = {
    "battery": PERCENTAGE,
    "battery_voltage": ELECTRIC_POTENTIAL_VOLT,
    "current": ELECTRIC_CURRENT_AMPERE,
    "humidity": PERCENTAGE,
    "outdoor_temp": TEMP_CELSIUS,
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

    multiply: float = None
    round: int = None

    report_ts = None
    report_mint = None
    report_maxt = None
    report_delta = None
    report_value = None

    def __init__(self, ewelink: XRegistry, device: dict):
        if self.param and self.uid is None:
            self.uid = self.param

        default_class = (
            self.uid[:-2] if self.uid.endswith(("_1", "_2", "_3", "_4")) else self.uid
        )
        self._attr_device_class = DEVICE_CLASSES.get(default_class)

        if default_class in UNITS:
            # by default all sensors with units is measurement sensors
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = UNITS[default_class]

        XEntity.__init__(self, ewelink, device)

        reporting = device.get("reporting", {}).get(self.uid)
        if reporting:
            self.report_mint, self.report_maxt, self.report_delta = reporting
            self.report_ts = time.time()
            self._attr_should_poll = True

    def set_state(self, params: dict = None, value: float = None):
        if params:
            value = params[self.param]
            if self.native_unit_of_measurement and isinstance(value, str):
                try:
                    # https://github.com/AlexxIT/SonoffLAN/issues/1061
                    value = float(value)
                except Exception:
                    return
            if self.multiply:
                value *= self.multiply
            if self.round is not None:
                # convert to int when round is zero
                value = round(value, self.round or None)

        if self.report_ts is not None:
            ts = time.time()

            try:
                if (ts - self.report_ts < self.report_mint) or (
                    ts - self.report_ts < self.report_maxt
                    and abs(value - self.native_value) <= self.report_delta
                ):
                    self.report_value = value
                    return

                self.report_value = None
            except Exception:
                pass

            self.report_ts = ts

        self._attr_native_value = value

    async def async_update(self):
        if self.report_value is not None:
            XSensor.set_state(self, value=self.report_value)


class XTemperatureTH(XSensor):
    params = {"currentTemperature", "temperature"}
    uid = "temperature"

    def set_state(self, params: dict = None, value: float = None):
        try:
            # can be int, float, str or undefined
            value = params.get("currentTemperature") or params["temperature"]
            value = float(value)
            # filter zero values
            # https://github.com/AlexxIT/SonoffLAN/issues/110
            # filter wrong values
            # https://github.com/AlexxIT/SonoffLAN/issues/683
            if value != 0 and -270 < value < 270:
                XSensor.set_state(self, value=round(value, 1))
        except Exception:
            XSensor.set_state(self)


class XHumidityTH(XSensor):
    params = {"currentHumidity", "humidity"}
    uid = "humidity"

    def set_state(self, params: dict = None, value: float = None):
        try:
            value = params.get("currentHumidity") or params["humidity"]
            value = float(value)
            # filter zero values
            # https://github.com/AlexxIT/SonoffLAN/issues/110
            if value != 0:
                XSensor.set_state(self, value=value)
        except Exception:
            XSensor.set_state(self)


class XEnergySensor(XEntity, SensorEntity):
    get_params = None
    next_ts = 0

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_entity_registry_enabled_default = False
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_should_poll = True

    def __init__(self, ewelink: XRegistry, device: dict):
        XEntity.__init__(self, ewelink, device)
        reporting = device.get("reporting", {})
        self.report_dt, self.report_history = reporting.get(self.uid) or (3600, 0)

    @staticmethod
    def decode_energy(value: str) -> Optional[list]:
        try:
            return [
                round(
                    int(value[i : i + 2], 16)
                    + int(value[i + 3], 10) * 0.1
                    + int(value[i + 5], 10) * 0.01,
                    2,
                )
                for i in range(0, len(value), 6)
            ]
        except Exception:
            return None

    def set_state(self, params: dict):
        history = self.decode_energy(params[self.param])
        if not history:
            return

        self._attr_native_value = history[0]

        if self.report_history:
            self._attr_extra_state_attributes = {
                "history": history[0 : self.report_history]
            }

    async def async_update(self):
        ts = time.time()
        if ts < self.next_ts or not self.available or not self.ewelink.cloud.online:
            return
        ok = await self.ewelink.send_cloud(self.device, self.get_params, query=False)
        if ok == "online":
            self.next_ts = ts + self.report_dt


class XEnergySensorDualR3(XEnergySensor, SensorEntity):
    @staticmethod
    def decode_energy(value: str) -> Optional[list]:
        try:
            return [
                round(
                    int(value[i : i + 2], 16) + int(value[i + 2 : i + 4], 10) * 0.01, 2
                )
                for i in range(0, len(value), 4)
            ]
        except Exception:
            return None


class XEnergySensorPOWR3(XEnergySensor, SensorEntity):
    @staticmethod
    def decode_energy(value: str) -> Optional[list]:
        try:
            return [
                round(int(value[i], 16) + int(value[i + 1 : i + 3], 10) * 0.01, 2)
                for i in range(0, len(value), 3)
            ]
        except Exception:
            return None

    async def async_update(self):
        ts = time.time()
        if ts < self.next_ts or not self.available:
            return
        # POWR3 support LAN energy request (POST /zeroconf/getHoursKwh)
        ok = await self.ewelink.send(self.device, self.get_params, timeout_lan=5)
        if ok == "online":
            self.next_ts = ts + self.report_dt


class XEnergyTotal(XSensor):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL


class XTemperatureNS(XSensor):
    params = {"temperature", "tempCorrection"}
    uid = "temperature"

    def set_state(self, params: dict = None, value: float = None):
        if params:
            # cache updated in XClimateNS entity
            cache = self.device["params"]
            value = cache["temperature"] + cache.get("tempCorrection", 0)
        XSensor.set_state(self, value=value)


class XOutdoorTempNS(XSensor):
    param = "HMI_outdoorTemp"
    uid = "outdoor_temp"

    # noinspection PyMethodOverriding
    def set_state(self, params: dict):
        try:
            value = params[self.param]
            self._attr_native_value = value["current"]

            mint, maxt = value["range"].split(",")
            self._attr_extra_state_attributes = {
                "temp_min": int(mint),
                "temp_max": int(maxt),
            }
        except Exception:
            pass


class XWiFiDoorBattery(XSensor):
    param = "battery"
    uid = "battery_voltage"

    def internal_available(self) -> bool:
        # device with buggy online status
        return self.ewelink.cloud.online


BUTTON_STATES = ["single", "double", "hold"]


class XRemoteButton(XEntity, SensorEntity):
    _attr_native_value = ""

    def __init__(self, ewelink: XRegistry, device: dict):
        XEntity.__init__(self, ewelink, device)
        self.params = {"key"}

    def set_state(self, params: dict):
        button = params.get("outlet")
        key = BUTTON_STATES[params["key"]]
        self._attr_native_value = (
            f"button_{button + 1}_{key}" if button is not None else key
        )
        asyncio.create_task(self.clear_state())

    async def clear_state(self):
        await asyncio.sleep(0.5)
        self._attr_native_value = ""
        self._async_write_ha_state()


class XT5Action(XEntity, SensorEntity):
    uid = "action"
    _attr_native_value = ""

    def __init__(self, ewelink: XRegistry, device: dict):
        XEntity.__init__(self, ewelink, device)
        self.params = {"triggerType", "slide"}

    def set_state(self, params: dict):
        if params.get("triggerType") == 2:
            self._attr_native_value = "touch"
            asyncio.create_task(self.clear_state())

        if slide := params.get("slide"):
            self._attr_native_value = f"slide_{slide}"
            asyncio.create_task(self.clear_state())

    async def clear_state(self):
        await asyncio.sleep(0.5)
        self._attr_native_value = ""
        self._async_write_ha_state()


class XUnknown(XEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def internal_update(self, params: dict = None):
        self._attr_native_value = dt.utcnow()

        if params is not None:
            params.pop("bindInfos", None)
            self._attr_extra_state_attributes = params

        if self.hass:
            self._async_write_ha_state()
