from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import DeviceInfo, Entity, EntityCategory

from .const import DOMAIN
from .ewelink import XRegistry

DEVICE_CLASSES = {
    "battery": SensorDeviceClass.BATTERY,
    "current": SensorDeviceClass.CURRENT,
    "current_1": SensorDeviceClass.CURRENT,
    "current_2": SensorDeviceClass.CURRENT,
    "humidity": SensorDeviceClass.HUMIDITY,
    "power": SensorDeviceClass.POWER,
    "power_1": SensorDeviceClass.POWER,
    "power_2": SensorDeviceClass.POWER,
    "rssi": SensorDeviceClass.SIGNAL_STRENGTH,
    "temperature": SensorDeviceClass.TEMPERATURE,
    "voltage": SensorDeviceClass.VOLTAGE,
    "voltage_1": SensorDeviceClass.VOLTAGE,
    "voltage_2": SensorDeviceClass.VOLTAGE,
}

ENTITY_CATEGORIES = {
    "battery": EntityCategory.DIAGNOSTIC,
    "led": EntityCategory.CONFIG,
    "rssi": EntityCategory.DIAGNOSTIC,
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
    params: set = {}
    param: str = None
    uid: str = None

    # fix Hass v2021.12 empty attribute bug
    _attr_is_on = None

    def __init__(self, ewelink: XRegistry, device: dict):
        self.ewelink = ewelink
        self.device = device

        if self.param and self.uid is None:
            self.uid = self.param
        if self.param and not self.params:
            self.params = {self.param}

        if self.uid:
            self._attr_unique_id = f"{device['deviceid']}_{self.uid}"

            if not self.uid.isdigit():
                self._attr_device_class = DEVICE_CLASSES.get(self.uid)
                self._attr_entity_category = ENTITY_CATEGORIES.get(self.uid)
                self._attr_icon = ICONS.get(self.uid)

                s = NAMES.get(self.uid) or self.uid.title().replace("_", " ")
                self._attr_name = f"{device['name']} {s}"
            else:
                self._attr_name = device["name"]

        else:
            self._attr_name = device["name"]
            self._attr_unique_id = device["deviceid"]

        self._attr_should_poll = False

        # domain will be replaced in entity_registry.async_generate_entity_id
        self.entity_id = f"{DOMAIN}.{DOMAIN}_{self._attr_unique_id}"

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
