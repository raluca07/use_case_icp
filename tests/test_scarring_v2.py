"""Population-mined scars, trust propagation, and repair gating."""
from __future__ import annotations

import copy
import unittest

from use_case_icp import cassette_corpus as cc
from use_case_icp.scarring import (
    ScarDetector, features, healthy_variants, mint_from_population, propagate_trust,
)


def cap(cassette): return cc.capture(cassette)


def mutate(source_id, mutation, base=None):
    """Fault applied to a healthy cassette. The base must come from the same generative
    process as the healthy population, or minting sees process differences as faults."""
    c = copy.deepcopy(base if base is not None else cc.BASE_CASSETTE)
    cc.MUTATIONS[mutation][1](c[source_id])
    return c


class FeatureTests(unittest.TestCase):
    def test_features_reach_inside_lists_of_records(self) -> None:
        # The depth my first implementation lacked: a key dropped from every item of a
        # list is plainly visible, but only if the extractor descends into the list.
        value = {"needs": [{"need_id": "a", "support": "x"}, {"need_id": "b", "support": "y"}]}
        f = features(value)
        self.assertIn(("presence", "needs[].need_id"), f)
        self.assertEqual(f[("count", "needs")], 2)
        self.assertEqual(f[("vocab", "needs[].need_id")], frozenset({"a", "b"}))

    def test_dropping_a_nested_key_changes_the_features(self) -> None:
        whole = {"needs": [{"need_id": "a", "support": "x"}]}
        stripped = {"needs": [{"support": "x"}]}
        self.assertIn(("presence", "needs[].need_id"), features(whole))
        self.assertNotIn(("presence", "needs[].need_id"), features(stripped))


class PopulationTests(unittest.TestCase):
    def test_a_legitimately_varying_property_is_not_scarred(self) -> None:
        # Quote text differs between healthy runs. Single-pair minting would scar it;
        # population minting must not, or the scar fires on every honest run.
        pop = healthy_variants(5)
        healthy = [cap(c)["extract_evidence_records"] for c in pop]
        faulty = cap(mutate("registry_alpha", "truncated_response", pop[0]))["extract_evidence_records"]
        scar = mint_from_population(boundary="extract_evidence_records",
                                    pipeline=cc.build_pipeline(), healthy_values=healthy,
                                    faulty_value=faulty, provenance="p")
        scarred = {(c["kind"], c["path"]) for c in scar.checks}
        self.assertNotIn(("known_vocabulary", "records[].quote"), scarred)

    def test_an_invariant_property_is_scarred_with_its_support(self) -> None:
        pop = healthy_variants(5)
        healthy = [cap(c)["retrieve_registries"] for c in pop]
        faulty = cap(mutate("registry_alpha", "null_identifier", pop[0]))["retrieve_registries"]
        scar = mint_from_population(boundary="retrieve_registries",
                                    pipeline=cc.build_pipeline(), healthy_values=healthy,
                                    faulty_value=faulty, provenance="p")
        self.assertTrue(scar.checks)
        self.assertEqual(scar.support, 5)

    def test_no_healthy_run_raises_suspicion_from_its_own_scar(self) -> None:
        healthy_c = healthy_variants(6)
        healthy = [cap(c)["retrieve_registries"] for c in healthy_c]
        faulty = cap(mutate("registry_alpha", "truncated_response", healthy_c[0]))["retrieve_registries"]
        scar = mint_from_population(boundary="retrieve_registries",
                                    pipeline=cc.build_pipeline(), healthy_values=healthy,
                                    faulty_value=faulty, provenance="p")
        det = ScarDetector([scar])
        for c in healthy_c:
            labels = det.label(cc.BOUNDARIES, cap(c), cc.build_pipeline())
            self.assertEqual(labels["retrieve_registries"], "trusted")

    def test_the_scar_still_catches_the_recurrence(self) -> None:
        pop = healthy_variants(5)
        healthy = [cap(c)["retrieve_registries"] for c in pop]
        faulty_c = mutate("registry_beta", "truncated_response", pop[0])
        scar = mint_from_population(boundary="retrieve_registries",
                                    pipeline=cc.build_pipeline(), healthy_values=healthy,
                                    faulty_value=cap(faulty_c)["retrieve_registries"],
                                    provenance="p")
        labels = ScarDetector([scar]).label(cc.BOUNDARIES, cap(faulty_c), cc.build_pipeline())
        self.assertEqual(labels["retrieve_registries"], "suspect")


class SaturationTests(unittest.TestCase):
    """A vocabulary check is only safe over a closed domain.

    Identifiers come from a fixed registry, so the set stops growing and an unseen value
    is a real signal. Dates and free text do not, so a vocabulary check over them is
    guaranteed to fire on an honest run eventually. The population itself says which is
    which: if late observations still add new values, the domain is open.
    """

    def test_a_fault_only_visible_in_an_open_domain_is_refused(self) -> None:
        # A stale publication date differs from every date seen, but so does an honest
        # new one. Refusing is correct: the alternative fires on real runs, which the
        # held-out measurement confirms.
        pop = healthy_variants(8)
        healthy = [cap(c)["retrieve_registries"] for c in pop]
        faulty = cap(mutate("registry_alpha", "stale_copy", pop[0]))["retrieve_registries"]
        with self.assertRaises(ValueError):
            mint_from_population(boundary="retrieve_registries", pipeline=cc.build_pipeline(),
                                 healthy_values=healthy, faulty_value=faulty, provenance="p")

    def test_a_closed_domain_fault_is_still_scarred(self) -> None:
        pop = healthy_variants(8)
        healthy = [cap(c)["retrieve_registries"] for c in pop]
        faulty = cap(mutate("registry_alpha", "null_identifier", pop[0]))["retrieve_registries"]
        scar = mint_from_population(boundary="retrieve_registries", pipeline=cc.build_pipeline(),
                                    healthy_values=healthy, faulty_value=faulty, provenance="p")
        self.assertTrue(scar.checks)


