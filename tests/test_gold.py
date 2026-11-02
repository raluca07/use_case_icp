from types import SimpleNamespace

from builders import gold_trace

from rdr.gold import eligible, gate_verdict, generator_of


def _run(digest="d", succeeded=True, success=True, trace=None):
    return SimpleNamespace(succeeded=succeeded, evaluation={"success": success}, digest=digest,
                           trace=trace or gold_trace(), failed_calls=[])


def test_generator_and_eligibility_exclude_the_nondeterministic_generators():
    assert generator_of("60d0b5b_1") == "60d0b5b"
    assert eligible(["df61dc5_1", "60d0b5b_2", "3c13f5a_3", "60d0b5b_1"]) == ["60d0b5b_1", "60d0b5b_2"]


def test_gate_passes_identical_runs():
    assert gate_verdict(_run(), _run()) == {"passed": True, "reasons": [], "digest": "d"}


def test_gate_fails_on_different_end_states_or_failed_evaluation():
    assert gate_verdict(_run("a"), _run("b"))["reasons"] == ["end states differ"]
    assert "second run failed evaluation" in gate_verdict(_run(), _run(success=False))["reasons"]
    assert "first run did not execute cleanly" in gate_verdict(_run(succeeded=False), _run())["reasons"]


def test_gate_fails_on_different_traces_with_equal_digests():
    other = gold_trace()
    other.calls[0].response = {"access_token": "other"}
    assert gate_verdict(_run(), _run(trace=other))["reasons"] == ["traces differ"]
