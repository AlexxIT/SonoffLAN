"""
Each device has a specification - list of classes (XEntity childs). Platform
will setup entity if it isinstance() of platform entity class.

User can override SwitchEntity of any device via YAML (device_class option).

XEntity properties:
- params - required, set of parameters that this entity can read
- param - optional, entity main parameter (useful for sensors)
- uid - optional, entity unique_id tail

Developer can change global properties of existing classes via spec function.
"""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.light import LightEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity

from .ewelink import XDevice
from ..binary_sensor import (
    XBinarySensor,
    XWiFiDoor,
    XZigbeeMotion,
    XHumanSensor,
    XLightSensor,
)
from ..climate import XClimateNS, XClimateTH, XThermostat
from ..core.entity import XEntity
from ..cover import XCover, XCoverDualR3, XZigbeeCover, XCover91
from ..fan import XDiffuserFan, XFan, XToggleFan, XFanDualR3
from ..light import (
    XDiffuserLight,
    XDimmer,
    XFanLight,
    XLight57,
    XLightB1,
    XLightB02,
    XLightB05B,
    XLightD1,
    XLightGroup,
    XLightL1,
    XLightL3,
    XOnOffLight,
    XT5Light,
    XZigbeeLight,
)
from ..number import XPulseWidth, XSensitivity
from ..remote import XRemote
from ..sensor import (
    XEnergySensor,
    XHumidityTH,
    XOutdoorTempNS,
    XRemoteButton,
    XSensor,
    XTemperatureNS,
    XTemperatureTH,
    XUnknown,
    XWiFiDoorBattery,
    XEnergySensorDualR3,
    XEnergySensorPOWR3,
    XEnergyTotal,
    XT5Action,
)
from ..switch import (
    XSwitch,
    XSwitches,
    XSwitchTH,
    XToggle,
    XZigbeeSwitches,
    XSwitchPOWR3,
    XDetach,
    XBoolSwitch,
)

# supported custom device_class
DEVICE_CLASS = {
    "binary_sensor": (XEntity, BinarySensorEntity),
    "fan": (XToggleFan,),  # using custom class for overriding is_on function
    "light": (XOnOffLight,),  # fix color modes support
    "sensor": (XEntity, SensorEntity),
    "switch": (XEntity, SwitchEntity),
}


def unwrap_cached_properties(attrs: dict):
    """Fix metaclass CachedProperties problem in latest Hass."""
    for k, v in list(attrs.items()):
        if k.startswith("_attr_") and f"_{k}" in attrs and isinstance(v, property):
            attrs[k] = attrs.pop(f"_{k}")
    return attrs


def spec(cls, base: str = None, enabled: bool = None, **kwargs) -> type:
    """Make duplicate for cls class with changes in kwargs params.

    If `base` param provided - can change Entity base class for cls. So it can
    be added to different Hass domain.
    """
    if enabled is not None:
        kwargs["_attr_entity_registry_enabled_default"] = enabled
    if base:
        attrs = cls.__mro__[-len(XSwitch.__mro__) :: -1]
        attrs = {k: v for b in attrs for k, v in b.__dict__.items()}
        attrs = unwrap_cached_properties({**attrs, **kwargs})
        return type(cls.__name__, DEVICE_CLASS[base], attrs)
    return type(cls.__name__, (cls,), kwargs)


Switch1 = spec(XSwitches, channel=0, uid="1")
Switch2 = spec(XSwitches, channel=1, uid="2")
Switch3 = spec(XSwitches, channel=2, uid="3")
Switch4 = spec(XSwitches, channel=3, uid="4")

XSensor100 = spec(XSensor, multiply=0.01, round=2)

Battery = spec(XSensor, param="battery")
LED = spec(XToggle, param="sledOnline", uid="led", enabled=False)
RSSI = spec(XSensor, param="rssi", enabled=False)
PULSE = spec(XToggle, param="pulse", enabled=False)
ZRSSI = spec(XSensor, param="subDevRssi", uid="rssi", enabled=False)

SPEC_SWITCH = [XSwitch, LED, RSSI, PULSE, XPulseWidth]
SPEC_1CH = [Switch1, LED, RSSI]
SPEC_2CH = [Switch1, Switch2, LED, RSSI]
SPEC_3CH = [Switch1, Switch2, Switch3, LED, RSSI]
SPEC_4CH = [Switch1, Switch2, Switch3, Switch4, LED, RSSI]

