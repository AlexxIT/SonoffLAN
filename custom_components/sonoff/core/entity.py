"""Base entity class for Sonoff devices."""
import logging

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import DeviceInfo, Entity, EntityCategory

from .const import DOMAIN
from .ewelink import XDevice, XRegistry

_LOGGER = logging.getLogger(__name__)

ENTITY_CATEGORIES = {
    "battery": EntityCategory.DIAGNOSTIC,
    "battery_voltage": EntityCategory.DIAGNOSTIC,
    "led": EntityCategory.CONFIG,
    "pulse": EntityCategory.CONFIG,
    "pulseWidth": EntityCategory.CONFIG,
    "rssi": EntityCategory.DIAGNOSTIC,
    "sensitivity": EntityCategory.CONFIG,
}

ICONS = {
    "dusty": "mdi:cloud",
    "led": "mdi:led-off",
    "noise": "mdi:bell-ring",
}

NAMES = {
    "led": "LED",
    "rssi": "RSSI",
    "pulse": "INCHING",
    "pulseWidth": "INCHING Duration",
}


def clean_device_name(name: str) -> str:
    """Cihaz adını temizle (Türkçe karakter + özel karakter)."""
    # Büyük harf Türkçe karakterler
    name = name.replace('Ü', 'U').replace('İ', 'I').replace('Ğ', 'G').replace('Ş', 'S').replace('Ç', 'C').replace('Ö', 'O')
    # Küçük harf Türkçe karakterler  
    name = name.replace('ü', 'u').replace('ı', 'i').replace('ğ', 'g').replace('ş', 's').replace('ç', 'c').replace('ö', 'o')
    # Özel karakterleri temizle
    name = name.replace('(', '').replace(')', '').replace('&', 'and').replace('/', '_').replace(':', '')
    # Son olarak boşlukları ve kısa çizgileri alt çizgi yap ve küçük harfe çevir
    name = name.replace(' ', '_').replace('-', '_').lower()
    return name


class XEntity(Entity):
    event: bool = False  # if True - skip set_state on entity init
    params: set = {}
    param: str = None
    uid: str = None

    _attr_should_poll = False

    def __init__(self, ewelink: XRegistry, device: XDevice) -> None:
        self.ewelink = ewelink
        self.device = device

        if self.param and self.uid is None:
            self.uid = self.param
        if self.param and not self.params:
            self.params = {self.param}

        # TÜM ENTİTY'LER İÇİN ORTAK: Cihaz adını temizle
        device_name = clean_device_name(device["name"])
        device_id = device["deviceid"]

        if self.uid:
            # SENSOR, MULTI-SWITCH, LED vs. için
            if not self.uid.isdigit():
                self._attr_entity_category = ENTITY_CATEGORIES.get(self.uid)
                self._attr_icon = ICONS.get(self.uid)
                s = NAMES.get(self.uid) or self.uid.title().replace("_", " ")
                self._attr_name = f"{device['name']} {s}"
                # SENSOR, LED vs: salon_lamba_1000xxx_current
                self._attr_unique_id = f"{device_name}_{device_id}_{self.uid}"
            else:
                self._attr_name = device["name"]
                # MULTI-SWITCH: salon_lamba_1000xxx_1
                self._attr_unique_id = f"{device_name}_{device_id}_{self.uid}"

        else:
            # TEK SWITCH/COVER/CLIMATE vs.
            self._attr_name = device["name"]
            # TEK CİHAZ: salon_lamba_1000xxx
            self._attr_unique_id = f"{device_name}_{device_id}"

        # LEVONISYAS DÜZENLEMESİ: Entity ID formatı
        self.entity_id = f"{DOMAIN}.{self._attr_unique_id.lower()}"

        deviceid: str = device["deviceid"]
        params: dict = device["params"]

        connections = (
            {(CONNECTION_NETWORK_MAC, params["staMac"])} if "staMac" in params else None
        )

        self._attr_device_info = DeviceInfo(
            connections=connections,
            identifiers={(DOMAIN, deviceid)},
            manufacturer=device.get("brandName"),
            model=device.get("productModel"),
            name=device["name"],
            sw_version=params.get("fwVersion"),
        )

        try:
            self.internal_update(None if self.event else params)
        except Exception as e:
            _LOGGER.error(f"Can't init device: {device}", exc_info=e)

        ewelink.dispatcher_connect(deviceid, self.internal_update)

        if parent := device.get("parent"):
            ewelink.dispatcher_connect(parent["deviceid"], self.internal_parent_update)

    def set_state(self, params: dict):
        pass

    def internal_available(self) -> bool:
        ok = self.ewelink.can_cloud(self.device) or self.ewelink.can_local(self.device)
        return ok

    def internal_update(self, params: dict = None):
        available = self.internal_available()
        change = False

        if self._attr_available != available:
            self._attr_available = available
            change = True

        if params and params.keys() & self.params:
            self.set_state(params)
            change = True

        if change and self.hass:
            self._async_write_ha_state()

    def internal_parent_update(self, params: dict = None):
        self.internal_update(None)

    async def async_update(self):
        if led := self.device["params"].get("sledOnline"):
            # device response with current status if we change any param
            await self.ewelink.send(
                self.device, params_lan={"sledOnline": led}, cmd_lan="sledonline"
            )
        else:
            await self.ewelink.send(self.device)
