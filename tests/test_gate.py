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
    assert not gate.assumed_state
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


@pytest.mark.parametrize("via_ha", [False, True])
@pytest.mark.parametrize("fully_open", [False, True])
def test_closing_pause_without_a_new_report_keeps_non_closed_position(
    make_gate, via_ha, fully_open
):
    reg, gate = make_gate()
    command(reg, "on", "open")
    report(reg, 1, 1)
    if fully_open:
        report(reg, 1, 2)
    else:
        command(reg, "pause", "pause-open")

    if via_ha:
        reg.call(gate.async_close_cover())
        reg.call(gate.async_stop_cover())
    else:
        command(reg, "off", "close")
        command(reg, "pause", "pause-close")
    assert_gate(gate, "open", "stopped")
    assert gate.assumed_state
    assert gate.hass.states.get(gate.entity_id).attributes["assumed_state"]

    # Both directions remain available after the pause, even before a new 1.
    reg.call(gate.async_open_cover())
    assert_gate(gate, "opening", "opening")
    reg.call(gate.async_stop_cover())
    assert_gate(gate, "open", "stopped")
    reg.call(gate.async_close_cover())
    assert_gate(gate, "closing", "closing")
    report(reg, 0, 3)
    assert_gate(gate, "closed", "closed", False)


def test_closing_pause_from_unknown_does_not_invent_position(make_gate):
    reg, gate = make_gate(None)
    command(reg, "off", "close")
    command(reg, "pause", "stop")
    assert_gate(gate, "unknown", "stopped")
    assert gate.assumed_state


def test_endstops_disable_redundant_commands_but_allow_reverse(make_gate):
    reg, gate = make_gate()
    assert not gate.hass.states.get(gate.entity_id).attributes.get("assumed_state")
    reg.call(gate.async_close_cover())
    reg.cloud.send.assert_not_called()
    assert_gate(gate, "closed", "closed", False)

    reg.call(gate.async_open_cover())
    assert reg.cloud.send.call_args.args[1] == {"switch": "on"}
    assert gate.assumed_state
    report(reg, 1, 1)
    assert gate.assumed_state  # One report is not the open endstop.
    report(reg, 1, 2)
    assert not gate.assumed_state
    assert not gate.hass.states.get(gate.entity_id).attributes.get("assumed_state")
    reg.cloud.send.reset_mock()
    reg.call(gate.async_open_cover())
    reg.cloud.send.assert_not_called()
    assert_gate(gate, "open", "open", True)

    # An idle stop does not lose the known endpoint or permit redundant opens.
    reg.call(gate.async_stop_cover())
    reg.cloud.send.reset_mock()
    reg.call(gate.async_open_cover())
    reg.cloud.send.assert_not_called()
    assert_gate(gate, "open", "stopped", True)
    reg.call(gate.async_close_cover())
    assert reg.cloud.send.call_args.args[1] == {"switch": "off"}
    assert gate.assumed_state
    report(reg, 0, 3)
    assert not gate.assumed_state
    assert_gate(gate, "closed", "closed", False)


def test_reconnect_reenables_commands_when_position_is_unknown(make_gate):
    reg, gate = make_gate()
    assert not gate.assumed_state
    reg.cloud.set_online(False)
    reg.cloud.set_online(True)
    assert_gate(gate, "unknown", "unknown")
    assert gate.assumed_state
    reg.call(gate.async_close_cover())
    assert reg.cloud.send.call_args.args[1] == {"switch": "off"}
    assert_gate(gate, "closing", "closing")


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
    reg, _gate = make_gate()
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


