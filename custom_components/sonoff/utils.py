import logging

_LOGGER = logging.getLogger(__name__)


def init_zeroconf_singleton(hass):
    """Generate only one Zeroconf. Component must be loaded before Zeroconf."""
    from homeassistant.components import zeroconf
    if isinstance(zeroconf.Zeroconf, type):
        def zeroconf_singleton():
            if 'zeroconf' not in hass.data:
                from zeroconf import Zeroconf
                _LOGGER.debug("Generate zeroconf singleton")
                hass.data['zeroconf'] = Zeroconf()
            else:
                _LOGGER.debug("Use zeroconf singleton")
            return hass.data['zeroconf']

        _LOGGER.debug("Init zeroconf singleton")
        zeroconf.Zeroconf = zeroconf_singleton


UIIDS = {}
TYPES = {}


def init_device_class(default_class: str = 'switch'):
    switch1 = default_class
    switch2 = [default_class, default_class]
    switch3 = [default_class, default_class, default_class]
    switch4 = [default_class, default_class, default_class, default_class]
    switchx = [default_class]

    UIIDS.update({
        1: switch1,
        2: switch2,
        3: switch3,
        4: switch4,
        5: switch1,
        6: switch1,
        7: switch2,
        8: switch3,
        9: switch4,
        11: 'cover',  # King Art - King Q4 Cover (only cloud)
        22: 'light',  # Sonoff B1 (only cloud)
        28: 'remote',  # Sonoff RF Brigde 433
        29: switch2,
        30: switch3,
        31: switch4,
        34: ['light', {'fan': [2, 3, 4]}],  # Sonoff iFan02 and iFan03
        36: 'light',  # KING-M4 (dimmer, only cloud)
        44: 'light',  # Sonoff D1
        59: 'light',  # Sonoff LED (only cloud)
        77: switchx,  # Sonoff Micro
        78: switchx,
        81: switch1,
        82: switch2,
        83: switch3,
        84: switch4,
        107: switchx
    })

    TYPES.update({
        'plug': switch1,  # Basic, Mini
        'diy_plug': switch1,  # Mini in DIY mode
        'enhanced_plug': switch1,  # Sonoff Pow R2?
        'th_plug': switch1,  # Sonoff TH?
        'strip': switch4,  # 4CH Pro R2, Micro!, iFan02!
        'light': 'light',  # D1
        'rf': 'remote',  # RF Bridge 433
        'fan_light': ['light', 'fan'],  # iFan03
    })


def guess_device_class(config: dict):
    """Get device_class from uiid (from eWeLink Servers) or from zeroconf type.

    Sonoff iFan02 and iFan03 both have uiid 34. But different types (strip and
    fan_light) and different local API for each type. Without uiid iFan02 will
    be displayed as 4 switches.
    """
    uiid = config.get('uiid')
    type_ = config.get('type')
    return UIIDS.get(uiid) or TYPES.get(type_)
