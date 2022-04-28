import asyncio

from homeassistant.components.binary_sensor import BinarySensorEntity, \
    BinarySensorDeviceClass
from homeassistant.components.script import ATTR_LAST_TRIGGERED
from homeassistant.helpers.entity import DeviceInfo

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import XRegistry, SIGNAL_ADD_ENTITIES

PARALLEL_UPDATES = 0  # fix entity_platform parallel_updates Semaphore


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES, lambda x: add_entities(
            [e for e in x if isinstance(e, BinarySensorEntity)]
        )
    )


# noinspection PyUnresolvedReferences
DEVICE_CLASSES = {cls.value: cls for cls in BinarySensorDeviceClass}


# noinspection PyAbstractClass
class XBinarySensor(XEntity, BinarySensorEntity):
    def __init__(self, ewelink: XRegistry, device: dict):
        XEntity.__init__(self, ewelink, device)
        self._attr_device_class = DEVICE_CLASSES.get(
            device.get("device_class")
        )


# noinspection PyAbstractClass
class XWiFiDoor(XBinarySensor):
    params = {"switch"}

    _attr_device_class = BinarySensorDeviceClass.DOOR

    def set_state(self, params: dict):
        self._attr_is_on = params['switch'] == 'on'


# noinspection PyAbstractClass
class XZigbeeMotion(XBinarySensor):
    params = {"motion", "online"}

    _attr_device_class = BinarySensorDeviceClass.MOTION

    def set_state(self, params: dict):
        if "motion" in params:
            self._attr_is_on = params['motion'] == 1
        elif params.get("online") is False:
            # Fix stuck in `on` state after bridge goes to unavailable
            # https://github.com/AlexxIT/SonoffLAN/pull/425
            self._attr_is_on = False


# noinspection PyAbstractClass
class XZigbeeDoor(XBinarySensor):
    params = {"lock"}

    _attr_device_class = BinarySensorDeviceClass.DOOR

    def set_state(self, params: dict):
        self._attr_is_on = params['lock'] == 1


class XWater(XBinarySensor):
    params = {"water"}

    def set_state(self, params: dict):
        self._attr_is_on = params['water'] == 1


# noinspection PyAbstractClass
class XRemoteSensor(BinarySensorEntity):
    task: asyncio.Task = None

    def __init__(self, ewelink: XRegistry, bridge: dict, sensor: dict):
        self.ewelink = ewelink
        self.channel = next(iter(sensor['buttonName'][0]))

        name = sensor["name"]
        try:
            item = ewelink.config["rfbridge"][name]

            self.timeout = item.get("timeout", 120)
            self._attr_device_class = DEVICE_CLASSES.get(
                item.get("device_class")
            )
            self._attr_name = item.get("name", name)

            if "payload_off" in item:
                XRemoteSensorOff.sensors[item["payload_off"]] = self
        except Exception:
            self.timeout = 120
            self._attr_name = name

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, bridge['deviceid'])}
        )
        self._attr_extra_state_attributes = {}
        self._attr_is_on = False
        self._attr_unique_id = f"{bridge['deviceid']}_{self.channel}"

        self.entity_id = DOMAIN + "." + self._attr_unique_id

    def internal_update(self, ts: str):
        if self.task:
            self.task.cancel()

        self._attr_extra_state_attributes = {ATTR_LAST_TRIGGERED: ts}
        self._attr_is_on = True
        self._async_write_ha_state()

        if self.timeout:
            self.task = asyncio.create_task(self.clear_state(self.timeout))

    async def clear_state(self, delay: int):
        await asyncio.sleep(delay)
        self._attr_is_on = False
        self._async_write_ha_state()

    async def async_will_remove_from_hass(self):
        if self.task:
            self.task.cancel()


class XRemoteSensorOff:
    sensors = {}

    def __init__(self, channel: str, name: str, sensor: XRemoteSensor):
        self.channel = channel
        self.name = name
        self.sensor = sensor

    # noinspection PyProtectedMember
    def internal_update(self, ts: str):
        self.sensor._attr_is_on = False
        self.sensor._async_write_ha_state()
