from custom_components.sonoff.climate import XClimateTH
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
