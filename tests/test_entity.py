import asyncio

from homeassistant.components.fan import FanEntity
from homeassistant.components.light import LightEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import Config
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

from custom_components.sonoff.binary_sensor import XRemoteSensor, XBinarySensor
from custom_components.sonoff.core import devices
from custom_components.sonoff.core.ewelink import XRegistry, \
    SIGNAL_ADD_ENTITIES, SIGNAL_UPDATE, SIGNAL_CONNECTED
from custom_components.sonoff.fan import XFan
from custom_components.sonoff.light import XFanLight, XLightGroup
from custom_components.sonoff.sensor import XSensor, XZigbeeButton, XUnknown
from custom_components.sonoff.switch import XSwitch, XSwitchTH, XToggle, \
    XSwitches

DEVICEID = "1000123abc"


class DummyHass:
    def __init__(self):
        # noinspection PyTypeChecker
        self.config = Config(None)
        self.data = {}

        self.states = self
        self.async_set = lambda *args: None

        self.bus = self
        self.async_fire = lambda *args: None


class DummyRegistry(XRegistry):
    send_args = None

    async def send(self, *args):
        self.send_args = args


# noinspection PyTypeChecker
def get_entitites(device: dict, config: dict = None):
    device.setdefault("name", "Device1")
    device.setdefault("deviceid", DEVICEID)
    device.setdefault("online", True)
    device.setdefault("extra", {"uiid": None})
    params = device.setdefault("params", {})
    params.setdefault("staMac", "11:22:33:AA:BB:CC")

    entities = []

    asyncio.create_task = lambda _: None

    reg = DummyRegistry(None)
    reg.config = config
    reg.dispatcher_connect(SIGNAL_ADD_ENTITIES, lambda x: entities.extend(x))
    reg.setup_devices(reg.restore_devices([device]))

    hass = DummyHass()
    for entity in entities:
        entity.hass = hass

    return reg, entities


