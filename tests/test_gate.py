"""Gate traces use synthetic identities and the reported command/report timing."""

import asyncio
from unittest.mock import AsyncMock

import pytest
import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError

from custom_components.sonoff import CONFIG_SCHEMA
from custom_components.sonoff.core.ewelink import (
    SIGNAL_DEVICE_EVENT,
    SIGNAL_UPDATE,
    XRegistry,
)
from custom_components.sonoff.cover import XCover216, XCover216Tracked

from . import DEVICEID, init


@pytest.fixture
def make_gate(monkeypatch):
    # The upstream test helper replaces these globally; restore them after tests.
    monkeypatch.setattr(asyncio, "create_task", asyncio.create_task)
    monkeypatch.setattr(asyncio, "get_running_loop", asyncio.get_running_loop)

    def make(door=0, tracking=True, uiid=216):
        params = {} if door is None else {"doorState": door}
        reg, entities = init(
            {"extra": {"uiid": uiid}, "params": params},
            {"devices": {DEVICEID: {"gate_state_tracking": tracking}}},
        )
        # Exercise the real transport selection and command sequence forwarding.
        reg.send = XRegistry.send.__get__(reg)
        reg.cloud.send = AsyncMock(return_value="online")
        return reg, entities[0]

    return make


def message(reg, params, *, agent="device", identity=None, action="update"):
    msg = {"deviceid": DEVICEID, "params": params, "userAgent": agent}
    if action is not None:
        msg["action"] = action
    if identity is not None:
        msg["sequence" if agent == "app" else "d_seq"] = identity
    reg.call(reg.cloud._process_ws_msg(msg))


def command(reg, value, identity):
    message(reg, {"switch": value}, agent="app", identity=identity)


def report(reg, value, identity):
    message(reg, {"doorState": value}, identity=identity)


def assert_gate(gate, state, operation, fully_open=None):
    actual = gate.hass.states.get(gate.entity_id)
    assert actual.state == state
    # Home Assistant omits extra attributes while an entity is unavailable.
    attrs = gate.extra_state_attributes if state == "unavailable" else actual.attributes
    assert attrs["operation_state"] == operation
    assert attrs["fully_open"] is fully_open
    assert "current_position" not in actual.attributes


def test_continuous_opening_and_closing(make_gate):
    reg, gate = make_gate()
    assert gate.unique_id == DEVICEID
    assert gate.supported_features == 11  # open, close, stop, no position control
    assert gate.assumed_state
    assert_gate(gate, "closed", "closed", False)
    command(reg, "on", "cmd-1")
    assert_gate(gate, "opening", "opening")
    report(reg, 1, 5830)
    assert_gate(gate, "opening", "opening")
    report(reg, 1, 30502)
    assert_gate(gate, "open", "open", True)
    command(reg, "off", "cmd-2")
    assert_gate(gate, "closing", "closing")
    report(reg, 1, 32000)
    assert_gate(gate, "closing", "closing")
    report(reg, 0, 36341)
    assert_gate(gate, "closed", "closed", False)


def test_opening_with_three_pauses(make_gate):
    reg, gate = make_gate()
    # Each on starts a new segment, including resumes near the open endstop.
    for index in range(4):
        command(reg, "on", f"open-{index}")
        report(reg, 1, 100 + index)
        assert_gate(gate, "opening", "opening")
        if index < 3:
            command(reg, "pause", f"pause-{index}")
            assert_gate(gate, "open", "stopped")
    report(reg, 1, 110)
    assert_gate(gate, "open", "open", True)


def test_pause_while_closing_does_not_claim_closed(make_gate):
    reg, gate = make_gate(1)
    command(reg, "off", "close")
    report(reg, 1, 10)
    command(reg, "pause", "stop")
    assert_gate(gate, "open", "stopped")


def test_pause_before_first_report_does_not_reuse_old_closed_state(make_gate):
    reg, gate = make_gate(0)
    command(reg, "on", "open")
    command(reg, "pause", "stop")
    assert_gate(gate, "unknown", "stopped")
    report(reg, 1, 1)
    assert_gate(gate, "open", "stopped")


@pytest.mark.parametrize(
    "door,state,full",
    [(0, "closed", False), (1, "open", None), (None, "unknown", None)],
)
def test_startup_uses_position_but_not_stale_command(make_gate, door, state, full):
    reg, gate = make_gate(door)
    assert_gate(gate, state, "closed" if door == 0 else "unknown", full)
    message(reg, {"switch": "on", "doorState": 1}, action=None)
    assert_gate(gate, state, "closed" if door == 0 else "unknown", full)


def test_identical_values_are_distinct_events_but_replayed_ids_are_not(make_gate):
    reg, gate = make_gate()
    command(reg, "on", "open")
    report(reg, 1, 50)
    report(reg, 1, "50")
    assert_gate(gate, "opening", "opening")
    # Device identifiers can decrease or wrap; they are not timestamps.
    report(reg, 1, 0)
    assert_gate(gate, "open", "open", True)


