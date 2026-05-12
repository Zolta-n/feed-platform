from __future__ import annotations

import json

from niche.web.template_filters import as_bullets


def test_valid_json_list_of_strings_returns_list():
    value = json.dumps(["First point.", "Second point.", "Third point."])
    assert as_bullets(value) == ["First point.", "Second point.", "Third point."]


def test_strips_whitespace_from_each_bullet():
    value = json.dumps(["  point a  ", " point b "])
    assert as_bullets(value) == ["point a", "point b"]


def test_plain_text_returns_none():
    assert as_bullets("Just a regular paragraph summary.") is None


def test_json_object_returns_none():
    assert as_bullets(json.dumps({"key": "value"})) is None


def test_empty_string_returns_none():
    assert as_bullets("") is None


def test_none_returns_none():
    assert as_bullets(None) is None


def test_non_string_returns_none():
    assert as_bullets(123) is None
    assert as_bullets(["already", "a", "list"]) is None


def test_empty_json_list_returns_none():
    assert as_bullets("[]") is None


def test_list_with_non_strings_returns_none():
    assert as_bullets(json.dumps(["valid", 42, "another"])) is None


def test_list_with_blank_strings_returns_none():
    assert as_bullets(json.dumps(["valid", "", "another"])) is None


def test_malformed_json_returns_none():
    assert as_bullets("[unclosed bracket") is None
