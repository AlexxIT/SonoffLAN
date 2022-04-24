from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import *
from homeassistant.const import TEMP_CELSIUS

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import XRegistry, SIGNAL_ADD_ENTITIES


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, ClimateEntity)])
    )


# noinspection PyAbstractClass
class XClimateTH(XEntity, ClimateEntity):
    params = {"targets", "deviceType", "currentTemperature", "temperature"}

    _attr_entity_registry_enabled_default = False
    _attr_hvac_modes = [
        HVAC_MODE_OFF, HVAC_MODE_HEAT, HVAC_MODE_COOL, HVAC_MODE_DRY
    ]
    _attr_max_temp = 99
    _attr_min_temp = 1
    _attr_supported_features = SUPPORT_TARGET_TEMPERATURE_RANGE
    _attr_temperature_unit = TEMP_CELSIUS
    _attr_target_temperature_step = 1

    heat: bool = None

    def set_state(self, params: dict):
        if "targets" in params:
            hi, lo = params["targets"]

            self._attr_is_aux_heat = lo["reaction"]["switch"] == "on"
            self._attr_target_temperature_high = float(hi["targetHigh"])
            self._attr_target_temperature_low = float(lo["targetLow"])

            if params["deviceType"] == "normal":
                self._attr_hvac_mode = HVAC_MODE_OFF
            elif params["deviceType"] == "humidity":
                self._attr_hvac_mode = HVAC_MODE_DRY
            elif self.is_aux_heat:
                self._attr_hvac_mode = HVAC_MODE_HEAT
            else:
                self._attr_hvac_mode = HVAC_MODE_COOL

        try:
            if self.hvac_mode != HVAC_MODE_DRY:
                value = float(
                    params.get("currentTemperature") or params["temperature"]
                )
                value = round(value, 1)
            else:
                value = int(
                    params.get("currentHumidity") or params["humidity"]
                )
            self._attr_current_temperature = value
        except Exception:
            pass

    def get_targets(self, heat: bool) -> list:
        return [{
            "targetHigh": str(self.target_temperature_high),
            "reaction": {"switch": "off" if heat else "on"}
        }, {
            "targetLow": str(self.target_temperature_low),
            "reaction": {"switch": "on" if heat else "off"}
        }]

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        if hvac_mode == HVAC_MODE_HEAT:
            params = {
                "mainSwitch": "on", "deviceType": "temperature",
                "targets": self.get_targets(True)
            }
        elif hvac_mode == HVAC_MODE_COOL:
            params = {
                "mainSwitch": "on", "deviceType": "temperature",
                "targets": self.get_targets(False)
            }
        elif hvac_mode == HVAC_MODE_DRY:
            params = {
                "mainSwitch": "on", "deviceType": "humidity",
                "targets": self.get_targets(self.is_aux_heat)
            }
        else:
            params = {"mainSwitch": "off", "deviceType": "normal"}
        await self.ewelink.cloud.send(self.device, params)

    async def async_set_temperature(
            self, target_temp_high: float, target_temp_low: float,
            hvac_mode: str = None, **kwargs
    ) -> None:
        heat = self.is_aux_heat
        if hvac_mode is None:
            params = {}
        elif hvac_mode == HVAC_MODE_HEAT:
            heat = True
            params = {"mainSwitch": "on", "deviceType": "temperature"}
        elif hvac_mode == HVAC_MODE_COOL:
            heat = False
            params = {"mainSwitch": "on", "deviceType": "temperature"}
        elif hvac_mode == HVAC_MODE_DRY:
            params = {"mainSwitch": "on", "deviceType": "humidity"}
        else:
            params = {"mainSwitch": "off", "deviceType": "normal"}

        params["targets"] = [{
            "targetHigh": str(target_temp_high),
            "reaction": {"switch": "off" if heat else "on"}
        }, {
            "targetLow": str(target_temp_low),
            "reaction": {"switch": "on" if heat else "off"}
        }]

        await self.ewelink.cloud.send(self.device, params)
