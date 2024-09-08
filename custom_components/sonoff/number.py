from homeassistant.components.number import NumberEntity

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import SIGNAL_ADD_ENTITIES, XRegistry

PARALLEL_UPDATES = 0  # fix entity_platform parallel_updates Semaphore


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, NumberEntity)]),
    )


# noinspection PyAbstractClass
class XNumber(XEntity, NumberEntity):
    multiply: float = None
    round: int = None

    def set_state(self, params: dict):
        value = params[self.param]
        if self.multiply:
            value *= self.multiply
        if self.round is not None:
            # convert to int when round is zero
            value = round(value, self.round or None)
        self._attr_native_value = value

    async def async_set_native_value(self, value: float) -> None:
        if self.multiply:
            value /= self.multiply
        await self.ewelink.send(self.device, {self.param: int(value)})


class XPulseWidth(XNumber):
    param = "pulseWidth"

    _attr_entity_registry_enabled_default = False

    _attr_native_max_value = 36000
    _attr_native_min_value = 0.5
    _attr_native_step = 0.5

    def set_state(self, params: dict):
        self._attr_native_value = params["pulseWidth"] / 1000

    async def async_set_native_value(self, value: float) -> None:
        """
        we need to send {'pulse': 'on'}  in order to also set the pilseWidth
        else it'll reject the command
        also, since value is in (float) seconds, ensure we send milliseconds
        in 500 multiples (int(value / .5) * 500)
        """
        await self.ewelink.send(
            self.device, {"pulse": "on", "pulseWidth": int(value / 0.5) * 500}
        )


class XSensitivity(XNumber):
    param = "sensitivity"

    _attr_entity_registry_enabled_default = False
    _attr_native_max_value = 3
    _attr_native_min_value = 1