Current1 = spec(XSensor100, param="current_00", uid="current_1")
Current2 = spec(XSensor100, param="current_01", uid="current_2")
Current3 = spec(XSensor100, param="current_02", uid="current_3")
Current4 = spec(XSensor100, param="current_03", uid="current_4")
Voltage1 = spec(XSensor100, param="voltage_00", uid="voltage_1")
Voltage2 = spec(XSensor100, param="voltage_01", uid="voltage_2")
Voltage3 = spec(XSensor100, param="voltage_02", uid="voltage_3")
Voltage4 = spec(XSensor100, param="voltage_03", uid="voltage_4")
Power1 = spec(XSensor100, param="actPow_00", uid="power_1")
Power2 = spec(XSensor100, param="actPow_01", uid="power_2")
Power3 = spec(XSensor100, param="actPow_02", uid="power_3")
Power4 = spec(XSensor100, param="actPow_03", uid="power_4")

EnergyPOW = spec(
    XEnergySensor,
    param="hundredDaysKwhData",
    uid="energy",
    get_params={"hundredDaysKwh": "get"},
)

# backward compatibility for unique_id
DoorLock = spec(XBinarySensor, param="lock", uid="", default_class="door")

# https://github.com/CoolKit-Technologies/eWeLink-API/blob/main/en/UIIDProtocol.md
DEVICES = {
    1: SPEC_SWITCH,
    2: SPEC_2CH,
    3: SPEC_3CH,
    4: SPEC_4CH,
    5: [
        XSwitch,
        LED,
        RSSI,
        spec(XSensor, param="power"),
        EnergyPOW,
    ],  # Sonoff POW (first)
    6: SPEC_SWITCH,
    7: SPEC_2CH,  # Sonoff T1 2CH
    8: SPEC_3CH,  # Sonoff T1 3CH
    9: SPEC_4CH,
    11: [XCover, LED, RSSI],  # King Art - King Q4 Cover (only cloud)
    14: SPEC_SWITCH,  # Sonoff Basic (3rd party)
    15: [
        XSwitchTH,
        XClimateTH,
        XTemperatureTH,
        XHumidityTH,
        LED,
        RSSI,
    ],  # Sonoff TH16
    18: [
        spec(XSensor, param="temperature"),
        spec(XSensor, param="humidity"),
        spec(XSensor, param="dusty"),
        spec(XSensor, param="light"),
        spec(XSensor, param="noise"),
    ],
    22: [XLightB1, RSSI],  # Sonoff B1 (only cloud)
    # https://github.com/AlexxIT/SonoffLAN/issues/173
    25: [
        XDiffuserFan,
        XDiffuserLight,
        RSSI,
        spec(XBinarySensor, param="water", uid=""),
    ],  # Diffuser
    28: [XRemote, LED, RSSI],  # Sonoff RF Brigde 433
    29: SPEC_2CH,
    30: SPEC_3CH,
    31: SPEC_4CH,
    32: [
        XSwitch,
        LED,
        RSSI,
        spec(XSensor, param="current"),
        spec(XSensor, param="power"),
        spec(XSensor, param="voltage"),
        EnergyPOW,
    ],  # Sonoff POWR2
    33: [XLightL1, RSSI],  # https://github.com/AlexxIT/SonoffLAN/issues/985
    34: [
        XFan,
        XFanLight,
        LED,
        RSSI,
    ],  # Sonoff iFan02 and iFan03
    36: [XDimmer, RSSI],  # KING-M4 (dimmer, only cloud)
    44: [XLightD1, RSSI],  # Sonoff D1
    57: [XLight57, RSSI],  # Mosquito Killer Lamp
    59: [XLightL1, RSSI],  # Sonoff LED (only cloud)
    66: [RSSI, LED, spec(XBinarySensor, param="zled", enabled=False)],  # ZigBee Bridge
    77: SPEC_1CH,  # Sonoff Micro
    78: SPEC_1CH,  # https://github.com/AlexxIT/SonoffLAN/issues/615
    81: SPEC_1CH,
    82: SPEC_2CH,
    83: SPEC_3CH,
    84: SPEC_4CH,
    91: [XCover91],
    102: [XWiFiDoor, XWiFiDoorBattery, RSSI],  # Sonoff DW2 Door/Window sensor
    103: [XLightB02, RSSI],  # Sonoff B02 CCT bulb
    104: [XLightB05B, RSSI],  # Sonoff B05-B RGB+CCT color bulb
    107: SPEC_1CH,
    126: [
        Switch1,
        Switch2,
        RSSI,
        Current1,
        Current2,
        Voltage1,
        Voltage2,
        Power1,
        Power2,
        spec(
            XEnergySensorDualR3,
            param="kwhHistories_00",
            uid="energy_1",
            get_params={"getKwh_00": 2},
        ),
        spec(
            XEnergySensorDualR3,
            param="kwhHistories_01",
            uid="energy_2",
            get_params={"getKwh_01": 2},
        ),
    ],  # Sonoff DualR3
    127: [XThermostat],  # https://github.com/AlexxIT/SonoffLAN/issues/358
    128: [LED],  # SPM-Main
    130: [
        Switch1,
        Switch2,
        Switch3,
        Switch4,
        Current1,
        Current2,
        Current3,
        Current4,
        Voltage1,
        Voltage2,
        Voltage3,
        Voltage4,
        Power1,
        Power2,
        Power3,
        Power4,
        spec(
            XEnergySensorDualR3,
            param="kwhHistories_00",
            uid="energy_1",
            get_params={"getKwh_00": 2},
        ),
        spec(
            XEnergySensorDualR3,
            param="kwhHistories_01",
            uid="energy_2",
            get_params={"getKwh_01": 2},
        ),
        spec(
            XEnergySensorDualR3,
            param="kwhHistories_02",
            uid="energy_3",
            get_params={"getKwh_02": 2},
        ),
        spec(
            XEnergySensorDualR3,
            param="kwhHistories_03",
            uid="energy_4",
            get_params={"getKwh_03": 2},
        ),
    ],  # SPM-4Relay, https://github.com/AlexxIT/SonoffLAN/issues/658
    133: [
        # Humidity. ALWAYS 50... NSPanel DOESN'T HAVE HUMIDITY SENSOR
        # https://github.com/AlexxIT/SonoffLAN/issues/751
        Switch1,
        Switch2,
        XClimateNS,
        XTemperatureNS,
        XOutdoorTempNS,
    ],  # Sonoff NS Panel
    # https://github.com/AlexxIT/SonoffLAN/issues/1026
    135: [XLightB02, RSSI],  # Sonoff B02-BL
    # https://github.com/AlexxIT/SonoffLAN/issues/766
    # https://github.com/AlexxIT/SonoffLAN/issues/890
    # https://github.com/AlexxIT/SonoffLAN/pull/892
    # https://github.com/AlexxIT/SonoffLAN/pull/1035
    136: [spec(XLightB05B, min_ct=0, max_ct=100), RSSI],  # Sonoff B05-BL
    137: [XLightL1, RSSI],
    # https://github.com/AlexxIT/SonoffLAN/issues/623#issuecomment-1365841454
    138: [
        Switch1,
        LED,
        RSSI,
        XDetach,
        spec(XRemoteButton, param="action"),
    ],  # MINIR3, MINIR4
    # https://github.com/AlexxIT/SonoffLAN/issues/808
    154: [XWiFiDoor, Battery, RSSI],  # DW2-Wi-Fi-L
    160: SPEC_1CH,  # Sonoff SwitchMan M5-1C, https://github.com/AlexxIT/SonoffLAN/issues/1432
    161: SPEC_2CH,  # Sonoff SwitchMan M5-2C, https://github.com/AlexxIT/SonoffLAN/issues/1432
    162: SPEC_3CH,  # Sonoff SwitchMan M5-3C, https://github.com/AlexxIT/SonoffLAN/issues/659
    165: [Switch1, Switch2, RSSI],  # DualR3 Lite, without power consumption
    # https://github.com/AlexxIT/SonoffLAN/issues/857
    168: [RSSI],  # new ZBBridge-P
    173: [XLightL3, RSSI],  # Sonoff L3-5M-P
    174: [XRemoteButton],  # Sonoff R5 (6-key remote)
    177: [XRemoteButton],  # Sonoff S-Mate
    181: [
        XSwitchTH,
        XTemperatureTH,
        XHumidityTH,
        LED,
        RSSI,
    ],  # Sonoff THR320D or THR316D
    182: [
        Switch1,
        LED,
        RSSI,
        spec(XSensor, param="current"),
        spec(XSensor, param="power"),
        spec(XSensor, param="voltage"),
        EnergyPOW,
    ],  # Sonoff S40
    190: [
        XSwitchPOWR3,
        LED,
        RSSI,
        spec(XSensor100, param="current"),
        spec(XSensor100, param="power"),
        spec(XSensor100, param="voltage"),
        spec(XEnergyTotal, param="dayKwh", uid="energy_day", multiply=0.01, round=2),
        spec(
            XEnergyTotal, param="monthKwh", uid="energy_month", multiply=0.01, round=2
        ),
        spec(
            XEnergySensorPOWR3,
            param="hoursKwhData",
            uid="energy",
            get_params={"getHoursKwh": {"start": 0, "end": 24 * 30 - 1}},
        ),
    ],  # Sonoff POWR3
    # https://github.com/AlexxIT/SonoffLAN/issues/984
    195: [XTemperatureTH],  # NSPanel Pro
    # https://github.com/AlexxIT/SonoffLAN/issues/1183
    209: [Switch1, XT5Light, XT5Action],  # T5-1C-86
    210: [Switch1, Switch2, XT5Light, XT5Action],  # T5-2C-86
    211: [Switch1, Switch2, Switch3, XT5Light, XT5Action],  # T5-3C-86
    # https://github.com/AlexxIT/SonoffLAN/issues/1251
    212: [Switch1, Switch2, Switch3, Switch4, XT5Light, XT5Action],  # T5-4C-86
    226: [
        XBoolSwitch,
        LED,
        RSSI,
        spec(XSensor, param="phase_0_c", uid="current"),
        spec(XSensor, param="phase_0_p", uid="power"),
        spec(XSensor, param="phase_0_v", uid="voltage"),
        spec(XEnergyTotal, param="totalPower", uid="energy"),
    ],  # CK-BL602-W102SW18-01(226)
    1000: [XRemoteButton, Battery],  # zigbee_ON_OFF_SWITCH_1000
    # https://github.com/AlexxIT/SonoffLAN/issues/1195
    1256: [spec(XSwitch)],  # ZCL_HA_DEVICEID_ON_OFF_LIGHT
    1257: [XLightD1],  # ZigbeeWhiteLight
    # https://github.com/AlexxIT/SonoffLAN/issues/972
    1514: [XZigbeeCover, spec(XSensor, param="battery", multiply=2)],
    1770: [
        spec(XSensor100, param="temperature"),
        spec(XSensor100, param="humidity"),
        Battery,
    ],  # ZCL_HA_DEVICEID_TEMPERATURE_SENSOR
    1771: [
        spec(XSensor100, param="temperature"),
        spec(XSensor100, param="humidity"),
        Battery,
    ],  # https://github.com/AlexxIT/SonoffLAN/issues/1150
    2026: [XZigbeeMotion, Battery],  # ZIGBEE_MOBILE_SENSOR
    3026: [DoorLock, Battery],  # ZIGBEE_DOOR_AND_WINDOW_SENSOR
    # https://github.com/AlexxIT/SonoffLAN/issues/1265
    3258: [XZigbeeLight],  # ZigbeeColorTunableWhiteLight
    4026: [
        spec(XBinarySensor, param="water", uid="", default_class="moisture"),
        Battery,
    ],  # https://github.com/AlexxIT/SonoffLAN/issues/852
    4256: [
        spec(XZigbeeSwitches, channel=0, uid="1"),
        spec(XZigbeeSwitches, channel=1, uid="2"),
        spec(XZigbeeSwitches, channel=2, uid="3"),
        spec(XZigbeeSwitches, channel=3, uid="4"),
    ],
    7000: [XRemoteButton, Battery],
    # https://github.com/AlexxIT/SonoffLAN/issues/1435
    7002: [XZigbeeMotion, XLightSensor, Battery, ZRSSI],  # SNZB-03P
    # https://github.com/AlexxIT/SonoffLAN/issues/1439
    7003: [DoorLock, Battery, ZRSSI],  # SNZB-04P
    # https://github.com/AlexxIT/SonoffLAN/issues/1398
    7004: [XSwitch, ZRSSI],  # ZBMINIL2
    # https://github.com/AlexxIT/SonoffLAN/issues/1283
    7006: [XZigbeeCover, Battery],
    # https://github.com/AlexxIT/SonoffLAN/issues/1456
    7009: [XZigbeeLight],  # CK-BL702-AL-01(7009_Z102LG03-1)
    7014: [
        spec(XSensor100, param="temperature"),
        spec(XSensor100, param="humidity"),
        Battery,
    ],  # https://github.com/AlexxIT/SonoffLAN/issues/1166
    7016: [XHumanSensor, XLightSensor, XSensitivity, ZRSSI],  # SNZB-06P
}