@pytest.mark.parametrize("initial,target", [("off", "on"), ("on", "off")])
def test_direction_reversal_waits_for_stop_acknowledgement(make_gate, initial, target):
    reg, gate = make_gate(1)
    command(reg, initial, "initial")
    loop = asyncio.new_event_loop()

    async def scenario():
        stopping, acknowledged = asyncio.Event(), asyncio.Event()

        async def send(device, params, sequence, **kwargs):
            # Echoes must not cancel the continuation or restart its sequence.
            reg.cloud.dispatcher_send(
                SIGNAL_UPDATE,
                {
                    "deviceid": DEVICEID,
                    "action": "update",
                    "userAgent": "app",
                    "sequence": sequence,
                    "params": params,
                },
            )
            if params["switch"] == "pause":
                stopping.set()
                await acknowledged.wait()
            return "online"

        reg.cloud.send.side_effect = send
        action = gate.async_open_cover if target == "on" else gate.async_close_cover
        task = loop.create_task(action())
        await asyncio.wait_for(stopping.wait(), timeout=1)
        assert [c.args[1]["switch"] for c in reg.cloud.send.call_args_list] == ["pause"]
        assert_gate(gate, "open", "stopped")
        acknowledged.set()
        await task

    try:
        loop.run_until_complete(scenario())
    finally:
        loop.close()
    sent = reg.cloud.send.call_args_list
    assert [c.args[1]["switch"] for c in sent] == ["pause", target]
    assert sent[0].args[2] != sent[1].args[2]
    expected = "opening" if target == "on" else "closing"
    assert_gate(gate, expected, expected)
    if target == "on":
        report(reg, 1, 1)
        assert_gate(gate, "opening", "opening")
        report(reg, 1, 2)
        assert_gate(gate, "open", "open", True)


@pytest.mark.parametrize("failure", ["offline", "E#503", None, RuntimeError("offline")])
def test_failed_stop_never_sends_the_reverse_command(make_gate, failure):
    reg, gate = make_gate(1)
    command(reg, "off", "closing")
    if isinstance(failure, Exception):
        reg.cloud.send.side_effect = failure
    else:
        reg.cloud.send.return_value = failure
    with pytest.raises((HomeAssistantError, RuntimeError)):
        reg.call(gate.async_open_cover())
    assert [c.args[1]["switch"] for c in reg.cloud.send.call_args_list] == ["pause"]
    assert_gate(gate, "unknown", "unknown")


@pytest.mark.parametrize("new_command", ["pause", "on", "off"])
def test_new_request_supersedes_a_pending_reversal(make_gate, new_command):
    reg, gate = make_gate(1)
    command(reg, "off", "closing")
    loop = asyncio.new_event_loop()

    async def scenario():
        stopping, acknowledged = asyncio.Event(), asyncio.Event()

        async def send(*args, **kwargs):
            if reg.cloud.send.call_count == 1:
                stopping.set()
                await acknowledged.wait()
            return "online"

        reg.cloud.send.side_effect = send
        first = loop.create_task(gate.async_open_cover())
        await asyncio.wait_for(stopping.wait(), timeout=1)
        action = {
            "pause": gate.async_stop_cover,
            "on": gate.async_open_cover,
            "off": gate.async_close_cover,
        }[new_command]
        latest = loop.create_task(action())
        await asyncio.sleep(0)  # Let the new request wait on the command lock.
        assert reg.cloud.send.call_count == 1
        acknowledged.set()
        await asyncio.gather(first, latest)

    try:
        loop.run_until_complete(scenario())
    finally:
        loop.close()
    assert [c.args[1]["switch"] for c in reg.cloud.send.call_args_list] == [
        "pause",
        new_command,
    ]
    expected = {
        "pause": ("open", "stopped"),
        "on": ("opening", "opening"),
        "off": ("closing", "closing"),
    }[new_command]
    assert_gate(gate, *expected)


@pytest.mark.parametrize("interruption", ["external_stop", "disconnect", "cancel"])
def test_interrupted_reversal_never_restarts_the_gate(make_gate, interruption):
    reg, gate = make_gate(1)
    command(reg, "off", "closing")
    loop = asyncio.new_event_loop()

    async def scenario():
        stopping, acknowledged = asyncio.Event(), asyncio.Event()

        async def send(*args, **kwargs):
            stopping.set()
            await acknowledged.wait()
            return "online"

        reg.cloud.send.side_effect = send
        task = loop.create_task(gate.async_open_cover())
        await asyncio.wait_for(stopping.wait(), timeout=1)
        if interruption == "external_stop":
            reg.cloud.dispatcher_send(
                SIGNAL_UPDATE,
                {
                    "deviceid": DEVICEID,
                    "action": "update",
                    "userAgent": "app",
                    "sequence": "external",
                    "params": {"switch": "pause"},
                },
            )
        elif interruption == "disconnect":
            reg.cloud.set_online(False)
        else:
            task.cancel()
        acknowledged.set()
        if interruption == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task

    try:
        loop.run_until_complete(scenario())
    finally:
        loop.close()
    assert [c.args[1]["switch"] for c in reg.cloud.send.call_args_list] == ["pause"]
    if interruption == "external_stop":
        assert_gate(gate, "open", "stopped")
    else:
        assert_gate(
            gate,
            "unavailable" if interruption == "disconnect" else "unknown",
            "unknown",
        )


