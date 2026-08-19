"""Scoring trust signals against injected ground truth."""

from __future__ import annotations

import unittest

from use_case_icp.fault_injection import FAULT_CATALOGUE, inject
from use_case_icp.fault_scoring import (
    Contract,
    ContractDetector,
    SchemaDetector,
    capture_stage_outputs,
    score,
)
from use_case_icp.records import GeneratedFile, GeneratedPipeline

SOURCE = (
    "import json\n"
    "def collect():\n"
    "    return {'needs': ['alpha', 'beta', 'gamma'], 'sources': ['s1', 's2']}\n"
    "def rank(payload):\n"
    "    return sorted(payload['needs'])\n"
    "result = rank(collect())\n"
    "print(json.dumps(result))\n"
)

BOUNDARIES = ["collect", "rank"]

SCHEMAS = {
    "collect": {
        "type": "object",
        "required": ["needs", "sources"],
        "properties": {"needs": {"type": "array"}, "sources": {"type": "array"}},
    },
    "rank": {"type": "array"},
}

CONTRACTS = {
    "collect": Contract(
        function="collect",
        required_fields=["needs", "sources"],
        min_items={"needs": 3, "sources": 2},
        field_pattern={"needs": r"^[a-z]+$"},
    ),
    "rank": Contract(function="rank", ordered=True),
}


def build_pipeline(source: str = SOURCE) -> GeneratedPipeline:
    return GeneratedPipeline(
        "pipeline.py",
        [GeneratedFile("pipeline.py", source)],
        [{"function_name": name} for name in BOUNDARIES],
    )


class CaptureTests(unittest.TestCase):
    def test_captures_each_boundary_return_value(self) -> None:
        outputs = capture_stage_outputs(build_pipeline(), BOUNDARIES)
        self.assertEqual(outputs["collect"]["sources"], ["s1", "s2"])
        self.assertEqual(outputs["rank"], ["alpha", "beta", "gamma"])

    def test_capture_runs_the_injected_pipeline(self) -> None:
        injected = inject(
            build_pipeline(), FAULT_CATALOGUE["drop_field"], target="collect", parameter="sources"
        )
        outputs = capture_stage_outputs(injected.pipeline, BOUNDARIES)
        self.assertNotIn("sources", outputs["collect"])


class DetectorTests(unittest.TestCase):
    def label(self, detector, source_pipeline):
        outputs = capture_stage_outputs(source_pipeline, BOUNDARIES)
        return detector.label(BOUNDARIES, outputs)

    def test_clean_pipeline_is_trusted_by_both_detectors(self) -> None:
        pipeline = build_pipeline()
        for detector in (SchemaDetector(SCHEMAS), ContractDetector(CONTRACTS)):
            labels = self.label(detector, pipeline)
            self.assertEqual(set(labels.values()), {"trusted"}, type(detector).__name__)

    def test_schema_catches_a_missing_required_field(self) -> None:
        injected = inject(
            build_pipeline(), FAULT_CATALOGUE["drop_field"], target="collect", parameter="sources"
        )
        labels = self.label(SchemaDetector(SCHEMAS), injected.pipeline)
        self.assertEqual(labels["collect"], "suspect")

    def test_schema_misses_a_truncated_sequence(self) -> None:
        # Still an array of strings, so the schema has nothing to object to.
        injected = inject(
            build_pipeline(), FAULT_CATALOGUE["truncate_sequence"], target="collect"
        )
        labels = self.label(SchemaDetector(SCHEMAS), injected.pipeline)
        self.assertEqual(labels["collect"], "trusted")

    def test_contract_catches_the_truncated_sequence_the_schema_missed(self) -> None:
        injected = inject(
            build_pipeline(), FAULT_CATALOGUE["truncate_sequence"], target="collect"
        )
        labels = self.label(ContractDetector(CONTRACTS), injected.pipeline)
        self.assertEqual(labels["collect"], "suspect")

    def test_contract_catches_a_fabricated_identifier(self) -> None:
        injected = inject(
            build_pipeline(),
            FAULT_CATALOGUE["fabricate_identifier"],
            target="collect",
            parameter="PLACEHOLDER-001",
        )
        labels = self.label(ContractDetector(CONTRACTS), injected.pipeline)
        self.assertEqual(labels["collect"], "suspect")

    def test_schema_misses_the_fabricated_identifier(self) -> None:
        injected = inject(
            build_pipeline(),
            FAULT_CATALOGUE["fabricate_identifier"],
            target="collect",
            parameter="PLACEHOLDER-001",
        )
        labels = self.label(SchemaDetector(SCHEMAS), injected.pipeline)
        self.assertEqual(labels["collect"], "trusted")


