import logging

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import SIGNAL_ADD_ENTITIES, XRegistry, XDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, SelectEntity)]),
    )


class XT5Select(XEntity, SelectEntity):
    entity_category = EntityCategory.CONFIG
    _attr_current_option = None
    _attr_options = None

    property: str = None
    effect_name: str = None
    effect_count: int = None

    def __init__(self, ewelink: XRegistry, device: XDevice):
        self._attr_options = ["None"]
        self._attr_options.extend(map(lambda x: f"{self.effect_name} {x+1}", range(self.effect_count)))

        super().__init__(ewelink, device)

    def set_state(self, params: dict):
        effect_params = params[self.param]
        cache = self.device["params"][self.param]
        if cache != effect_params:
            cache.update(effect_params)

        if self.property in effect_params:
            self._attr_current_option = self._attr_options[effect_params[self.property]]

    def get_params(self, option: str) -> dict:
        params = self.device['params'][self.param]
        params[self.property] = self._attr_options.index(option or self._attr_current_option)
        return params

    async def async_select_option(self, option: str) -> None:
        """Update the current selected option."""
        params = self.get_params(option)
        self._attr_current_option = option

        await self.ewelink.send(self.device, {
            self.param: params
        })