def get_spec(device: dict) -> list:
    uiid = device["extra"]["uiid"]

    if uiid in DEVICES:
        classes = DEVICES[uiid]
    elif "switch" in device["params"]:
        classes = SPEC_SWITCH
    elif "switches" in device["params"]:
        classes = SPEC_4CH
    else:
        classes = [XUnknown]

    # DualR3 in cover mode
    if uiid in [126, 165] and device["params"].get("workMode") == 2:
        classes = [cls for cls in classes if XSwitches not in cls.__bases__]
        classes = [XCoverDualR3, XFanDualR3] + classes

    # NSPanel Climate disable without switch configuration
    if uiid in [133] and not device["params"].get("HMI_ATCDevice"):
        classes = [cls for cls in classes if XClimateNS not in cls.__bases__]

    # SNZB-06P has no battery
    if uiid in [2026] and not device["params"].get("battery"):
        classes = [cls for cls in classes if cls != Battery]

    if "device_class" in device:
        classes = get_custom_spec(classes, device["device_class"])

    return classes


def get_custom_spec(classes: list, device_class):
    """Supported device_class formats:
    1. Single channel:
       device_class: light
    2. Multiple channels:
       device_class: [light, fan, switch]
    3. Light with brightness control
       device_class:
         - switch  # entity 1 (channel 1)
         - light: [2, 3]  # entity 2 (channels 2 and 3)
         - fan: 4  # entity 3 (channel 4)
    """
    # 1. single channel
    if isinstance(device_class, str):
        if device_class in DEVICE_CLASS:
            classes = [spec(classes[0], base=device_class)] + classes[1:]

    elif isinstance(device_class, list):
        # remove all default multichannel classes from spec
        base = classes[0].__base__
        classes = [cls for cls in classes if base not in cls.__bases__]

        for i, sub_class in enumerate(device_class):
            # 2. simple multichannel
            if isinstance(sub_class, str):
                classes.append(spec(base, channel=i, uid=str(i + 1), base=sub_class))

            elif isinstance(sub_class, dict):
                sub_class, i = next(iter(sub_class.items()))

                # 3. light with brightness
                if isinstance(i, list) and sub_class == "light":
                    chs = [x - 1 for x in i]
                    uid = "".join(str(x) for x in i)
                    classes.append(spec(XLightGroup, channels=chs, uid=uid))

                # 4. multichannel
                elif isinstance(i, int):
                    classes.append(
                        spec(base, channel=(i - 1), uid=str(i), base=sub_class)
                    )

    return classes