class PropagationTests(unittest.TestCase):
    def test_contamination_flows_downstream_of_an_untrusted_boundary(self) -> None:
        labels = {b: "trusted" for b in cc.BOUNDARIES}
        labels["retrieve_registries"] = "suspect"
        out = propagate_trust(cc.build_pipeline(), cc.BOUNDARIES, labels)
        self.assertEqual(out["retrieve_registries"], "suspect")
        for downstream in ("merge_sources", "extract_evidence_records", "synthesize_market_demand"):
            self.assertEqual(out[downstream], "contaminated")

    def test_a_sibling_branch_is_left_trusted(self) -> None:
        labels = {b: "trusted" for b in cc.BOUNDARIES}
        labels["retrieve_registries"] = "suspect"
        out = propagate_trust(cc.build_pipeline(), cc.BOUNDARIES, labels)
        self.assertEqual(out["retrieve_trackers"], "trusted")
        self.assertEqual(out["retrieve_vendor_docs"], "trusted")

    def test_a_clean_run_propagates_to_all_trusted(self) -> None:
        labels = {b: "trusted" for b in cc.BOUNDARIES}
        out = propagate_trust(cc.build_pipeline(), cc.BOUNDARIES, labels)
        self.assertEqual(set(out.values()), {"trusted"})

    def test_downstream_blame_is_arithmetically_contradicted(self) -> None:
        # A judge naming a downstream stage while its inputs are untrusted is not
        # merely unlikely, it is inconsistent with the propagated state.
        labels = {b: "trusted" for b in cc.BOUNDARIES}
        labels["retrieve_registries"] = "suspect"
        out = propagate_trust(cc.build_pipeline(), cc.BOUNDARIES, labels)
        self.assertNotEqual(out["synthesize_market_demand"], "suspect")


class AttributionTests(unittest.TestCase):
    """Forward propagation cannot reach a cause that has no check of its own.

    Truncating a source flags the aggregating stages downstream while the retrieval stage
    that consumed the bad response passes every declared check. The suspect set therefore
    sits entirely downstream of the fault, which is the same failure the model judges
    showed, in the deterministic signals.
    """

    def _flagged(self):
        from use_case_icp.fault_scoring import ContractDetector
        pop = healthy_variants(2)
        outs = cap(mutate("registry_alpha", "truncated_response", pop[0]))
        return outs, ContractDetector(cc.CONTRACTS).label(cc.BOUNDARIES, outs)

    def test_the_true_cause_carries_no_flag_of_its_own(self) -> None:
        _, labels = self._flagged()
        self.assertEqual(labels["retrieve_registries"], "trusted")
        self.assertEqual(labels["extract_evidence_records"], "suspect")

    def test_attribution_narrows_to_a_candidate_set_containing_the_cause(self) -> None:
        from use_case_icp.scarring import attribute_upstream
        _, labels = self._flagged()
        out = attribute_upstream(cc.build_pipeline(), cc.BOUNDARIES, labels)
        candidates = {b for b, v in out.items() if v == "implicated"}
        self.assertIn("retrieve_registries", candidates)
        self.assertLess(len(candidates), len(cc.BOUNDARIES))

    def test_attribution_never_implicates_a_stage_downstream_of_the_suspect(self) -> None:
        from use_case_icp.scarring import attribute_upstream
        _, labels = self._flagged()
        out = attribute_upstream(cc.build_pipeline(), cc.BOUNDARIES, labels)
        self.assertNotEqual(out["synthesize_market_demand"], "implicated")

    def test_attribution_does_not_implicate_a_clean_run(self) -> None:
        from use_case_icp.scarring import attribute_upstream
        labels = {b: "trusted" for b in cc.BOUNDARIES}
        out = attribute_upstream(cc.build_pipeline(), cc.BOUNDARIES, labels)
        self.assertEqual(set(out.values()), {"trusted"})

    def test_a_flagged_boundary_keeps_its_own_verdict(self) -> None:
        from use_case_icp.scarring import attribute_upstream
        labels = {b: "trusted" for b in cc.BOUNDARIES}
        labels["retrieve_registries"] = "suspect"
        out = attribute_upstream(cc.build_pipeline(), cc.BOUNDARIES, labels)
        self.assertEqual(out["retrieve_registries"], "suspect")


class GateTests(unittest.TestCase):
    def _scar(self):
        self.pop = healthy_variants(5)
        healthy = [cap(c)["retrieve_registries"] for c in self.pop]
        faulty = cap(mutate("registry_alpha", "truncated_response", self.pop[0]))["retrieve_registries"]
        return mint_from_population(boundary="retrieve_registries", pipeline=cc.build_pipeline(),
                                    healthy_values=healthy, faulty_value=faulty, provenance="p")

    def test_a_repair_that_does_not_fix_the_flagged_property_is_refused(self) -> None:
        scar = self._scar()
        still_broken = cap(mutate("registry_gamma", "truncated_response", self.pop[0]))["retrieve_registries"]
        ok, reasons = scar.clears(still_broken)
        self.assertFalse(ok)
        self.assertTrue(reasons)

    def test_a_genuine_repair_clears_the_gate(self) -> None:
        scar = self._scar()
        ok, reasons = scar.clears(cap(self.pop[0])["retrieve_registries"])
        self.assertTrue(ok, reasons)


if __name__ == "__main__":
    unittest.main()
