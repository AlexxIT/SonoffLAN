from homeassistant.const import REQUIRED_PYTHON_VER

from custom_components.sonoff import *
from custom_components.sonoff.binary_sensor import *
from custom_components.sonoff.button import *
from custom_components.sonoff.climate import *
from custom_components.sonoff.config_flow import *
from custom_components.sonoff.cover import *
from custom_components.sonoff.diagnostics import *
from custom_components.sonoff.fan import *
from custom_components.sonoff.light import *
from custom_components.sonoff.number import *
from custom_components.sonoff.remote import *
from custom_components.sonoff.sensor import *
from custom_components.sonoff.switch import *
from custom_components.sonoff.system_health import *
from . import init


def test_backward():
    # https://github.com/home-assistant/core/blob/2023.2.0/homeassistant/const.py
    assert (MAJOR_VERSION, MINOR_VERSION) >= (2023, 2)
    assert REQUIRED_PYTHON_VER >= (3, 10, 0)

    assert async_setup_entry
    assert async_get_config_entry_diagnostics
    assert system_health_info

    assert FlowHandler

    assert XBinarySensor
    assert XRemoteButton
    assert XClimateTH
    assert XCover
    assert XFan
    assert XOnOffLight
    assert XNumber
    assert XRemote
    assert XSensor
    assert XSwitch


def test_2024_1_cached_properties():
    _, entities = init({"extra": {"uiid": 5}})
    sensor: SensorEntity = next(e for e in entities if e.uid == "energy")
    assert sensor.device_class == SensorDeviceClass.ENERGY

    _, entities = init({"extra": {"uiid": 1256}})
    sensor: SensorEntity = next(e for e in entities)
    assert sensor.should_poll is False


def test_2024_2_climate():
    _, entities = init({"extra": {"uiid": 15}})
    climate: ClimateEntity = next(e for e in entities if isinstance(e, XClimateTH))
    if (MAJOR_VERSION, MINOR_VERSION) >= (2024, 2):
        assert climate.supported_features == (
            ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
    else:
        assert (
            climate.supported_features == ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        )


def test_2024_8_fan():
    _, entities = init({"extra": {"uiid": 34}})
    fan: FanEntity = next(e for e in entities if isinstance(e, XFan))
    if (MAJOR_VERSION, MINOR_VERSION) >= (2024, 8):
        assert fan.supported_features == (
            FanEntityFeature.SET_SPEED
            | FanEntityFeature.PRESET_MODE
            | FanEntityFeature.TURN_OFF
            | FanEntityFeature.TURN_ON
        )
    else:
        assert fan.supported_features == (
            FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
        )