def test_duplicates_across_pause_and_reversal(make_gate):
    reg, gate = make_gate()
    command(reg, "on", "open-1")
    report(reg, 1, 1)
    command(reg, "pause", "pause")
    command(reg, "on", "open-2")
    report(reg, 1, 1)  # delayed replay from previous segment
    report(reg, 1, 2)
    assert_gate(gate, "opening", "opening")
    command(reg, "off", "close")
    command(reg, "on", "open-1")  # delayed command echo
    report(reg, 1, 3)
    assert_gate(gate, "closing", "closing")
    report(reg, 0, 4)
    assert_gate(gate, "closed", "closed", False)


def test_repeated_open_is_a_new_segment(make_gate):
    reg, gate = make_gate()
    command(reg, "on", "open-1")
    report(reg, 1, 1)
    command(reg, "on", "open-2")
    report(reg, 1, 2)
    assert_gate(gate, "opening", "opening")
    report(reg, 1, 3)
    assert_gate(gate, "open", "open", True)


def test_old_closed_report_cannot_override_a_new_opening(make_gate):
    reg, gate = make_gate()
    report(reg, 0, 1)
    command(reg, "on", "open")
    report(reg, 0, 1)
    assert_gate(gate, "opening", "opening")
    report(reg, 0, 2)  # A distinct physical closed report is authoritative.
    assert_gate(gate, "closed", "closed", False)


def test_restart_does_not_restore_an_opening_sequence(make_gate):
    reg, gate = make_gate()
    command(reg, "on", "open")
    report(reg, 1, 1)
    restarted_reg, restarted_gate = make_gate(1)
    report(restarted_reg, 1, 1)
    report(restarted_reg, 1, 2)
    assert_gate(restarted_gate, "open", "unknown")


@pytest.mark.parametrize("action", [None, "sysmsg"])
@pytest.mark.parametrize("door", [0, 1])
def test_query_and_snapshot_cannot_complete_or_cancel_opening(make_gate, action, door):
    reg, gate = make_gate()
    command(reg, "on", "open")
    report(reg, 1, 1)
    message(reg, {"switch": "off", "doorState": door}, identity=2, action=action)
    assert_gate(gate, "opening", "opening")
    report(reg, 1, 3)
    assert_gate(gate, "open", "open", True)


def test_command_payload_door_state_is_not_a_device_report(make_gate):
    reg, gate = make_gate()
    message(reg, {"switch": "on", "doorState": 1}, agent="app", identity="open")
    report(reg, 1, 1)
    assert_gate(gate, "opening", "opening")
    message(reg, {"switch": "off", "doorState": 1}, identity=2)
    assert_gate(gate, "open", "open", True)  # cached device switch is ignored


def test_missing_report_does_not_complete_opening(make_gate):
    reg, gate = make_gate()
    command(reg, "on", "open")
    report(reg, 1, 1)  # Could be the first report or only the final report.
    assert_gate(gate, "opening", "opening")


def test_missing_identity_invalidates_inference(make_gate):
    reg, gate = make_gate()
    command(reg, "on", "open")
    report(reg, 1, 1)
    report(reg, 1, None)
    report(reg, 1, 2)
    assert_gate(gate, "open", "unknown")
    report(reg, 0, 3)
    assert_gate(gate, "closed", "closed", False)


def test_unidentified_command_cannot_arm_completion(make_gate):
    reg, gate = make_gate()
    command(reg, "on", None)
    report(reg, 1, 1)
    report(reg, 1, 2)
    assert_gate(gate, "opening", "opening")


def test_reports_without_command_do_not_invent_direction_or_fully_open(make_gate):
    reg, gate = make_gate()
    report(reg, 1, 1)
    report(reg, 1, 2)
    assert_gate(gate, "open", "unknown")


@pytest.mark.parametrize("lan_available", [False, True])
def test_reconnect_discards_sequence_and_keeps_replay_history(make_gate, lan_available):
    reg, gate = make_gate()
    command(reg, "on", "open-1")
    report(reg, 1, 1)
    if lan_available:
        reg.local.online = True
        gate.device["local"] = True
    reg.cloud.set_online(False)
    assert_gate(gate, "unknown" if lan_available else "unavailable", "unknown")
    reg.cloud.set_online(True)
    assert_gate(gate, "unknown", "unknown")
    report(reg, 1, 2)
    assert_gate(gate, "open", "unknown")
    command(reg, "on", "open-2")
    report(reg, 1, 1)
    report(reg, 1, 3)
    assert_gate(gate, "opening", "opening")
    report(reg, 1, 4)
    assert_gate(gate, "open", "open", True)


