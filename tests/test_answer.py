import pytest

from rdr.answer import ANSWER_SCHEMA, normalise_record, validate_answer

GOOD = {"anything_wrong": True, "origin_call": 1, "still_wrong_records": ["a#1"]}


def test_valid_answers_pass_and_are_returned():
    assert validate_answer(GOOD) == GOOD
    null_origin = {"anything_wrong": False, "origin_call": None, "still_wrong_records": []}
    assert validate_answer(null_origin) == null_origin


def test_schema_requires_the_three_keys():
    assert sorted(ANSWER_SCHEMA["required"]) == ["anything_wrong", "origin_call", "still_wrong_records"]


@pytest.mark.parametrize("bad", [
    None,
    [],
    {"anything_wrong": True, "origin_call": 1},
    {**GOOD, "extra": 1},
    {**GOOD, "anything_wrong": "yes"},
    {**GOOD, "anything_wrong": 1},
    {**GOOD, "origin_call": True},
    {**GOOD, "origin_call": "1"},
    {**GOOD, "origin_call": 1.5},
    {**GOOD, "still_wrong_records": "a#1"},
    {**GOOD, "still_wrong_records": ["a#1", 2]},
])
def test_malformed_answers_raise(bad):
    with pytest.raises(ValueError):
        validate_answer(bad)


def test_normalise_record_strips_one_prefix_and_whitespace():
    assert normalise_record("rec:splitwise.expenses#77") == "splitwise.expenses#77"
    assert normalise_record("  rec:splitwise.expenses#77 ") == "splitwise.expenses#77"
    assert normalise_record("splitwise.expenses#77") == "splitwise.expenses#77"
    assert normalise_record("rec:rec:x#1") == "rec:x#1"
