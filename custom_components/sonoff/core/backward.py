"""Backward support for older Hass versions."""
from homeassistant.const import MAJOR_VERSION, MINOR_VERSION

# from v2021.7 important to using Entity attributes
# https://github.com/home-assistant/core/blob/933e0161501ffc160fb9009baf0112eabbae17f7/homeassistant/helpers/entity.py#L223-L238
hass_version_supported = (MAJOR_VERSION, MINOR_VERSION) >= (2021, 7)

# EntityCategory support from v2021.12
# https://github.com/home-assistant/core/blob/604a2ac3270bc51f050e0f7a7ce5079bf6da5225/homeassistant/helpers/entity.py#L183
if (MAJOR_VERSION, MINOR_VERSION) >= (2021, 12):
    from homeassistant.helpers.entity import EntityCategory

    ENTITY_CATEGORY_CONFIG = EntityCategory.CONFIG
    ENTITY_CATEGORY_DIAGNOSTIC = EntityCategory.DIAGNOSTIC
else:
    ENTITY_CATEGORY_CONFIG = "config"
    ENTITY_CATEGORY_DIAGNOSTIC = "diagnostic"
