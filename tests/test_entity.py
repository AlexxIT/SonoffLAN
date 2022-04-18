from homeassistant.core import Config
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

from custom_components.sonoff.core.ewelink import XRegistry, \
    SIGNAL_ADD_ENTITIES, SIGNAL_UPDATE
from custom_components.sonoff.fan import XFan
from custom_components.sonoff.light import XFanLight
from custom_components.sonoff.sensor import XSensor
from custom_components.sonoff.switch import XSwitch, XSwitchTH

DEVICEID = "1000123abc"


class HassDummy:
    def __init__(self):
        self.async_set = lambda *args: None
        self.config = Config(None)
        self.data = {}
        self.states = self


# noinspection PyTypeChecker
def get_entitites(device: dict):
    entities = []

    reg = XRegistry(None)
    reg.dispatcher_connect(SIGNAL_ADD_ENTITIES, lambda x: entities.extend(x))
    reg.setup_devices([device])

    hass = HassDummy()
    for entity in entities:
        entity.hass = hass

    return reg, entities


def test_switch1():
    _, entities = get_entitites({
        'name': 'Kitchen',
        'deviceid': DEVICEID,
        'extra': {'uiid': 1, 'model': 'PSF-BD1-GL'},
        'brandName': 'SONOFF',
        'productModel': 'MINI',
        'online': True,
        'params': {
            'sledOnline': 'on',
            'switch': 'on',
            'fwVersion': '3.3.0',
            'rssi': -39,
            'startup': 'off',
            'init': 1,
            'pulse': 'off',
            'pulseWidth': 3000,
            'staMac': '11:22:33:AA:BB:CC'
        },
    })
    assert len(entities) == 3

    switch: XSwitch = entities[0]
    assert switch.name == "Kitchen"
    assert switch.unique_id == DEVICEID
    assert (CONNECTION_NETWORK_MAC, "11:22:33:AA:BB:CC") in \
           switch.device_info["connections"]
    assert switch.device_info["manufacturer"] == "SONOFF"
    assert switch.device_info["model"] == "MINI"
    assert switch.device_info["sw_version"] == "3.3.0"
    assert switch.state == "on"

    led: XSwitch = entities[1]
    # assert rssi.unique_id == "1000123abc_led"
    assert led.state == "on"
    assert led.entity_registry_enabled_default is False

    rssi: XSensor = entities[2]
    assert rssi.unique_id == DEVICEID + "_rssi"
    assert rssi.native_value == -39
    assert rssi.entity_registry_enabled_default is False


def test_available():
    reg, entities = get_entitites({
        'name': 'Sonoff Basic',
        'deviceid': DEVICEID,
        'extra': {'uiid': 1},
        'online': True,
        'params': {'switch': 'on'},
    })
    switch: XSwitch = entities[0]
    assert switch.available is True
    assert switch.state == "on"

    # only cloud online changed
    msg = {"deviceid": DEVICEID, "params": {"online": False}}
    reg.cloud.dispatcher_send(SIGNAL_UPDATE, msg)
    assert switch.available is False
    assert switch.state == "on"

    # cloud state changed (also change available)
    msg = {"deviceid": DEVICEID, "params": {"switch": "off"}}
    reg.cloud.dispatcher_send(SIGNAL_UPDATE, msg)
    assert switch.available is True
    assert switch.state == "off"


