from custom_components.sonoff.core.ewelink import XRegistry
from custom_components.sonoff.core.ewelink.cloud import cloud_error_event


def test_cloud_error_event_is_redacted():
    event = cloud_error_event(
        {
            "error": 411,
            "deviceid": "1000123abc",
            "sequence": "123",
            "apikey": "must-not-leak",
            "uid": "must-not-leak",
        }
    )

    assert event == {
        "error": 411,
        "deviceid": "1000123abc",
        "sequence": "123",
        "action": None,
    }


def test_cloud_error_records_parent_context_without_running_loop():
    registry = XRegistry(None)
    parent = {"deviceid": "10022bd4a5", "productModel": "ZBBridge-P"}
    device = {"deviceid": "1000123abc", "parent": parent}
    registry.devices = {device["deviceid"]: device}
    registry.cloud_pending["123"] = {
        "action": "update",
        "param_keys": ["switch"],
        "safe_retry": True,
        "origin": "command",
        "transport": "cloud",
        "transport_reason": "zbbridge_child_lan_unsupported",
        "device_rssi": -73,
        "bridge_rssi": -43,
        "bridge_framework": "3.3.0",
    }

    registry.cloud_error({"error": 411, "deviceid": device["deviceid"], "sequence": "123"})

    assert device["last_cloud_error"]["code"] == 411
    assert device["last_cloud_error"]["parent_model"] == "ZBBridge-P"
    assert device["last_cloud_error"]["param_keys"] == ["switch"]
    assert device["last_cloud_error"]["transport_reason"] == "zbbridge_child_lan_unsupported"
    assert device["last_cloud_error"]["device_rssi"] == -73
    assert device["last_cloud_error"]["bridge_framework"] == "3.3.0"


def test_only_explicit_switch_values_are_safe_to_retry():
    assert XRegistry.is_safe_retry({"switch": "on"})
    assert XRegistry.is_safe_retry({"switch": "off"})
    assert not XRegistry.is_safe_retry({"switch": "toggle"})
    assert not XRegistry.is_safe_retry({"switch": "on", "brightness": 10})
    assert not XRegistry.is_safe_retry(None)


def test_known_switch_state_skips_only_a_redundant_command():
    device = {"params": {"switch": "off"}}

    assert XRegistry.is_redundant_switch_command(device, {"switch": "off"})
    assert not XRegistry.is_redundant_switch_command(device, {"switch": "on"})
    assert not XRegistry.is_redundant_switch_command(device, {"switch": "toggle"})
    assert not XRegistry.is_redundant_switch_command(
        device, {"switch": "off", "brightness": 50}
    )


def test_reconciliation_requires_the_matching_response_and_state():
    command = {"params": {"switch": "on"}}
    device = {"cloud_seq": "query-1", "params": {"switch": "on"}}

    assert XRegistry.is_command_confirmed(device, command, "query-1")
    assert not XRegistry.is_command_confirmed(device, command, "query-2")

    device["params"]["switch"] = "off"
    assert not XRegistry.is_command_confirmed(device, command, "query-1")


def test_cloud_context_marks_zbbridge_children_as_cloud_only():
    context = XRegistry.cloud_context(
        {
            "params": {"subDevRssi": -73},
            "parent": {
                "deviceid": "10022bd4a5",
                "productModel": "ZBBridge-P",
                "params": {"rssi": -43, "hostVersion": "3.3.0"},
            },
        }
    )

    assert context == {
        "transport": "cloud",
        "device_rssi": -73,
        "parentid": "10022bd4a5",
        "parent_model": "ZBBridge-P",
        "bridge_rssi": -43,
        "bridge_framework": "3.3.0",
        "transport_reason": "zbbridge_child_lan_unsupported",
    }
