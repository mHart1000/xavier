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


def test_highlight_ordinal_word():
    cmd = parse_command("highlight third expand")
    assert cmd["name"] == "highlight_text"
    assert cmd["args"]["text"] == "expand"
    assert cmd["args"]["ordinal"] == 3


def test_highlight_no_ordinal_omits_arg():
    assert "ordinal" not in parse_command("highlight expand")["args"]


def test_highlight_bare_ordinal_is_literal():
    # "highlight first" with no following target stays a literal "first" match.
    cmd = parse_command("highlight first")
    assert cmd["args"]["text"] == "first"
    assert "ordinal" not in cmd["args"]


def test_highlight_numeric_ordinal():
    cmd = parse_command("highlight 2nd comment")
    assert cmd["args"]["ordinal"] == 2
    assert cmd["args"]["text"] == "comment"


def test_highlight_trailing_cardinal():
    # "highlight expand three" == "highlight third expand".
    cmd = parse_command("highlight expand three")
    assert cmd["args"]["text"] == "expand"
    assert cmd["args"]["ordinal"] == 3


def test_highlight_trailing_digit():
    cmd = parse_command("highlight expand 3")
    assert cmd["args"]["text"] == "expand"
    assert cmd["args"]["ordinal"] == 3


def test_highlight_leading_cardinal_stays_literal():
    # Cardinals are trailing-only, so a leading "one" is part of the target.
    cmd = parse_command("highlight one piece")
    assert cmd["args"]["text"] == "one piece"
    assert "ordinal" not in cmd["args"]


def test_highlight_trailing_homonym_to():
    # Whisper hears "expand two" as "expand to".
    cmd = parse_command("highlight expand to")
    assert cmd["args"]["text"] == "expand"
    assert cmd["args"]["ordinal"] == 2
    assert cmd["args"]["literal"] == "expand to"


def test_highlight_trailing_homonym_for():
    cmd = parse_command("highlight expand for")
    assert cmd["args"]["ordinal"] == 4
    assert cmd["args"]["literal"] == "expand for"


def test_highlight_trailing_keeps_literal():
    assert parse_command("highlight expand three")["args"]["literal"] == "expand three"


def test_highlight_leading_ordinal_has_no_literal():
    assert "literal" not in parse_command("highlight third expand")["args"]


def test_clear_highlights_parses():
    assert parse_command("clear highlights")["name"] == "clear_highlights"


def test_next_previous_parse():
    assert parse_command("next")["name"] == "highlight_next"
    assert parse_command("previous")["name"] == "highlight_previous"


def test_next_tab_still_parses():
    # bare "next" cycles matches, but "next tab" must still switch tabs.
    assert parse_command("next tab")["name"] == "tab_next"
    assert parse_command("previous tab")["name"] == "tab_prev"


def test_cancel_parses():
    assert parse_command("cancel")["name"] == "cancel"


def test_open_new_tab_parses():
    assert parse_command("open in new tab")["name"] == "open_new_tab"
    assert parse_command("control click")["name"] == "open_new_tab"


def test_plain_new_tab_still_parses():
    # "open in new tab" must not collide with the plain open-a-tab commands.
    assert parse_command("new tab")["name"] == "tab_new"
    assert parse_command("open tab")["name"] == "tab_new"


def test_command_grammar_contains_highlight():
    assert "highlight" in command_grammar()
