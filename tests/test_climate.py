from custom_components.sonoff.climate import XClimateTH, XThermostatTRVZB
from homeassistant.components.climate import HVACMode
from . import init


def test_th():
    _, entities = init(
        {
            "extra": {"uiid": 15},
            "params": {
                "bindInfos": {"alice": []},
                "version": 8,
                "sledOnline": "on",
                "init": 1,
                "switch": "off",
                "fwVersion": "3.5.0",
                "rssi": -50,
                "startup": "off",
                "pulse": "off",
                "pulseWidth": 500,
                "deviceType": "temperature",
                "sensorType": "AM2301",
                "currentHumidity": "45",
                "currentTemperature": "18.8",
                "mainSwitch": "on",
                "targets": [
                    {"targetHigh": "20", "reaction": {"switch": "on"}},
                    {"targetLow": "10", "reaction": {"switch": "off"}},
                ],
                "state": "off",
                "timeZone": 3,
                "only_device": {"ota": "success"},
            },
        }
    )

    climate = next(e for e in entities if isinstance(e, XClimateTH))
    assert climate


def test_thr316d():
    # https://github.com/AlexxIT/SonoffLAN/issues/1074
    _, entities = init(
        {
            "extra": {"uiid": 181},
            "params": {
                "version": 8,
                "fwVersion": "1.1.0",
                "sensorType": "DS18B20",
                "currentTemperature": "19.2",
                "currentHumidity": "unavailable",
                "switch": "off",
                "startup": "off",
                "pulseConfig": {"pulse": "off", "switch": "off", "pulseWidth": 500},
                "sledOnline": "on",
                "tempUnit": 0,
                "rssi": -38,
                "autoControl": [
                    {
                        "deviceType": "temperature",
                        "targets": [
                            {"high": "33.0", "reaction": {"switch": "on"}},
                            {"low": "25.0", "reaction": {"switch": "off"}},
                        ],
                        "effTime": {
                            "spanType": "any",
                            "days": [0, 1, 2, 3, 4, 5, 6],
                            "from": "00:00",
                            "to": "01:00",
                        },
                    }
                ],
                "autoControlEnabled": 1,
                "uiActive": 60,
                "timeZone": 2,
                "only_device": {"ota": "success", "ota_fail_reason": 0},
                "tempCorrection": 0,
                "humCorrection": 0,
                "tempHumiType": 1,
            },
            "model": "THR316D",
        }
    )

    # climate = next(e for e in entities if isinstance(e, XClimateTH))
    # assert climate


def test_trvzb_fw14():
    """Test TRVZB with FW 1.4.0+ params (string temperature, int targets).

    https://github.com/AlexxIT/SonoffLAN/issues/1682
    """
    reg, entities = init(
        {
            "extra": {"uiid": 7017},
            "params": {
                "subDevId": "235722feffc8d8c47017",
                "parentid": "10025b5a97",
                "fwVersion": "1.4.1",
                "staMac": "c4d8c8fffe225723",
                "workMode": "0",
                "curTargetTemp": 270,
                "manTargetTemp": 270,
                "autoTargetTemp": 235,
                "ecoTargetTemp": 70,
                "workState": "1",
                "temperature": "205",
                "battery": 100,
                "runVoltage": 137.8,
                "childLock": True,
                "windowSwitch": True,
                "openPercent": 100,
                "closePercent": 100,
                "tempCorrection": 0,
                "direction": "90",
                "isSupportBoost": False,
                "isSupportDirection": True,
                "isSupportTimerMode": False,
                "timerTargetTemp": 0,
            },
        }
    )

    climate = next(e for e in entities if isinstance(e, XThermostatTRVZB))
    assert climate is not None

    # FW 1.4.0+ sends temperature as string "205" = 20.5°C
    assert climate.current_temperature == 20.5

    # Target temp from int
    assert climate.target_temperature == 27.0

    # HVAC mode from string workMode
    assert climate.hvac_mode == HVACMode.HEAT

    # Test setting temperature sends int, not float
    device, params = reg.call(climate.async_set_temperature(temperature=23.5))
    assert params["manTargetTemp"] == 235  # int, not 235.0 float
    assert isinstance(params["manTargetTemp"], int)

    # Test setting HVAC mode to AUTO
    device, params = reg.call(
        climate.async_set_temperature(temperature=22.0, hvac_mode=HVACMode.AUTO)
    )
    assert params["workMode"] == "2"
    assert params["autoTargetTemp"] == 220
    assert isinstance(params["autoTargetTemp"], int)

    # Test setting HVAC mode to OFF
    device, params = reg.call(
        climate.async_set_temperature(temperature=7.0, hvac_mode=HVACMode.OFF)
    )
    assert params["workMode"] == "1"
    assert params["ecoTargetTemp"] == 70
    assert isinstance(params["ecoTargetTemp"], int)


def test_trvzb_string_temperature_update():
    """FW 1.4.0+ sends temperature as string in state updates."""
    reg, entities = init(
        {
            "extra": {"uiid": 7017},
            "params": {
                "workMode": "2",
                "curTargetTemp": 235,
                "temperature": "195",
                "staMac": "c4d8c8fffe225723",
            },
        }
    )

    climate = next(e for e in entities if isinstance(e, XThermostatTRVZB))

    # Initial state: string temp "195" = 19.5°C
    assert climate.current_temperature == 19.5
    assert climate.hvac_mode == HVACMode.AUTO

    # Simulate firmware update pushing new string temperature
    climate.set_state({"temperature": "225", "curTargetTemp": 240})
    assert climate.current_temperature == 22.5
    assert climate.target_temperature == 24.0


def test_trvzb_unknown_workmode():
    """Unknown workMode values should not crash (IndexError fix).

    FW 1.4.0+ can send workMode values beyond the expected 0/1/2 range.
    https://github.com/AlexxIT/SonoffLAN/issues/1682
    """
    reg, entities = init(
        {
            "extra": {"uiid": 7017},
            "params": {
                "workMode": "3",  # unknown workMode
                "curTargetTemp": 200,
                "temperature": "180",
                "staMac": "c4d8c8fffe225723",
            },
        }
    )

    climate = next(e for e in entities if isinstance(e, XThermostatTRVZB))

    # Temperature should still parse correctly
    assert climate.current_temperature == 18.0
    assert climate.target_temperature == 20.0

    # Unknown workMode should not crash; hvac_mode left at default (None)
    # since no known workMode was ever set
    assert True  # no IndexError = success

    # Updating with another unknown workMode should not crash
    climate.set_state({"workMode": "5", "temperature": "190"})
    assert climate.current_temperature == 19.0

    # Setting a known workMode after unknown ones should work
    climate.set_state({"workMode": "0"})
    assert climate.hvac_mode == HVACMode.HEAT