class EvasionTests(unittest.TestCase):
    def test_a_plausible_substitution_evades_every_deterministic_arm(self) -> None:
        # Same fault class as the fabricated identifier, but the injected value looks
        # like the real thing. It is present, correctly typed, correctly counted, it
        # matches the declared pattern, and the ranking is still ordered. Detection
        # here depends on how plausible the value is, not on the fault class, and no
        # invariant that does not consult the source can separate the two.
        injected = inject(
            build_pipeline(),
            FAULT_CATALOGUE["fabricate_identifier"],
            target="collect",
            parameter="zeta",
        )
        outputs = capture_stage_outputs(injected.pipeline, BOUNDARIES)
        for detector in (SchemaDetector(SCHEMAS), ContractDetector(CONTRACTS)):
            labels = detector.label(BOUNDARIES, outputs)
            result = score(injected.ground_truth, BOUNDARIES, labels)
            self.assertTrue(
                result.false_trust,
                f"{type(detector).__name__} unexpectedly caught it",
            )
            self.assertTrue(result.shipped_contaminated_output)


class ScoreTests(unittest.TestCase):
    def test_labelling_the_injected_boundary_trusted_is_a_false_trust(self) -> None:
        injected = inject(
            build_pipeline(), FAULT_CATALOGUE["truncate_sequence"], target="collect"
        )
        result = score(
            injected.ground_truth,
            BOUNDARIES,
            {"collect": "trusted", "rank": "trusted"},
        )
        self.assertTrue(result.false_trust)
        self.assertIsNone(result.resume_function)

    def test_flagging_a_clean_boundary_is_a_false_suspect(self) -> None:
        injected = inject(
            build_pipeline(), FAULT_CATALOGUE["reverse_ordering"], target="rank"
        )
        result = score(
            injected.ground_truth,
            BOUNDARIES,
            {"collect": "suspect", "rank": "suspect"},
        )
        self.assertEqual(result.false_suspects, ["collect"])

    def test_resuming_downstream_of_the_fault_is_a_positive_localisation_error(self) -> None:
        # collect is poisoned but only rank is flagged, so the resume point sits past
        # the fault and the contaminated output is kept.
        injected = inject(
            build_pipeline(), FAULT_CATALOGUE["truncate_sequence"], target="collect"
        )
        result = score(
            injected.ground_truth,
            BOUNDARIES,
            {"collect": "trusted", "rank": "suspect"},
        )
        self.assertEqual(result.localisation_error, 1)
        self.assertTrue(result.shipped_contaminated_output)

    def test_resuming_upstream_of_the_fault_wastes_work_but_ships_nothing(self) -> None:
        injected = inject(
            build_pipeline(), FAULT_CATALOGUE["reverse_ordering"], target="rank"
        )
        result = score(
            injected.ground_truth,
            BOUNDARIES,
            {"collect": "suspect", "rank": "suspect"},
        )
        self.assertEqual(result.localisation_error, -1)
        self.assertFalse(result.shipped_contaminated_output)

    def test_an_exact_hit_scores_zero(self) -> None:
        injected = inject(
            build_pipeline(), FAULT_CATALOGUE["truncate_sequence"], target="collect"
        )
        result = score(
            injected.ground_truth,
            BOUNDARIES,
            {"collect": "suspect", "rank": "trusted"},
        )
        self.assertEqual(result.localisation_error, 0)
        self.assertFalse(result.false_trust)
        self.assertEqual(result.false_suspects, [])


if __name__ == "__main__":
    unittest.main()
