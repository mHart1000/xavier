"""Activation policy: wake stripping, sessions, risk tiers, confirmation."""

import pytest

from core.activation_policy import ActivationPolicy, risk_tier


def make_policy(mode="vad_continuous", allow_continuous=True, confirm_high=True):
    listener = {"mode": mode, "wake_phrase": "browser", "session_timeout_seconds": 300,
                "pre_roll_ms": 500, "min_speech_ms": 300, "end_silence_ms": 700,
                "max_segment_seconds": 8}
    safety = {"confirm_high_risk_commands": confirm_high,
              "allow_continuous_commands_without_wake": allow_continuous}
    return ActivationPolicy(listener, safety)


def test_low_command_passes():
    cmd, reason = make_policy().evaluate("scroll down", now=0)
    assert reason == "ok"
    assert cmd["name"] == "scroll_down"


def test_wake_phrase_stripped():
    cmd, reason = make_policy().evaluate("browser show hints", now=0)
    assert reason == "ok"
    assert cmd["name"] == "hints_show"


def test_wake_only_activates_session_without_command():
    cmd, reason = make_policy().evaluate("browser", now=0)
    assert cmd is None
    assert reason == "wake_only"


def test_no_match():
    cmd, reason = make_policy().evaluate("banana pancakes", now=0)
    assert cmd is None
    assert reason == "no_match"


def test_high_risk_requires_confirmation():
    policy = make_policy()
    cmd, reason = policy.evaluate("close tab", now=0)
    assert cmd is None
    assert reason == "await_confirm"

    cmd, reason = policy.evaluate("confirm", now=1)
    assert reason == "confirmed"
    assert cmd["name"] == "tab_close"


def test_confirmed_variant_also_confirms():
    policy = make_policy()
    policy.evaluate("close tab", now=0)
    cmd, reason = policy.evaluate("confirmed", now=1)
    assert reason == "confirmed"
    assert cmd["name"] == "tab_close"


def test_non_confirm_cancels_pending_high():
    policy = make_policy()
    policy.evaluate("close tab", now=0)
    cmd, reason = policy.evaluate("scroll down", now=1)
    assert cmd["name"] == "scroll_down"
    assert reason == "ok"
    assert policy.pending_command is None


def test_cancel_aborts_pending_high_risk():
    policy = make_policy()
    policy.evaluate("close tab", now=0)
    cmd, reason = policy.evaluate("cancel", now=1)
    assert cmd is None
    assert reason == "cancelled"
    assert policy.pending_command is None


def test_cancel_without_pending_emits_command():
    cmd, reason = make_policy().evaluate("cancel", now=0)
    assert cmd["name"] == "cancel"
    assert reason == "ok"


def test_confirmation_times_out():
    policy = make_policy()
    policy.evaluate("close tab", now=0)
    cmd, reason = policy.evaluate("confirm", now=100)  # > CONFIRM_TIMEOUT_SECONDS
    assert cmd is None
    assert reason == "no_match"  # pending expired; "confirm" alone is not a command


def test_continuous_disabled_without_wake_rejected():
    cmd, reason = make_policy(allow_continuous=False).evaluate("scroll down", now=0)
    assert cmd is None
    assert reason == "no_session"


def test_continuous_disabled_but_wake_present():
    cmd, reason = make_policy(allow_continuous=False).evaluate("browser scroll down", now=0)
    assert reason == "ok"
    assert cmd["name"] == "scroll_down"


def test_stubbed_mode_rejected_at_construction():
    with pytest.raises(NotImplementedError):
        make_policy(mode="adaptive_wake")


def test_risk_tier_classification():
    assert risk_tier("scroll_down") == "low"
    assert risk_tier("nav_back") == "medium"
    assert risk_tier("tab_close") == "high"
    assert risk_tier("something_unknown") == "medium"
    assert risk_tier("highlight_text") == "low"
    assert risk_tier("highlight_next") == "low"
    assert risk_tier("cancel") == "low"
    assert risk_tier("click") == "medium"
    assert risk_tier("open_new_tab") == "medium"
    assert risk_tier("input_text") == "low"
    assert risk_tier("links_show") == "low"
    assert risk_tier("link_select") == "low"


def test_input_enters_mode():
    policy = make_policy()
    cmd, reason = policy.evaluate("input", now=0)
    assert cmd is None
    assert reason == "input_start"
    assert policy.in_input_mode is True


def test_input_same_breath_payload_is_typed():
    policy = make_policy()
    cmd, reason = policy.evaluate("input buy some milk", now=0)
    assert reason == "input_start"
    assert cmd["name"] == "input_text"
    assert cmd["args"]["text"] == "buy some milk"
    assert policy.in_input_mode is True


def test_input_dictation_preserves_casing_and_punctuation():
    policy = make_policy()
    policy.evaluate("input", now=0)
    cmd, reason = policy.evaluate("Don't forget the milk.", now=1)
    assert reason == "input"
    assert cmd["name"] == "input_text"
    assert cmd["args"]["text"] == "Don't forget the milk."


def test_input_mode_suppresses_commands():
    # In input mode a command phrase is dictated verbatim, not executed.
    policy = make_policy()
    policy.evaluate("input", now=0)
    cmd, reason = policy.evaluate("scroll down", now=1)
    assert reason == "input"
    assert cmd["name"] == "input_text"
    assert cmd["args"]["text"] == "scroll down"


def test_end_input_exits_mode():
    policy = make_policy()
    policy.evaluate("input", now=0)
    cmd, reason = policy.evaluate("end input", now=1)
    assert cmd is None
    assert reason == "input_end"
    assert policy.in_input_mode is False


def test_wake_then_input_enters_mode():
    policy = make_policy()
    cmd, reason = policy.evaluate("browser input", now=0)
    assert reason == "input_start"
    assert cmd is None  # wake + bare trigger, nothing to type yet
    assert policy.in_input_mode is True


def test_wake_then_input_with_payload():
    policy = make_policy()
    cmd, reason = policy.evaluate("browser input hello there", now=0)
    assert reason == "input_start"
    assert cmd["args"]["text"] == "hello there"


def test_input_silence_timeout_and_refresh():
    policy = make_policy()  # default input_silence_timeout = 5
    policy.evaluate("input", now=0)            # deadline = 5
    assert policy.input_expired(4) is False
    policy.refresh_input_activity(4)            # still speaking: deadline = 9
    assert policy.input_expired(5) is False
    assert policy.input_expired(9) is True
    assert policy.exit_input_mode() is True
    assert policy.in_input_mode is False
    assert policy.input_expired(20) is False    # no longer in mode
