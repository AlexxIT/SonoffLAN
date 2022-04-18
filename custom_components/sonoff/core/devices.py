"""
Each device has a specification - list of classes (XEntity childs)

XEntity properties:
- params - required, set of parameters that this entity can read
- param - optional, entity main parameter (useful for sensors)
- uid - optional, entity unique_id tail

`spec` - function can change default class with some options
"""
from typing import Optional

from ..cover import XCover
from ..fan import XFan, XDiffuserFan
from ..light import *
from ..sensor import XSensor, XSensor100
from ..switch import XSwitch, XSwitches, XSwitchTH, XToggle


def spec(cls, enabled=None, **kwargs):
    if enabled is not None:
        kwargs["_attr_entity_registry_enabled_default"] = enabled
    return type(cls.__name__, (cls,), {**cls.__dict__, **kwargs})


Switch1 = spec(XSwitches, channel=0, uid="1")
Switch2 = spec(XSwitches, channel=1, uid="2")
Switch3 = spec(XSwitches, channel=2, uid="3")
Switch4 = spec(XSwitches, channel=3, uid="4")
LED = spec(XToggle, param="sledOnline", uid="led", enabled=False)
RSSI = spec(XSensor, param="rssi", enabled=False)

SPEC_SWITCH = [XSwitch, LED, RSSI]
SPEC_1CH = [Switch1]
SPEC_2CH = [Switch1, Switch2]
SPEC_3CH = [Switch1, Switch2, Switch3]
SPEC_4CH = [Switch1, Switch2, Switch3, Switch4]

DEVICES = {
    1: SPEC_SWITCH,
    2: SPEC_2CH,
    3: SPEC_3CH,
    4: SPEC_4CH,
    5: SPEC_SWITCH,  # Sonoff Pow
    6: SPEC_SWITCH,
    7: SPEC_2CH,  # Sonoff T1 2CH
    8: SPEC_3CH,  # Sonoff T1 3CH
    9: SPEC_4CH,
    11: [XCover, LED, RSSI],  # King Art - King Q4 Cover (only cloud)
    14: SPEC_SWITCH,  # Sonoff Basic (3rd party)
    15: [
        XSwitchTH, LED, RSSI,
        spec(XSensor, param="currentTemperature", uid="temperature"),
        spec(XSensor, param="currentHumidity", uid="humidity"),
    ],  # Sonoff TH16
    22: [XLightB1],  # Sonoff B1 (only cloud)
    # https://github.com/AlexxIT/SonoffLAN/issues/173
    25: [XDiffuserFan, XDiffuserLight],  # Diffuser
    28: [LED, RSSI],  # Sonoff RF Brigde 433
    29: SPEC_2CH,
    30: SPEC_3CH,
    31: SPEC_4CH,
    34: [XFan, XFanLight],  # Sonoff iFan02 and iFan03
    36: [XDimmer],  # KING-M4 (dimmer, only cloud)
    44: [XLightD1],  # Sonoff D1
    57: [XLight57],  # Mosquito Killer Lamp
    59: [XLightLED],  # Sonoff LED (only cloud)
    # 66: switch1,  # ZigBee Bridge
    77: SPEC_1CH,  # Sonoff Micro
    78: SPEC_1CH,
    81: SPEC_1CH,
    82: SPEC_2CH,
    83: SPEC_3CH,
    84: SPEC_4CH,
    103: [XLightB02],  # Sonoff B02 CCT bulb
    104: [XLightB05],  # Sonoff B05 RGB+CCT color bulb
    107: SPEC_1CH,
    126: [
        Switch1, Switch2,
        spec(XSensor100, param="current_00", uid="current_1"),
        spec(XSensor100, param="current_01", uid="current_2"),
        spec(XSensor100, param="voltage_00", uid="voltage_1"),
        spec(XSensor100, param="voltage_01", uid="voltage_2"),
        spec(XSensor100, param="actPow_00", uid="power_1"),
        spec(XSensor100, param="actPow_01", uid="power_2"),
    ],  # DUALR3
}

DIY = {
    # DIY type, UIID, Brand, Model/Name
    "plug": [1, None, "Single Channel DIY"],
    "strip": [4, None, "Multi Channel DIY"],
    "diy_plug": [1, "SONOFF", "MINI DIY"],
    "enhanced_plug": [5, "SONOFF", "POW DIY"],
    "th_plug": [15, "SONOFF", "TH DIY"],
    "rf": [28, "SONOFF", "RFBridge DIY"],
    "fan_light": [34, "SONOFF", "iFan DIY"],
    "light": [44, "SONOFF", "D1 DIY"],
    "multifun_switch": [126, "SONOFF", "DualR3 DIY"],
}


def get_spec(device: dict) -> Optional[list]:
    return DEVICES.get(device["extra"]["uiid"])


def setup_diy(device: dict) -> dict:
    uiid, brand, model = DIY.get(device["diy"])
    device.setdefault("name", model)
    device["brandName"] = brand
    device["extra"] = {"uiid": uiid}
    device["online"] = False
    device["productModel"] = model
    return device