def test_ordinary_device_report_during_stop_does_not_cancel_reversal(make_gate):
    reg, gate = make_gate(1)
    command(reg, "off", "closing")

    async def send(device, params, *args, **kwargs):
        if params["switch"] == "pause":
            reg.cloud.dispatcher_send(
                SIGNAL_UPDATE,
                {
                    "deviceid": DEVICEID,
                    "action": "update",
                    "userAgent": "device",
                    "d_seq": 1,
                    "params": {"doorState": 1},
                },
            )
        return "online"

    reg.cloud.send.side_effect = send
    reg.call(gate.async_open_cover())
    assert [c.args[1]["switch"] for c in reg.cloud.send.call_args_list] == [
        "pause",
        "on",
    ]
    report(reg, 1, 2)
    assert_gate(gate, "opening", "opening")
    report(reg, 1, 3)
    assert_gate(gate, "open", "open", True)


def test_stop_does_not_wait_for_a_movement_acknowledgement(make_gate):
    reg, gate = make_gate()
    loop = asyncio.new_event_loop()

    async def scenario():
        opening, acknowledged = asyncio.Event(), asyncio.Event()

        async def send(device, params, *args, **kwargs):
            if params["switch"] == "on":
                opening.set()
                await acknowledged.wait()
            return "online"

        reg.cloud.send.side_effect = send
        task = loop.create_task(gate.async_open_cover())
        await asyncio.wait_for(opening.wait(), timeout=1)
        # An explicit stop must not wait for the opening command's ACK/timeout.
        await asyncio.wait_for(gate.async_stop_cover(), timeout=1)
        assert [c.args[1]["switch"] for c in reg.cloud.send.call_args_list] == [
            "on",
            "pause",
        ]
        assert_gate(gate, "unknown", "stopped")
        acknowledged.set()
        await task
        assert_gate(gate, "unknown", "stopped")

    try:
        loop.run_until_complete(scenario())
    finally:
        loop.close()


def test_new_movement_waits_for_an_explicit_stop_acknowledgement(make_gate):
    reg, gate = make_gate(1)
    loop = asyncio.new_event_loop()

    async def scenario():
        opening, stopping = asyncio.Event(), asyncio.Event()
        open_ack, stop_ack = asyncio.Event(), asyncio.Event()

        async def send(device, params, *args, **kwargs):
            if params["switch"] == "on":
                opening.set()
                await open_ack.wait()
            elif params["switch"] == "pause":
                stopping.set()
                await stop_ack.wait()
            return "online"

        reg.cloud.send.side_effect = send
        first = loop.create_task(gate.async_open_cover())
        await asyncio.wait_for(opening.wait(), timeout=1)
        stop = loop.create_task(gate.async_stop_cover())
        await asyncio.wait_for(stopping.wait(), timeout=1)
        latest = loop.create_task(gate.async_close_cover())
        open_ack.set()
        await first
        await asyncio.sleep(0)
        assert [c.args[1]["switch"] for c in reg.cloud.send.call_args_list] == [
            "on",
            "pause",
        ]
        stop_ack.set()
        await asyncio.gather(stop, latest)

    try:
        loop.run_until_complete(scenario())
    finally:
        loop.close()
    assert [c.args[1]["switch"] for c in reg.cloud.send.call_args_list] == [
        "on",
        "pause",
        "off",
    ]
    assert_gate(gate, "closing", "closing")


def test_endstop_arriving_during_stop_avoids_redundant_close(make_gate):
    reg, gate = make_gate(1)
    command(reg, "on", "opening")

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
        return "online"

    reg.cloud.send.side_effect = send
    reg.call(gate.async_close_cover())
    assert [c.args[1]["switch"] for c in reg.cloud.send.call_args_list] == ["pause"]
    assert_gate(gate, "closed", "closed", False)


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