def test_switch2():
    _, entities = get_entitites({
        'name': 'Switch 2CH',
        'deviceid': DEVICEID,
        'extra': {'uiid': 2, 'model': 'PSF-B04-GL'},
        'brandName': 'AoYan touch',
        'productModel': 'M602-1',
        'online': True,
        'params': {
            'init': 1,
            'switches': [
                {'switch': 'on', 'outlet': 0},
                {'switch': 'off', 'outlet': 1},
                {'switch': 'off', 'outlet': 2},
                {'switch': 'off', 'outlet': 3}
            ],
            'configure': [
                {'startup': 'off', 'outlet': 0},
                {'startup': 'off', 'outlet': 1},
                {'startup': 'off', 'outlet': 2},
                {'startup': 'off', 'outlet': 3}
            ],
            'fwVersion': '3.3.0',
            'rssi': -41,
            'staMac': '11:22:33:AA:BB:CC',
            'pulse': 'off',
            'pulseWidth': 0,
            'version': 8,
            'sledOnline': 'on',
            'lock': 0,
            'pulses': [
                {'pulse': 'off', 'width': 1000, 'outlet': 0},
                {'pulse': 'off', 'width': 1000, 'outlet': 1},
                {'pulse': 'off', 'width': 1000, 'outlet': 2},
                {'pulse': 'off', 'width': 1000, 'outlet': 3}
            ]
        },
        'tags': {
            'ck_channel_name': {'0': 'Channel A', '1': 'Channel B'}
        }
    })
    assert len(entities) == 2

    switch1: XSwitch = entities[0]
    assert switch1.name == "Channel A"
    assert switch1.unique_id == DEVICEID + "_1"
    assert (CONNECTION_NETWORK_MAC, "11:22:33:AA:BB:CC") in \
           switch1.device_info["connections"]
    assert switch1.device_info["manufacturer"] == "AoYan touch"
    assert switch1.device_info["model"] == "M602-1"
    assert switch1.device_info["sw_version"] == "3.3.0"
    assert switch1.state == "on"

    switch2: XSwitch = entities[1]
    assert switch2.name == "Channel B"
    assert switch2.unique_id == DEVICEID + "_2"
    assert switch2.state == "off"


def test_fan():
    _, entities = get_entitites({
        'name': 'iFan Toilet',
        'deviceid': DEVICEID,
        'extra': {'uiid': 34, 'model': 'PSF-BFB-GL'},
        'brandName': 'SONOFF',
        'productModel': 'iFan03',
        'online': True,
        'params': {
            'version': 8,
            'sledOnline': 'on',
            'init': 1,
            'fwVersion': '3.5.0',
            'rssi': -47,
            'switches': [
                {'switch': 'off', 'outlet': 0},
                {'switch': 'off', 'outlet': 1},
                {'switch': 'off', 'outlet': 2},
                {'switch': 'on', 'outlet': 3}
            ],
            'configure': [
                {'startup': 'on', 'outlet': 0},
                {'startup': 'off', 'outlet': 1},
                {'startup': 'stay', 'outlet': 2},
                {'startup': 'stay', 'outlet': 3}
            ],
            'staMac': 'D8:F1:5B:8D:A3:2F'
        },
    })

    fan: XFan = entities[0]
    assert fan.state == "off"
    assert fan.percentage == 0
    assert fan.speed_count == 3

    fan.set_state({'switches': [
        {'switch': 'off', 'outlet': 0},
        {'switch': 'on', 'outlet': 1},
        {'switch': 'on', 'outlet': 2},
        {'switch': 'off', 'outlet': 3}
    ]})
    assert fan.state == "on"
    assert fan.percentage == 67

    light: XFanLight = entities[1]
    assert light.state == "off"


def test_sonoff_th():
    reg, entities = get_entitites({
        'name': 'Sonoff TH',
        'deviceid': DEVICEID,
        'extra': {'uiid': 15, 'model': 'PSA-BHA-GL'},
        'brandName': 'SONOFF',
        'productModel': 'TH16',
        'online': True,
        'params': {
            'currentHumidity': '42',
            'currentTemperature': '14.6',
            'deviceType': 'normal',
            'fwVersion': '3.4.0',
            'init': 1,
            'mainSwitch': 'off',
            'pulse': 'off',
            'pulseWidth': 500,
            'rssi': -43,
            'sensorType': 'AM2301',
            'sledOnline': 'on',
            'staMac': '11:22:33:AA:BB:CC',
            'startup': 'stay',
            'switch': 'off',
            'targets': [
                {'reaction': {'switch': 'off'}, 'targetHigh': '22'},
                {'reaction': {'switch': 'on'}, 'targetLow': '22'}
            ],
            "timers": [],
            "version": 8
        },
    })

    switch: XSwitchTH = entities[0]
    assert switch.state == "off"

    temp: XSensor = next(e for e in entities if e.uid == "temperature")
    assert temp.state == 14.6

    hum: XSensor = next(e for e in entities if e.uid == "humidity")
    assert hum.state == 42

    # check TH v3.4.0 param name
    msg = {"deviceid": DEVICEID, "host": "", "params": {"humidity": 48}}
    reg.local.dispatcher_send(SIGNAL_UPDATE, msg)
    assert hum.state == 48

    # check TH v3.4.0 zero humidity bug (skip value)
    msg["params"] = {"humidity": 0}
    reg.local.dispatcher_send(SIGNAL_UPDATE, msg)
    assert hum.state == 48

    msg["params"] = {"currentHumidity": "unavailable"}
    reg.local.dispatcher_send(SIGNAL_UPDATE, msg)
    assert hum.state is None


