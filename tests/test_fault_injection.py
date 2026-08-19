"""Fault injection with ground truth known by construction.

Trust labels in this system come from one LLM reviewing another, so nothing in the
loop knows the right answer. These faults are injected into a known boundary, which
makes it possible to score a trust signal instead of trusting it.
"""

from __future__ import annotations

import unittest

from use_case_icp.fault_injection import (
    FAULT_CATALOGUE,
    inject,
    downstream_functions,
)
from use_case_icp.records import GeneratedFile, GeneratedPipeline

SOURCE = (
    "import json\n"
    "def collect():\n"
    "    return {'needs': ['a', 'b'], 'sources': ['s1', 's2']}\n"
    "def rank(payload):\n"
    "    kept = [need for need in payload['needs'] if len(need) > 0]\n"
    "    return sorted(kept)\n"
    "result = rank(collect())\n"
    "print(json.dumps(result))\n"
)


def build_pipeline() -> GeneratedPipeline:
    return GeneratedPipeline(
        "pipeline.py",
        [GeneratedFile("pipeline.py", SOURCE)],
        [{"function_name": "collect"}, {"function_name": "rank"}],
    )


class DownstreamTests(unittest.TestCase):
    def test_downstream_follows_module_level_dataflow(self) -> None:
        self.assertEqual(downstream_functions(build_pipeline(), "collect"), ["rank"])

    def test_a_terminal_stage_has_no_downstream(self) -> None:
        self.assertEqual(downstream_functions(build_pipeline(), "rank"), [])


class InjectionTests(unittest.TestCase):
    def test_injection_changes_only_the_target_function(self) -> None:
        fault = FAULT_CATALOGUE["drop_field"]
        injected = inject(build_pipeline(), fault, target="collect", parameter="sources")
        content = injected.pipeline.files[0].content
        self.assertNotIn("'sources'", content)
        self.assertNotIn('"sources"', content)
        for untouched in ("import json\n", "result = rank(collect())\n"):
            self.assertIn(untouched, content)

    def test_ground_truth_names_the_boundary_and_what_it_contaminates(self) -> None:
        fault = FAULT_CATALOGUE["drop_field"]
        injected = inject(build_pipeline(), fault, target="collect", parameter="sources")
        self.assertEqual(injected.ground_truth.injected_function, "collect")
        self.assertEqual(injected.ground_truth.contaminated_functions, ["rank"])
        self.assertEqual(injected.ground_truth.fault_class, "drop_field")

    def test_injection_into_an_unknown_boundary_is_refused(self) -> None:
        fault = FAULT_CATALOGUE["drop_field"]
        with self.assertRaises(ValueError):
            inject(build_pipeline(), fault, target="no_such_stage", parameter="sources")

    def test_a_fault_that_changes_nothing_is_refused(self) -> None:
        # A no-op mutation would enter the corpus as a fault nothing can detect,
        # and would score every arm as a false negative.
        fault = FAULT_CATALOGUE["drop_field"]
        with self.assertRaises(ValueError):
            inject(build_pipeline(), fault, target="collect", parameter="absent_field")


class CatalogueTests(unittest.TestCase):
    def test_every_catalogued_fault_actually_fires(self) -> None:
        # A fault that silently stops mutating would enter the corpus as an
        # undetectable case and depress every arm's score equally.
        parameters = {
            "drop_field": "sources",
            "fabricate_identifier": "PLACEHOLDER-001",
        }
        for name, fault in FAULT_CATALOGUE.items():
            target = "rank" if name in {"invert_comparison", "reverse_ordering"} else "collect"
            with self.subTest(fault=name):
                injected = inject(
                    build_pipeline(),
                    fault,
                    target=target,
                    parameter=parameters.get(name, ""),
                )
                self.assertNotEqual(
                    injected.pipeline.files[0].content,
                    SOURCE,
                    f"{name} produced an identical pipeline",
                )

    def test_every_fault_declares_its_provenance(self) -> None:
        # Faults observed in the ledgers carry more weight than invented ones, so the
        # corpus records which is which.
        for name, fault in FAULT_CATALOGUE.items():
            self.assertIn(fault.provenance, {"observed", "synthetic"}, name)
            self.assertTrue(fault.description, name)


if __name__ == "__main__":
    unittest.main()