def await_(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_simple_switch():
    _, entities = get_entitites({
        'name': 'Kitchen',
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

    led: XToggle = next(e for e in entities if e.uid == "led")
    assert led.unique_id == DEVICEID + "_led"
    assert led.state == "on"
    assert led.entity_registry_enabled_default is False

    rssi: XSensor = next(e for e in entities if e.uid == "rssi")
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
    assert switch.available is False
    assert switch.state == "on"

    reg.cloud.online = True
    reg.cloud.dispatcher_send(SIGNAL_CONNECTED)

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


def test_nospec():
    device = {"extra": {"uiid": "X"}, "params": {"switch": "on"}}
    _, entities = get_entitites(device)

    switch: XSwitch = entities[0]
    assert switch.state == "on"

    device = {"extra": {"uiid": "Y"}, "params": {"property": 123}}
    _, entities = get_entitites(device)

    sensor: XUnknown = entities[0]
    assert len(sensor.state) == 25
    assert sensor.extra_state_attributes["property"] == 123


def test_switch_2ch():
    _, entities = get_entitites({
        'extra': {'uiid': 2, 'model': 'PSF-B04-GL'},
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

    # test round to 1 digit
    msg = {
        "deviceid": DEVICEID, "host": "",
        "params": {"deviceType": "normal", "temperature": 12.34}
    }
    reg.local.dispatcher_send(SIGNAL_UPDATE, msg)
    assert temp.state == 12.3

    hum: XSensor = next(e for e in entities if e.uid == "humidity")
    assert hum.state == 42

    # check TH v3.4.0 param name
    msg = {
        "deviceid": DEVICEID, "host": "",
        "params": {"deviceType": "normal", "humidity": 48}
    }
    reg.local.dispatcher_send(SIGNAL_UPDATE, msg)
    assert hum.state == 48

    # check TH v3.4.0 zero humidity bug (skip value)
    msg = {
        "deviceid": DEVICEID, "host": "",
        "params": {"deviceType": "normal", "humidity": 0}
    }
    reg.local.dispatcher_send(SIGNAL_UPDATE, msg)
    assert hum.state == 48

    msg = {
        "deviceid": DEVICEID, "host": "",
        "params": {"deviceType": "normal", "currentHumidity": "unavailable"}
    }
    reg.local.dispatcher_send(SIGNAL_UPDATE, msg)
    assert hum.state is None


def test_dual_r3():
    # noinspection DuplicatedCode
    _, entities = get_entitites({
        'extra': {'uiid': 126},
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
        'extra': {'uiid': 25},
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


def test_sonoff_sc():
    _, entities = get_entitites({
        "extra": {"uiid": 18},
        "params": {
            "dusty": 2,
            "fwVersion": "2.7.0",
            "humidity": 92,
            "light": 10,
            "noise": 2,
            "rssi": -34,
            "sledOnline": "on",
            "staMac": "11:22:33:AA:BB:CC",
            "temperature": 25
        },
    })
    temp: XSensor = next(e for e in entities if e.uid == "temperature")
    assert temp.state == 25
    hum: XSensor = next(e for e in entities if e.uid == "humidity")
    assert hum.state == 92
    dusty: XSensor = next(e for e in entities if e.uid == "dusty")
    assert dusty.state == 2
    light: XSensor = next(e for e in entities if e.uid == "light")
    assert light.state == 10
    noise: XSensor = next(e for e in entities if e.uid == "noise")
    assert noise.state == 2


def test_sonoff_pow():
    _, entities = get_entitites({
        "extra": {"uiid": 32},
        "params": {
            "hundredDaysKwh": "get",
            "startTime": "2020-05-28T13:19:55.409Z",
            "endTime": "2020-05-28T18:24:24.429Z",
            "timeZone": 2,
            "uiActive": 60,
            "oneKwh": "stop",
            "current": "1.23",
            "voltage": "234.20",
            "power": "12.34",
            "pulseWidth": 500,
            "pulse": "off",
            "startup": "on",
            "switch": "on",
            "alarmPValue": [-1, -1],
            "alarmCValue": [-1, -1],
            "alarmVValue": [-1, -1],
            "alarmType": "pcv",
            "init": 1,
            "rssi": -72,
            "staMac": "11:22:33:AA:BB:CC",
            "fwVersion": "3.4.0",
            "sledOnline": "on",
            "version": 8
        },
    })

    power: XSensor = next(e for e in entities if e.uid == "power")
    assert power.state == 12.34
    power: XSensor = next(e for e in entities if e.uid == "current")
    assert power.state == 1.23


def test_rfbridge():
    reg, entities = get_entitites({
        "extra": {"uiid": 28},
        "params": {
            "cmd": "trigger",
            "fwVersion": "3.4.0",
            "init": 1,
            "rfChl": 0,
            "rfList": [],
            "rfTrig0": "2020-05-10T19:29:43.000Z",
            "rfTrig1": 0,
            "rssi": -55,
            "setState": "arm",
            "sledOnline": "on",
            "timers": [],
            "version": 8
        },
        "tags": {
            "disable_timers": [],
            "zyx_info": [{
                "buttonName": [{"0": "Button1"}],
                "name": "Alarm1",
                "remote_type": "6"
            }, {
                "buttonName": [{"1": "Button1"}],
                "name": "Alarm2",
                "remote_type": "6"
            }]
        }
    }, {
        "rfbridge": {
            "Alarm1": {
                "name": "Custom1",
                "timeout": 0,
                "payload_off": "Alarm2"
            }
        }
    })

    alarm: XRemoteSensor = next(e for e in entities if e.name == "Custom1")
    assert alarm.state == "off"

    reg.cloud.dispatcher_send(SIGNAL_UPDATE, {
        "deviceid": DEVICEID,
        "params": {"cmd": "trigger", "rfTrig0": "2022-04-19T03:56:52.000Z"}
    })
    assert alarm.state == "on"

    reg.cloud.dispatcher_send(SIGNAL_UPDATE, {
        "deviceid": DEVICEID,
        "params": {"cmd": "trigger", "rfTrig1": "2022-04-19T03:57:52.000Z"}
    })
    assert alarm.state == "off"


def test_wifi_sensor():
    _, entities = get_entitites({
        "extra": {"uiid": 102},
        "params": {
            "actionTime": "2020-05-20T08:43:33.151Z",
            "battery": 3,
            "fwVersion": "1000.2.917",
            "lastUpdateTime": "2020-05-20T13:43:24.124Z",
            "rssi": -64,
            "switch": "off",
            "type": 4
        }
    })

    sensor: XBinarySensor = entities[0]
    assert sensor.state == "off"


def test_zigbee_button():
    reg, entities = get_entitites({
        "extra": {"uiid": 1000},
        "params": {
            "battery": 100,
            "trigTime": "1601263115917",
            "key": 0
        }
    })

    button: XZigbeeButton = entities[0]
    assert button.state == ""

    reg.cloud.dispatcher_send(SIGNAL_UPDATE, {
        "deviceid": DEVICEID, "params": {'trigTime': '1601285000235', 'key': 1}
    })
    assert button.state == "double"


def test_zigbee_th():
    _, entities = get_entitites({
        "extra": {"uiid": 1770},
        "params": {
            "humidity": "6443",
            "temperature": "2096",
            "trigTime": "1594745697262",
            "battery": 127,
        }
    })

    temp: XSensor = entities[0]
    assert temp.state == 20.96

    hum: XSensor = entities[1]
    assert hum.state == 64.43

    bat: XSensor = entities[2]
    assert bat.state == 127


def test_zigbee_motion():
    reg, entities = get_entitites({
        "extra": {"uiid": 2026},
        "params": {
            "battery": 100,
            "trigTime": "1595266029933",
            "motion": 0,
        }
    })

    motion: XBinarySensor = entities[0]
    assert motion.state == "off"

    reg.cloud.dispatcher_send(SIGNAL_UPDATE, {
        "deviceid": DEVICEID,
        "params": {'trigTime': '1601285000235', 'motion': 1}
    })
    assert motion.state == "on"

    reg.cloud.dispatcher_send(SIGNAL_UPDATE, {
        "deviceid": DEVICEID, "params": {'online': False}
    })
    assert motion.state == "off"


def test_default_class():
    devices.set_default_class("light")

    _, entities = get_entitites({"extra": {"uiid": 15}})
    assert isinstance(entities[0], XSwitchTH)
    assert isinstance(entities[0], LightEntity)
    assert not isinstance(entities[0], SwitchEntity)

    _, entities = get_entitites({
        "extra": {"uiid": 1}
    }, {
        "devices": {
            DEVICEID: {"device_class": "switch"}
        }
    })
    assert isinstance(entities[0], SwitchEntity)
    assert not isinstance(entities[0], LightEntity)

    # restore changes
    devices.set_default_class("switch")


def test_device_class():
    reg, entities = get_entitites({
        "extra": {"uiid": 1}
    }, {
        "devices": {
            DEVICEID: {"device_class": "light"}
        }
    })

    entity: XSwitch = entities[0]
    assert entity.state is None

    reg.cloud.dispatcher_send(SIGNAL_UPDATE, {
        "deviceid": DEVICEID, "params": {"switch": "on"}
    })
    assert entity.state == "on"

    assert isinstance(entity, LightEntity)
    assert not isinstance(entity, SwitchEntity)


def test_device_class2():
    reg, entities = get_entitites({
        "extra": {"uiid": 2},
        "params": {
            'switches': [
                {'switch': 'on', 'outlet': 0},
                {'switch': 'off', 'outlet': 1},
                {'switch': 'off', 'outlet': 2},
                {'switch': 'off', 'outlet': 3}
            ],
        }
    }, {
        "devices": {
            DEVICEID: {"device_class": ["light", "fan"]}
        }
    })

    light: XSwitches = entities[0]
    assert isinstance(light, LightEntity)
    assert light.state == "on"

    fan: XSwitches = entities[1]
    assert isinstance(fan, FanEntity)
    assert fan.state == "off"


def test_light_group():
    reg, entities = get_entitites({
        "extra": {"uiid": 2},
        "params": {
            'switches': [
                {'switch': 'on', 'outlet': 0},
                {'switch': 'on', 'outlet': 1},
                {'switch': 'off', 'outlet': 2},
                {'switch': 'off', 'outlet': 3}
            ],
        }
    }, {
        "devices": {
            DEVICEID: {"device_class": [{"light": [2, 1]}]}
        }
    })

    light: XLightGroup = entities[0]
    assert light.state == "on" and light.brightness == 255

    await_(light.async_turn_on(brightness=128))
    assert reg.send_args[1]["switches"] == [
        {'outlet': 1, 'switch': 'on'}, {'outlet': 0, 'switch': 'off'}
    ]
    assert light.brightness == 128

    await_(light.async_turn_on(brightness=0))
    assert reg.send_args[1]["switches"] == [
        {'outlet': 1, 'switch': 'off'}, {'outlet': 0, 'switch': 'off'}
    ]

    await_(light.async_turn_on())
    assert reg.send_args[1]["switches"] == [
        {'outlet': 1, 'switch': 'on'}, {'outlet': 0, 'switch': 'on'}
    ]
