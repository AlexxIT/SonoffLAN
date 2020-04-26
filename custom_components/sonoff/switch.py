from . import DOMAIN
from .toggle import EWeLinkToggle


async def async_setup_platform(hass, config, add_entities,
                               discovery_info=None):
    if discovery_info is None:
        return

    deviceid = discovery_info['deviceid']
    channels = discovery_info['channels']
    device = hass.data[DOMAIN][deviceid]
    add_entities([EWeLinkToggle(device, channels)])
