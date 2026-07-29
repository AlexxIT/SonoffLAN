from custom_components.sonoff.diagnostics import redact_diagnostics_data


def test_diagnostics_redact_credentials_identifiers_and_log_values():
    appsecret = "a-secret-that-must-never-be-exported"
    deviceid = "1000abcdef"
    device_name = "Luce Salotto Andrea"
    data = {
        "appid": "private-app-id",
        "appsecret": appsecret,
        "deviceid": deviceid,
        "parentid": "1000parent",
        "host": "192.168.100.50",
        "apikey": "private-api-key",
        "uid": "private-user-id",
        "sequence": "123456789",
        "timestamp": 1234567890,
        "param_keys": ["switch"],
        "latency_ms": 120,
        "message": f"device={deviceid} name={device_name} secret={appsecret}",
    }

    result = redact_diagnostics_data(data, (appsecret, deviceid, device_name))

    for key in (
        "appid",
        "appsecret",
        "deviceid",
        "parentid",
        "host",
        "apikey",
        "uid",
        "sequence",
        "timestamp",
    ):
        assert result[key] == "***"
    assert result["param_keys"] == ["switch"]
    assert result["latency_ms"] == 120
    assert result["message"] == "device=*** name=*** secret=***"
