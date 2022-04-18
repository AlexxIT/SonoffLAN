"""
Each device has a specification - list of classes (XEntity childs)

XEntity properties:
- params - required, set of parameters that this entity can read
- param - optional, entity main parameter (useful for sensors)
- uid - optional, entity unique_id tail

`spec` - function can change default class with some options
"""
from typing import Optional

from ..conver import XCover
from ..fan import XFan
from ..light import XFanLight
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

DEVICES = [{
    1: "Sonoff 1CH",
    5: "Sonoff Pow",
    6: "??",
    14: "Sonoff Basic",
    "spec": [XSwitch, LED, RSSI]
}, {
    2: "Sonoff 2CH",
    7: "Sonoff T1 2CH",
    29: "Sonoff 2CH",
    "spec": [Switch1, Switch2]
}, {
    3: "Sonoff 3CH",
    8: "Sonoff T1 3CH",
    30: "Sonoff 3CH",
    "spec": [Switch1, Switch2, Switch3]
}, {
    4: "Sonoff 4CH",
    9: "Sonoff 4CH",
    31: "Sonoff 4CH",
    "spec": [Switch1, Switch2, Switch3, Switch4]
}, {
    77: "Sonoff Micro",
    78: "Sonoff 1CH",
    81: "Sonoff 1CH",
    107: "Sonoff 1CH",
    "spec": [Switch1]
}, {
    11: "King Art - King Q4 Cover",
    "spec": [XCover, LED, RSSI],
}, {
    15: "Sonoff TH16",
    "spec": [
        XSwitchTH, LED, RSSI,
        spec(XSensor, param="currentTemperature", uid="temperature"),
        spec(XSensor, param="currentHumidity", uid="humidity"),
    ]
}, {
    28: "Sonoff RFBridge",
    "spec": [LED, RSSI]
}, {
    34: "Sonoff iFan",  # Sonoff iFan02 and iFan03
    "spec": [XFan, XFanLight]
}, {
    126: "Sonoff Dual R3",
    "spec": [
        Switch1, Switch2,
        spec(XSensor100, param="current_00", uid="current_1"),
        spec(XSensor100, param="current_01", uid="current_2"),
        spec(XSensor100, param="voltage_00", uid="voltage_1"),
        spec(XSensor100, param="voltage_01", uid="voltage_2"),
        spec(XSensor100, param="actPow_00", uid="power_1"),
        spec(XSensor100, param="actPow_01", uid="power_2"),
    ]
}]

# , {
#     11: "Cover",
#     "spec": [
#         Converter("cover", "cover"),
#     ]
# }, {
#     18: "Sonoff SC",
#     "spec": [
#         Converter("xxx", "sensor"),
#     ]
# }, {
#     22: "Sonoff SC",
#     "spec": [
#         Converter("light", "light"),
#     ]
# }, {
#     25: "Diffuser",
#     "spec": [
#         Converter("fan", "fan", speed_count=2),
#         Converter("light", "light"),
#     ]
# }, {
#     28: "Sonoff RF Brigde 433",
#     "spec": [
#         Converter("", "remote"),
#     ]
# }, {
#     34: "Sonoff iFan",  # Sonoff iFan02 and iFan03
#     "spec": [
#         Converter("", "light"),
#         Converter("", "fan"),
#     ]
# }, {
#     36: "KING-M4",
#     "spec": [
#         Converter("", "light"),
#     ]
# }, {
#     44: "Sonoff D1",
#     "spec": [
#         Converter("", "light"),
#     ]
# }, {
#     102: "Sonoff DW2 Door/Window sensor",
#     "spec": [
#         Converter("door", "binary_sensor"),
#     ]
# }]

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
    try:
        uiid = device["extra"]["uiid"]
        info = next(i for i in DEVICES if uiid in i)
        return info["spec"]
    except:
        return None


def setup_diy(device: dict) -> dict:
    uiid, brand, model = DIY.get(device["diy"])
    device.setdefault("name", model)
    device["brandName"] = brand
    device["extra"] = {"uiid": uiid}
    device["online"] = False
    device["productModel"] = model
    return device