def test_dual_r3():
    _, entities = get_entitites({
        'name': 'Sonoff Dual R3',
        'deviceid': DEVICEID,
        'extra': {'uiid': 126},
        'online': False,
        'params': {
            'version': 7,
            'workMode': 1,
            'motorSwMode': 2,
            'motorSwReverse': 0,
            'outputReverse': 0,
            'motorTurn': 0,
            'calibState': 0,
            'currLocation': 0,
            'location': 0,
            'sledBright': 100,
            'staMac': '112233AABBCC',
            'rssi': -35,
            'overload_00': {
                'minActPow': {'enabled': 0, 'value': 10},
                'maxVoltage': {'enabled': 0, 'value': 24000},
                'minVoltage': {'enabled': 0, 'value': 10},
                'maxCurrent': {'enabled': 0, 'value': 1500},
                'maxActPow': {'enabled': 0, 'value': 360000}
            },
            'overload_01': {
                'minActPow': {'enabled': 0, 'value': 10},
                'maxVoltage': {'enabled': 0, 'value': 24000},
                'minVoltage': {'enabled': 0, 'value': 10},
                'maxCurrent': {'enabled': 0, 'value': 1500},
                'maxActPow': {'enabled': 0, 'value': 360000}
            },
            'oneKwhState_00': 0, 'startTime_00': '', 'endTime_00': '',
            'oneKwhState_01': 0, 'startTime_01': '', 'endTime_01': '',
            'oneKwhData_00': 0, 'oneKwhData_01': 0, 'current_00': 0,
            'voltage_00': 24762, 'actPow_00': 0, 'reactPow_00': 0,
            'apparentPow_00': 0, 'current_01': 0, 'voltage_01': 24762,
            'actPow_01': 0, 'reactPow_01': 0, 'apparentPow_01': 0,
            'fwVersion': '1.3.0', 'timeZone': 3, 'swMode_00': 2,
            'swMode_01': 2, 'swReverse_00': 0, 'swReverse_01': 0,
            'zyx_clear_timers': True,
            'switches': [
                {'switch': 'off', 'outlet': 0},
                {'switch': 'off', 'outlet': 1}
            ],
            'configure': [
                {'startup': 'off', 'outlet': 0},
                {'startup': 'off', 'outlet': 1}
            ],
            'pulses': [
                {'pulse': 'off', 'width': 1000, 'outlet': 0},
                {'pulse': 'off', 'width': 1000, 'outlet': 1}
            ],
            'getKwh_00': 2,
            'uiActive': {'time': 120, 'outlet': 0},
            'initSetting': 1,
            'getKwh_01': 2,
            'calibration': 1
        },
    })

    volt: XSensor = next(e for e in entities if e.uid == "voltage_1")
    assert volt.state == 247.62


def test_diffuser():
    _, entitites = get_entitites({
        'name': 'Wood Diffuser ',
        'deviceid': DEVICEID,
        'extra': {'uiid': 25},
        'online': False,
        'params': {
            'lightbright': 254,
            'lightBcolor': 255,
            'lightGcolor': 217,
            'lightRcolor': 7,
            'lightmode': 2,
            'lightswitch': 0,
            'water': 0,
            'state': 2,
            'switch': 'off',
            'staMac': '11:22:33:AA:BB:CC',
            'fwVersion': '3.4.0',
            'rssi': -88,
            'sledOnline': 'on',
            'version': 8,
            'only_device': {'ota': 'success'},
        }
    })
