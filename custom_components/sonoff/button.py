import asyncio

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.components.script import ATTR_LAST_TRIGGERED
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import SIGNAL_ADD_ENTITIES, XRegistry

PARALLEL_UPDATES = 0  # fix entity_platform parallel_updates Semaphore


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, ButtonEntity)]),
    )


# supported in Hass v2021.12
# noinspection PyAbstractClass
class XRemoteButton(ButtonEntity):
    def __init__(self, ewelink: XRegistry, bridge: dict, child: dict):
        self.ewelink = ewelink
        self.bridge = bridge
        self.channel = child["channel"]

        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, bridge["deviceid"])})
        self._attr_extra_state_attributes = {}
        self._attr_name = child["name"]
        self._attr_unique_id = f"{bridge['deviceid']}_{self.channel}"

        # Use button domain to match the entity's platform.
        # https://github.com/AlexxIT/SonoffLAN/issues/1787
        self.entity_id = "button." + self._attr_unique_id

    def internal_update(self, ts: str):
        self._attr_extra_state_attributes = {ATTR_LAST_TRIGGERED: ts}
        self._async_write_ha_state()

    async def async_press(self):
        await self.ewelink.send(
            self.bridge,
            {"cmd": "transmit", "rfChl": int(self.channel)},
            cmd_lan="transmit",
        )


class XButton(XEntity, ButtonEntity):
    value = None

    def __init__(self, ewelink: XRegistry, device: dict):
        XEntity.__init__(self, ewelink, device)

        if self.params == "reboot":
            self._attr_device_class = ButtonDeviceClass.RESTART
            self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self):
        await self.ewelink.send(self.device, {self.param: self.value})


class XT5Effect(XEntity, ButtonEntity):
    uid = "effect"

    async def async_press(self):
        if pre := self.device["params"].get("preEffects"):
            await self.ewelink.send(self.device, {"preEffects": pre})


class XAlarmButton(XEntity, ButtonEntity):
    """SNZB-09P (uiid 7056) - triggers the siren (confirmed working).

    Sends `alarmSetting.test = true`. The device turns it back off on its
    own once the configured Alarm Duration elapses, so no reset is sent.
    """

    params = {"alarmSetting"}
    uid = "allarme"
    _attr_icon = "mdi:bullhorn"

    async def async_press(self):
        setting = dict(self.device["params"].get("alarmSetting", {}))
        setting["test"] = True
        await self.ewelink.send(self.device, {"alarmSetting": setting})


class XCalibrateButton(XEntity, ButtonEntity):
    """MINI-RBS (uiid 258) - starts the roller shutter travel calibration.

    Same procedure as the eWeLink app: reset (`calibration=0`), then start
    (`calibration=3`). The motor then runs the full travel by itself (about
    two minutes) and ends with `calibState=1`. Works over LAN and Cloud.
    """

    params = {"calibState"}
    uid = "calibrate"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:ruler"
    _attr_entity_registry_enabled_default = False

    async def async_press(self):
        await self.ewelink.send(self.device, {"calibration": 0}, cmd_lan="calibration")
        await asyncio.sleep(3)
        await self.ewelink.send(self.device, {"calibration": 3}, cmd_lan="calibration")
