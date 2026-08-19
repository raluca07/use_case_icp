"""Scarring: a caught fault becomes a permanent deterministic check on its boundary.

History as context distorted every judge tested, each differently. A scar keeps the
lesson and discards the transcript: minted from one clean/faulty pair of observations,
attached to the boundary's identity, expiring when the boundary legitimately changes.
"""
from __future__ import annotations

import unittest

from use_case_icp.fault_corpus import BOUNDARIES, build_pipeline
from use_case_icp.fault_injection import FAULT_CATALOGUE, inject
from use_case_icp.fault_scoring import capture_stage_outputs
from use_case_icp.scarring import ScarDetector, boundary_fingerprint, mint_scar


def clean_outputs():
    return capture_stage_outputs(build_pipeline(), BOUNDARIES)


def faulty_outputs(fault, target, parameter=""):
    injected = inject(build_pipeline(), FAULT_CATALOGUE[fault], target=target, parameter=parameter)
    return capture_stage_outputs(injected.pipeline, BOUNDARIES), injected


class MintTests(unittest.TestCase):
    def test_scar_records_boundary_identity_and_provenance(self) -> None:
        outs, injected = faulty_outputs("truncate_sequence", "retrieve_public_sources")
        scar = mint_scar(
            boundary="retrieve_public_sources",
            pipeline=build_pipeline(),
            clean_value=clean_outputs()["retrieve_public_sources"],
            faulty_value=outs["retrieve_public_sources"],
            provenance="case-42",
        )
        self.assertEqual(scar.boundary, "retrieve_public_sources")
        self.assertEqual(scar.provenance, "case-42")
        self.assertEqual(scar.fingerprint, boundary_fingerprint(build_pipeline(), "retrieve_public_sources"))
        self.assertTrue(scar.checks)

    def test_minting_from_identical_values_is_refused(self) -> None:
        value = clean_outputs()["retrieve_public_sources"]
        with self.assertRaises(ValueError):
            mint_scar(boundary="retrieve_public_sources", pipeline=build_pipeline(),
                      clean_value=value, faulty_value=value, provenance="x")


class RecurrenceTests(unittest.TestCase):
    def _scar_for(self, fault, target, parameter=""):
        outs, _ = faulty_outputs(fault, target, parameter)
        return mint_scar(boundary=target, pipeline=build_pipeline(),
                         clean_value=clean_outputs()[target],
                         faulty_value=outs[target], provenance=f"{fault}|{target}")

    def test_recurrence_is_caught_deterministically(self) -> None:
        scar = self._scar_for("truncate_sequence", "retrieve_public_sources")
        det = ScarDetector([scar])
        outs, _ = faulty_outputs("truncate_sequence", "retrieve_public_sources")
        labels = det.label(BOUNDARIES, outs, build_pipeline())
        self.assertEqual(labels["retrieve_public_sources"], "suspect")

    def test_clean_run_raises_no_suspicion(self) -> None:
        scar = self._scar_for("truncate_sequence", "retrieve_public_sources")
        labels = ScarDetector([scar]).label(BOUNDARIES, clean_outputs(), build_pipeline())
        self.assertEqual(set(labels.values()), {"trusted"})

    def test_the_plausible_substitution_is_caught_after_one_exposure(self) -> None:
        # The paper's hard case: a substituted identifier that satisfies every declared
        # pattern and count. A scar records what the clean run actually contained, so
        # the recurrence fails an exact check no hand-written invariant supplied.
        scar = self._scar_for("fabricate_identifier", "retrieve_public_sources", "registries")
        outs, _ = faulty_outputs("fabricate_identifier", "retrieve_public_sources", "registries")
        labels = ScarDetector([scar]).label(BOUNDARIES, outs, build_pipeline())
        self.assertEqual(labels["retrieve_public_sources"], "suspect")

    def test_a_fault_at_another_boundary_is_not_blamed_on_the_scar(self) -> None:
        scar = self._scar_for("truncate_sequence", "retrieve_public_sources")
        outs, _ = faulty_outputs("reverse_ordering", "synthesize_market_demand")
        labels = ScarDetector([scar]).label(BOUNDARIES, outs, build_pipeline())
        self.assertEqual(labels["retrieve_public_sources"], "trusted")


class OrderingTests(unittest.TestCase):
    def test_a_reversed_ordering_is_scarred_and_caught(self) -> None:
        # Every value present, correct count, correct vocabulary; only the sequence
        # differs. Set-shaped checks cannot see this, so the scar records the order.
        target = "synthesize_market_demand"
        outs, _ = faulty_outputs("reverse_ordering", target)
        scar = mint_scar(boundary=target, pipeline=build_pipeline(),
                         clean_value=clean_outputs()[target],
                         faulty_value=outs[target], provenance="ord")
        self.assertTrue(any(c["kind"] == "ordering" for c in scar.checks))
        labels = ScarDetector([scar]).label(BOUNDARIES, outs, build_pipeline())
        self.assertEqual(labels[target], "suspect")

    def test_ordering_scar_does_not_fire_on_the_clean_run(self) -> None:
        target = "synthesize_market_demand"
        outs, _ = faulty_outputs("reverse_ordering", target)
        scar = mint_scar(boundary=target, pipeline=build_pipeline(),
                         clean_value=clean_outputs()[target],
                         faulty_value=outs[target], provenance="ord")
        labels = ScarDetector([scar]).label(BOUNDARIES, clean_outputs(), build_pipeline())
        self.assertEqual(labels[target], "trusted")


class ExpiryTests(unittest.TestCase):
    def test_scar_goes_inert_when_the_boundary_legitimately_changes(self) -> None:
        # A scar carrying yesterday's shape into today's code is exactly the stale
        # history it exists to replace, so it must expire on boundary change.
        outs, _ = faulty_outputs("truncate_sequence", "retrieve_public_sources")
        scar = mint_scar(boundary="retrieve_public_sources", pipeline=build_pipeline(),
                         clean_value=clean_outputs()["retrieve_public_sources"],
                         faulty_value=outs["retrieve_public_sources"], provenance="x")
        # A legitimate edit to the boundary, not a fault: same behaviour, different code.
        changed = inject(build_pipeline(), FAULT_CATALOGUE["fabricate_identifier"],
                         target="retrieve_public_sources", parameter="registries").pipeline
        outs2 = capture_stage_outputs(changed, BOUNDARIES)
        labels = ScarDetector([scar]).label(BOUNDARIES, outs2, changed)
        self.assertEqual(labels["retrieve_public_sources"], "trusted")
        self.assertFalse(scar.live(changed))


if __name__ == "__main__":
    unittest.main()
