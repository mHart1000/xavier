"""Parser: open_url spoken-URL parsing, command grammar, and triggers."""

from core.parser import command_grammar, command_triggers, parse_command


def test_open_url_dot():
    cmd = parse_command("open url example dot com")
    assert cmd["name"] == "open_url"
    assert cmd["args"]["url"] == "https://example.com"


def test_open_url_with_slash_path():
    cmd = parse_command("open url example dot com slash docs")
    assert cmd["args"]["url"] == "https://example.com/docs"


def test_open_url_multiple_dots():
    cmd = parse_command("open url docs dot example dot co dot uk")
    assert cmd["args"]["url"] == "https://docs.example.co.uk"


def test_open_url_without_argument_is_no_match():
    assert parse_command("open url") is None


def test_fixed_command_still_parses():
    assert parse_command("scroll down")["name"] == "scroll_down"


def test_hint_click_still_parses():
    cmd = parse_command("click a b")
    assert cmd["name"] == "hint_click"
    assert cmd["args"]["code"] == "AB"


def test_command_grammar_contains_expected_tokens():
    grammar = command_grammar()
    for token in ("scroll", "down", "click", "open", "url", "a", "z",
                  "confirm", "confirmed", "[unk]"):
        assert token in grammar


def test_command_grammar_includes_wake_word():
    assert "browser" in command_grammar(wake_phrase="browser")
    assert "browser" not in command_grammar()


def test_command_triggers():
    assert command_triggers() == ("open url", "highlight")


def test_bare_click_parses():
    cmd = parse_command("click")
    assert cmd["name"] == "click"
    assert cmd["args"] == {}


def test_highlight_text_parses():
    cmd = parse_command("highlight sign in")
    assert cmd["name"] == "highlight_text"
    assert cmd["args"]["text"] == "sign in"


def test_highlight_without_text_is_no_match():
    assert parse_command("highlight") is None


def test_clear_highlights_parses():
    assert parse_command("clear highlights")["name"] == "clear_highlights"


def test_command_grammar_contains_highlight():
    assert "highlight" in command_grammar()
