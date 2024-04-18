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
    assert REQUIRED_PYTHON_VER >= (3, 10, 0)

    assert async_setup_entry, async_unload_entry
    assert XBinarySensor
    assert XRemoteButton
    assert XClimateTH
    assert SonoffLANFlowHandler
    assert XCover
    assert async_get_config_entry_diagnostics
    assert XFan
    assert XOnOffLight
    assert XNumber
    assert XRemote
    assert XSensor
    assert XSwitch
    assert system_health_info


def test_2024_1_cached_properties():
    _, entities = init({"extra": {"uiid": 5}})
    sensor: SensorEntity = next(e for e in entities if e.uid == "energy")
    assert sensor.device_class == SensorDeviceClass.ENERGY

    _, entities = init({"extra": {"uiid": 1256}})
    sensor: SensorEntity = next(e for e in entities)
    assert sensor.should_poll is False