def test_device_offline_even_with_lan_available_discards_tracking(make_gate):
    reg, gate = make_gate()
    reg.local.online = True
    gate.device["local"] = True
    command(reg, "on", "open")
    report(reg, 1, 1)
    message(reg, {"online": False}, action="sysmsg")
    assert_gate(gate, "unknown", "unknown")
    report(reg, 1, 2)
    assert_gate(gate, "open", "unknown")


@pytest.mark.parametrize("door", [0, 1])
def test_unqualified_lan_reply_does_not_claim_an_endstop(make_gate, door):
    reg, gate = make_gate()
    command(reg, "on", "open")
    report(reg, 1, 1)
    reg.local.dispatcher_send(
        SIGNAL_UPDATE, {"deviceid": DEVICEID, "params": {"doorState": door}}
    )
    assert_gate(gate, "open" if door else "unknown", "unknown")


@pytest.mark.parametrize("value", [True, False, "1", 2, -1, None])
def test_invalid_door_values_are_not_endstop_events(make_gate, value):
    reg, gate = make_gate()
    command(reg, "on", "open")
    report(reg, 1, 1)
    report(reg, value, 2)
    assert_gate(gate, "opening", "opening")


def test_ha_commands_keep_transport_and_deduplicate_their_echoes(make_gate):
    reg, gate = make_gate()
    reg.call(gate.async_open_cover())
    sent = reg.cloud.send.call_args
    assert sent.args[1] == {"switch": "on"}
    sequence = sent.args[2]
    assert isinstance(sequence, str)
    report(reg, 1, 1)
    command(reg, "on", sequence)
    report(reg, 1, 2)
    assert_gate(gate, "open", "open", True)
    reg.call(gate.async_stop_cover())
    assert reg.cloud.send.call_args.args[1] == {"switch": "pause"}
    assert_gate(gate, "open", "stopped", True)
    reg.call(gate.async_close_cover())
    assert reg.cloud.send.call_args.args[1] == {"switch": "off"}
    assert_gate(gate, "closing", "closing")
    assert reg.cloud.send.call_count == 3  # No extra query can produce a false report.


@pytest.mark.parametrize("failure", ["offline", "E#503", None, RuntimeError("offline")])
def test_failed_command_does_not_leave_assumed_movement(make_gate, failure):
    reg, gate = make_gate()
    if isinstance(failure, Exception):
        reg.cloud.send.side_effect = failure
    else:
        reg.cloud.send.return_value = failure
    with pytest.raises((HomeAssistantError, RuntimeError)):
        reg.call(gate.async_open_cover())
    assert_gate(gate, "unknown", "unknown")


def test_failed_ack_does_not_overwrite_new_physical_closed_report(make_gate):
    reg, gate = make_gate(1)

    async def send(*args, **kwargs):
        reg.cloud.dispatcher_send(
            SIGNAL_UPDATE,
            {
                "deviceid": DEVICEID,
                "action": "update",
                "userAgent": "device",
                "d_seq": 1,
                "params": {"doorState": 0},
            },
        )
        return "offline"

    reg.cloud.send.side_effect = send
    with pytest.raises(HomeAssistantError):
        reg.call(gate.async_close_cover())
    assert_gate(gate, "closed", "closed", False)


def test_tracking_is_opt_in_and_only_for_uiid216(make_gate):
    reg, gate = make_gate(tracking=False)
    assert type(gate) is XCover216
    command(reg, "on", "open")
    report(reg, 1, 1)
    assert gate.state == "open"  # Preserve existing default behaviour.
    assert "operation_state" not in gate.hass.states.get(gate.entity_id).attributes
    assert not reg.dispatcher.get(DEVICEID + SIGNAL_DEVICE_EVENT)
    _, tracked = make_gate()
    assert type(tracked) is XCover216Tracked
    _, other = make_gate(uiid=1)
    assert not isinstance(other, XCover216Tracked)
    _, default_again = make_gate(tracking=False)
    assert type(default_again) is XCover216  # Shared device specification is unchanged.


@pytest.mark.parametrize("status", ["online", "offline"])
def test_existing_transport_callers_keep_their_return_contract(make_gate, status):
    reg, gate = make_gate()
    reg.cloud.send.return_value = status
    loop = asyncio.new_event_loop()
    try:
        # Existing energy sensors inspect this result; do not change their logic.
        assert loop.run_until_complete(reg.send(gate.device, query_cloud=False)) is None
        assert (
            loop.run_until_complete(
                reg.send(gate.device, query_cloud=False, return_status=True)
            )
            == status
        )
    finally:
        loop.close()


def test_configuration_accepts_boolean_only():
    config = {"sonoff": {"devices": {DEVICEID: {"gate_state_tracking": True}}}}
    assert (
        CONFIG_SCHEMA(config)["sonoff"]["devices"][DEVICEID]["gate_state_tracking"]
        is True
    )
    with pytest.raises(vol.Invalid):
        CONFIG_SCHEMA(
            {"sonoff": {"devices": {DEVICEID: {"gate_state_tracking": "invalid"}}}}
        )
