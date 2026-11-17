import pytest

from rdr.v2_pipeline import validate_execution_pair


def test_synthetic_or_same_world_variants_are_rejected():
    result = {"process": {"fresh_root": False}}
    with pytest.raises(ValueError, match="fresh-world"):
        validate_execution_pair(result, result, result)
