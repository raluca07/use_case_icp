from rdr.v2_statement_localization import canonical_statement, statement_span


SOURCE = """\
def workflow(api, payload):
    result = api.create_payment_request(
        user=payload["user"],
        amount=payload["amount"] + 1,
    )
    return result
"""


def test_lines_in_same_multiline_call_resolve_to_same_statement():
    assert statement_span(SOURCE, 2) == (2, 5)
    assert statement_span(SOURCE, 4) == (2, 5)
    assert canonical_statement("workflow.py:2", {"workflow.py": SOURCE}) == "workflow.py:2-5"
    assert canonical_statement("workflow.py:4", {"workflow.py": SOURCE}) == "workflow.py:2-5"


def test_separate_statement_does_not_match_multiline_call():
    assert canonical_statement("workflow.py:6", {"workflow.py": SOURCE}) == "workflow.py:6-6"


def test_unknown_or_malformed_locations_remain_exact():
    assert canonical_statement("other.py:4", {"workflow.py": SOURCE}) == "other.py:4"
    assert canonical_statement("workflow.py:not-a-line", {"workflow.py": SOURCE}) == "workflow.py:not-a-line"