def get_spec_wrapper(func, sensors: list):
    def wrapped(device: dict) -> list:
        classes = func(device)
        for uid in sensors:
            if (uid in device["params"] or uid == "host") and all(
                cls.param != uid and cls.uid != uid for cls in classes
            ):
                classes.append(spec(XSensor, param=uid))
        return classes

    return wrapped


def set_default_class(device_class: str):
    XSwitch.__bases__ = XSwitches.__bases__ = (
        XEntity,
        LightEntity if device_class == "light" else SwitchEntity,
    )


# Cloud: NSPanel
DIY = {
    # DIY type, UIID, Brand, Model/Name
    "plug": [1, None, "Single Channel DIY"],  # POWR316
    "strip": [4, None, "Multi Channel DIY"],  # 4CHPROR3
    "diy_plug": [1, "SONOFF", "MINI DIY"],
    "enhanced_plug": [5, "SONOFF", "POW DIY"],  # POWR2
    "th_plug": [15, "SONOFF", "TH DIY"],  # TH16R2
    "rf": [28, "SONOFF", "RFBridge DIY"],
    "fan_light": [34, "SONOFF", "iFan DIY"],
    "light": [44, "SONOFF", "D1 DIY"],  # don't know if light exist
    "diylight": [44, "SONOFF", "D1 DIY"],
    "diy_light": [136, "SONOFF", "B0x-BL DIY"],
    "switch_radar": [77, "SONOFF", "Micro DIY"],  # Micro
    "multifun_switch": [126, "SONOFF", "DualR3 DIY"],
}


def setup_diy(device: dict) -> XDevice:
    ltype = device["localtype"]
    try:
        uiid, brand, model = DIY[ltype]
        # https://github.com/AlexxIT/SonoffLAN/issues/1136
        # https://github.com/AlexxIT/SonoffLAN/issues/1156
        if ltype == "diy_plug" and "switches" in device["params"]:
            uiid = 77
            model = "MINI R3 DIY"
        device["name"] = model
        device["brandName"] = brand
        device["extra"] = {"uiid": uiid}
        device["productModel"] = model
    except Exception:
        device["name"] = "Unknown DIY"
        device["extra"] = {"uiid": 0}
        device["productModel"] = ltype
    return device
