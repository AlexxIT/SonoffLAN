from homeassistant.const import *
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import Entity, DeviceInfo

from .backward import ENTITY_CATEGORY_CONFIG, ENTITY_CATEGORY_DIAGNOSTIC
from .const import DOMAIN
from .ewelink import XRegistry

DEVICE_CLASSES = {
    "battery": DEVICE_CLASS_BATTERY,
    "current": DEVICE_CLASS_CURRENT,
    "current_1": DEVICE_CLASS_CURRENT,
    "current_2": DEVICE_CLASS_CURRENT,
    "humidity": DEVICE_CLASS_HUMIDITY,
    "power": DEVICE_CLASS_POWER,
    "power_1": DEVICE_CLASS_POWER,
    "power_2": DEVICE_CLASS_POWER,
    "rssi": DEVICE_CLASS_SIGNAL_STRENGTH,
    "temperature": DEVICE_CLASS_TEMPERATURE,
    "voltage": DEVICE_CLASS_VOLTAGE,
    "voltage_1": DEVICE_CLASS_VOLTAGE,
    "voltage_2": DEVICE_CLASS_VOLTAGE,
}

ENTITY_CATEGORIES = {
    "battery": ENTITY_CATEGORY_DIAGNOSTIC,
    "led": ENTITY_CATEGORY_CONFIG,
    "rssi": ENTITY_CATEGORY_DIAGNOSTIC,
}

ICONS = {
    "dusty": "mdi:cloud",
    "led": "mdi:led-off",
    "noise": "mdi:bell-ring",
}

NAMES = {
    "led": "LED",
    "rssi": "RSSI",
}


class XEntity(Entity):
    params: set = None
    param: str = None
    uid: str = None

    def __init__(self, ewelink: XRegistry, device: dict):
        self.ewelink = ewelink
        self.device = device

        if self.param and self.uid is None:
            self.uid = self.param
        if self.param and self.params is None:
            self.params = {self.param}

        if self.uid:
            self._attr_device_class = DEVICE_CLASSES.get(self.uid)
            self._attr_entity_category = ENTITY_CATEGORIES.get(self.uid)
            self._attr_icon = ICONS.get(self.uid)

            s = NAMES.get(self.uid) or self.uid.title()
            self._attr_name = f"{device['name']} {s}"
            self._attr_unique_id = f"{device['deviceid']}_{self.uid}"

        else:
            self._attr_name = device["name"]
            self._attr_unique_id = device["deviceid"]

        self.entity_id = DOMAIN + "." + self._attr_unique_id

        deviceid: str = device['deviceid']
        params: dict = device['params']

        connections = {(CONNECTION_NETWORK_MAC, params['staMac'])} \
            if "staMac" in params else None

        self._attr_device_info = DeviceInfo(
            connections=connections,
            identifiers={(DOMAIN, deviceid)},
            manufacturer=device.get('brandName'),
            model=device.get('productModel'),
            name=device["name"],
            sw_version=params.get('fwVersion'),
        )

        self.internal_update(params)
        ewelink.dispatcher_connect(deviceid, self.internal_update)

    def set_state(self, params: dict):
        pass

    def internal_update(self, params: dict = None):
        available = (self.ewelink.cloud.online and self.device["online"]) or \
                    (self.ewelink.local.online and "host" in self.device)
        change = False

        if self._attr_available != available:
            self._attr_available = available
            change = True

        if params and params.keys() & self.params:
            self.set_state(params)
            change = True

        if change and self.hass:
            self._async_write_ha_state()
