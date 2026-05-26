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


def test_non_confirm_cancels_pending_high():
    policy = make_policy()
    policy.evaluate("close tab", now=0)
    cmd, reason = policy.evaluate("scroll down", now=1)
    assert cmd["name"] == "scroll_down"
    assert reason == "ok"
    assert policy.pending_command is None


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
