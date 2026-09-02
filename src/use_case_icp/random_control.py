from __future__ import annotations

import hashlib
import json
import math
import random
import re
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .fault_experiment import PROTOCOL_CONTENT_HASH, _digest, _encode
from .records import EtiqEvidenceSnapshot
from .review import review_node_payload, review_relationship_payload


RANDOM_PROJECTION_MASTER_SEED = 8_675_309
RANDOM_SERIALIZER = "canonical-review-evidence-json"
RANDOM_SERIALIZER_VERSION = "1.0.0"
RANDOM_ABSOLUTE_TOLERANCE_BYTES = 2_048
RANDOM_RELATIVE_TOLERANCE = 0.05


def _projection_id(
    *, instance_id: str, job_id: str, boundary_id: str,
    protocol_content_hash: str = PROTOCOL_CONTENT_HASH,
) -> str:
    identity = f"{protocol_content_hash}:{instance_id}:{job_id}:{boundary_id}"
    return f"prj-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"


def random_budget_tolerance(structural_residual_bytes: int) -> int:
    return max(
        RANDOM_ABSOLUTE_TOLERANCE_BYTES,
        math.ceil(RANDOM_RELATIVE_TOLERANCE * structural_residual_bytes),
    )


def derive_random_projection_seed(
    *, instance_id: str, job_id: str, boundary_id: str,
    protocol_content_hash: str = PROTOCOL_CONTENT_HASH,
) -> int:
    material = (
        f"{RANDOM_PROJECTION_MASTER_SEED}:{protocol_content_hash}:"
        f"{instance_id}:{job_id}:{boundary_id}"
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big", signed=False)


def _serialized_evidence_bytes(
    snapshot: EtiqEvidenceSnapshot,
    node_refs: Iterable[str],
    relationship_refs: Iterable[str],
) -> bytes:
    node_by_ref = {node.node_ref: node for node in snapshot.nodes}
    relationship_by_ref = {
        relationship.relationship_ref: relationship
        for relationship in snapshot.relationships
    }
    return _encode(
        {
            "nodes": [
                review_node_payload(node_by_ref[ref]) for ref in sorted(set(node_refs))
            ],
            "relationships": [
                review_relationship_payload(relationship_by_ref[ref])
                for ref in sorted(set(relationship_refs))
            ],
        }
    )


def _mandatory_interface(
    snapshot: EtiqEvidenceSnapshot,
    boundary: Mapping[str, Any],
) -> tuple[set[str], set[str]]:
    relationship_by_ref = {
        relationship.relationship_ref: relationship
        for relationship in snapshot.relationships
    }
    relationship_refs = {
        str(ref)
        for ref in (
            list(boundary["input_relationship_refs"])
            + list(boundary["output_relationship_refs"])
        )
    }
    node_refs = {str(boundary["matched_function_node_ref"])}
    for ref in relationship_refs:
        relationship = relationship_by_ref.get(ref)
        if relationship is None:
            raise ValueError(f"mandatory relationship is absent from capture: {ref}")
        node_refs.update((relationship.source_ref, relationship.target_ref))
    return node_refs, relationship_refs


def build_random_projection(
    snapshot: EtiqEvidenceSnapshot,
    boundary: Mapping[str, Any],
    structural_selection: Mapping[str, Any],
    *,
    instance_id: str,
    handoffs: Iterable[Mapping[str, Any]] = (),
    protocol_content_hash: str = PROTOCOL_CONTENT_HASH,
) -> dict[str, Any]:
    """Freeze an oracle-blind equal-byte random graph projection for one boundary.

    This is a selection-policy control.  It deliberately retains Etiq graph
    evidence; current-run and history conditions test graph evidence more broadly.
    """
    boundary_id = str(boundary["boundary_id"])
    job_id = snapshot.job_id
    node_by_ref = {node.node_ref: node for node in snapshot.nodes}
    relationship_by_ref = {
        relationship.relationship_ref: relationship
        for relationship in snapshot.relationships
    }
    if len(node_by_ref) != len(snapshot.nodes) or len(relationship_by_ref) != len(
        snapshot.relationships
    ):
        raise ValueError("random projection requires unique captured evidence references")

    boundary_nodes = {str(ref) for ref in boundary["node_refs"]}
    boundary_relationships = {str(ref) for ref in boundary["relationship_refs"]}
    mandatory_nodes, mandatory_relationships = _mandatory_interface(snapshot, boundary)
    structural_visible = structural_selection.get("visible_evidence_by_boundary", {}).get(
        boundary_id
    )
    if structural_visible is None:
        raise ValueError(f"structural selection is missing boundary {boundary_id}")
    structural_nodes = {str(ref) for ref in structural_visible.get("node_refs", [])}
    structural_relationships = {
        str(ref) for ref in structural_visible.get("relationship_refs", [])
    }
    if not mandatory_nodes.issubset(structural_nodes) or not mandatory_relationships.issubset(
        structural_relationships
    ):
        raise ValueError("structural selection omits the mandatory boundary interface")

    structural_residual_nodes = structural_nodes - mandatory_nodes
    structural_residual_relationships = structural_relationships - mandatory_relationships
    structural_residual_bytes = len(
        _serialized_evidence_bytes(
            snapshot, structural_residual_nodes, structural_residual_relationships
        )
    )

    candidate_relationships = sorted(boundary_relationships - mandatory_relationships)
    candidate_nodes = sorted(boundary_nodes - mandatory_nodes)
    for ref in candidate_relationships:
        relationship = relationship_by_ref.get(ref)
        if relationship is None:
            raise ValueError(f"boundary relationship is absent from capture: {ref}")
        if relationship.source_ref not in boundary_nodes or relationship.target_ref not in boundary_nodes:
            raise ValueError(f"residual relationship escapes realized boundary: {ref}")

    structural_residual_endpoints = {
        endpoint
        for ref in structural_residual_relationships
        for endpoint in (
            relationship_by_ref[ref].source_ref,
            relationship_by_ref[ref].target_ref,
        )
    }
    allow_standalone_nodes = bool(
        structural_residual_nodes - structural_residual_endpoints
    )
    universe = [
        {
            "kind": "relationship_bundle",
            "relationship_ref": ref,
            "endpoint_node_refs": sorted(
                {
                    relationship_by_ref[ref].source_ref,
                    relationship_by_ref[ref].target_ref,
                }
                - mandatory_nodes
            ),
        }
        for ref in candidate_relationships
    ]
    candidate_relationship_endpoints = {
        endpoint
        for ref in candidate_relationships
        for endpoint in (
            relationship_by_ref[ref].source_ref,
            relationship_by_ref[ref].target_ref,
        )
    }
    if allow_standalone_nodes:
        universe.extend(
            {"kind": "standalone_node", "node_ref": ref}
            for ref in candidate_nodes
            if ref not in candidate_relationship_endpoints
        )

    derived_seed = derive_random_projection_seed(
        instance_id=instance_id, job_id=job_id, boundary_id=boundary_id,
        protocol_content_hash=protocol_content_hash,
    )
    sampled = list(universe)
    random.Random(derived_seed).shuffle(sampled)
    chosen_nodes: set[str] = set()
    chosen_relationships: set[str] = set()
    candidates: list[tuple[int, int, set[str], set[str], list[dict[str, Any]]]] = []

    def remember(chosen_bundles: list[dict[str, Any]]) -> None:
        serialized_size = len(
            _serialized_evidence_bytes(snapshot, chosen_nodes, chosen_relationships)
        )
        candidates.append(
            (
                abs(serialized_size - structural_residual_bytes),
                serialized_size,
                set(chosen_nodes),
                set(chosen_relationships),
                list(chosen_bundles),
            )
        )

    chosen_bundles: list[dict[str, Any]] = []
    remember(chosen_bundles)
    for bundle in sampled:
        if bundle["kind"] == "relationship_bundle":
            ref = str(bundle["relationship_ref"])
            relationship = relationship_by_ref[ref]
            chosen_relationships.add(ref)
            chosen_nodes.update(
                {relationship.source_ref, relationship.target_ref} - mandatory_nodes
            )
        else:
            chosen_nodes.add(str(bundle["node_ref"]))
        chosen_bundles.append(bundle)
        remember(chosen_bundles)

    difference, random_residual_bytes, residual_nodes, residual_relationships, selected = min(
        candidates, key=lambda item: (item[0], item[1], _encode(item[4]))
    )
    tolerance = random_budget_tolerance(structural_residual_bytes)
    if difference > tolerance:
        # A prefix is the primary seeded sample.  When endpoint bundles have
        # very uneven serialized sizes, deterministically test every one-bundle
        # exchange around every prefix before declaring the matched budget
        # infeasible.  This remains oracle-blind and bounded by O(n^2).
        exchanged = []
        for prefix_length in range(len(sampled) + 1):
            prefix_indexes = set(range(prefix_length))
            for toggle_index in range(len(sampled)):
                indexes = prefix_indexes ^ {toggle_index}
                exchange_nodes: set[str] = set()
                exchange_relationships: set[str] = set()
                exchange_bundles = [sampled[index] for index in sorted(indexes)]
                for bundle in exchange_bundles:
                    if bundle["kind"] == "relationship_bundle":
                        ref = str(bundle["relationship_ref"])
                        relationship = relationship_by_ref[ref]
                        exchange_relationships.add(ref)
                        exchange_nodes.update(
                            {relationship.source_ref, relationship.target_ref}
                            - mandatory_nodes
                        )
                    else:
                        exchange_nodes.add(str(bundle["node_ref"]))
                serialized_size = len(
                    _serialized_evidence_bytes(
                        snapshot, exchange_nodes, exchange_relationships
                    )
                )
                exchanged.append(
                    (
                        abs(serialized_size - structural_residual_bytes),
                        serialized_size,
                        exchange_nodes,
                        exchange_relationships,
                        exchange_bundles,
                    )
                )
        difference, random_residual_bytes, residual_nodes, residual_relationships, selected = min(
            exchanged, key=lambda item: (item[0], item[1], _encode(item[4]))
        )
    if difference > tolerance:
        raise ValueError(
            "no endpoint-complete random projection matches the structural residual "
            f"budget: difference={difference}, tolerance={tolerance}"
        )

    final_nodes = mandatory_nodes | residual_nodes
    final_relationships = mandatory_relationships | residual_relationships
    for ref in final_relationships:
        relationship = relationship_by_ref[ref]
        if relationship.source_ref not in final_nodes or relationship.target_ref not in final_nodes:
            raise AssertionError(f"random projection created a dangling relationship: {ref}")

    clean_handoffs = []
    for handoff in handoffs:
        if snapshot.job_id not in {
            str(handoff.get("upstream_job_id")),
            str(handoff.get("downstream_job_id")),
        }:
            continue
        handoff_ref = str(handoff.get("handoff_ref") or "")
        artifact_sha256 = str(handoff.get("artifact_sha256") or "")
        if not handoff_ref or not re.fullmatch(r"sha256:[0-9a-f]{64}", artifact_sha256):
            raise ValueError("mandatory handoff anchors require an exact artifact hash")
        clean_handoffs.append(
            {
                "handoff_ref": handoff_ref,
                "artifact_sha256": artifact_sha256,
            }
        )
    clean_handoffs.sort(key=lambda value: value["handoff_ref"])
    mandatory_graph_sha256 = _digest(
        _serialized_evidence_bytes(snapshot, mandatory_nodes, mandatory_relationships)
    )

    manifest: dict[str, Any] = {
        "schema_version": "1",
        "projection_id": _projection_id(
            instance_id=instance_id, job_id=job_id, boundary_id=boundary_id,
            protocol_content_hash=protocol_content_hash,
        ),
        "projection_identity_scope": "realized_boundary",
        "protocol_content_hash": protocol_content_hash,
        "instance_id": instance_id,
        "job_id": job_id,
        "boundary_id": boundary_id,
        "realized_boundary_sha256": _digest(_encode(boundary)),
        "mandatory_interface_sha256": _digest(
            _encode(
                {
                    "graph_sha256": mandatory_graph_sha256,
                    "handoffs": clean_handoffs,
                }
            )
        ),
        "mandatory_handoffs": clean_handoffs,
        "serializer": RANDOM_SERIALIZER,
        "serializer_version": RANDOM_SERIALIZER_VERSION,
        "structural_residual_utf8_bytes": structural_residual_bytes,
        "derived_seed": derived_seed,
        "ordered_candidate_universe_sha256": _digest(_encode(universe)),
        "candidate_universe": universe,
        "selected_bundles": selected,
        "node_refs": sorted(final_nodes),
        "relationship_refs": sorted(final_relationships),
        "residual_node_refs": sorted(residual_nodes),
        "residual_relationship_refs": sorted(residual_relationships),
        "random_residual_utf8_bytes": random_residual_bytes,
        "absolute_byte_difference": difference,
        "relative_byte_difference": (
            difference / structural_residual_bytes if structural_residual_bytes else 0.0
        ),
        "budget_tolerance_utf8_bytes": tolerance,
        "uses_fault_or_oracle_truth": False,
        "helper_expansion_allowed": False,
    }
    manifest["projection_sha256"] = _digest(_encode(manifest))
    return manifest


def verify_random_projection_manifest(
    snapshot: EtiqEvidenceSnapshot,
    boundary: Mapping[str, Any],
    structural_selection: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    instance_id: str,
    handoffs: Iterable[Mapping[str, Any]] = (),
    protocol_content_hash: str = PROTOCOL_CONTENT_HASH,
) -> dict[str, Any]:
    """Verify every frozen field before a random projection reaches packaging."""
    supplied = dict(manifest)
    supplied_hash = str(supplied.get("projection_sha256") or "")
    unhashed = {key: value for key, value in supplied.items() if key != "projection_sha256"}
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", supplied_hash) or _digest(
        _encode(unhashed)
    ) != supplied_hash:
        raise ValueError("random projection hash verification failed")
    expected = build_random_projection(
        snapshot,
        boundary,
        structural_selection,
        instance_id=instance_id,
        handoffs=handoffs,
        protocol_content_hash=protocol_content_hash,
    )
    if supplied != expected:
        differing = sorted(
            key
            for key in set(supplied) | set(expected)
            if supplied.get(key) != expected.get(key)
        )
        raise ValueError(
            "random projection does not match its frozen protocol identity: "
            f"{differing}"
        )
    return supplied


def freeze_random_projections(
    output_dir: Path | str,
    snapshot: EtiqEvidenceSnapshot,
    realized_boundaries: Iterable[Mapping[str, Any]],
    structural_selection: Mapping[str, Any],
    *,
    instance_id: str,
    handoffs: Iterable[Mapping[str, Any]] = (),
    protocol_content_hash: str = PROTOCOL_CONTENT_HASH,
) -> dict[str, dict[str, Any]]:
    """Persist one immutable boundary projection before any reviewer-model call."""
    root = Path(output_dir).absolute()
    if root.exists() and root.is_symlink():
        raise ValueError("random projection directory cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    handoff_values = [dict(value) for value in handoffs]
    frozen: dict[str, dict[str, Any]] = {}
    for boundary in realized_boundaries:
        manifest = build_random_projection(
            snapshot,
            boundary,
            structural_selection,
            instance_id=instance_id,
            handoffs=handoff_values,
            protocol_content_hash=protocol_content_hash,
        )
        path = root / f"{manifest['projection_id']}.json"
        content = _encode(manifest)
        if path.exists():
            if path.is_symlink() or path.read_bytes() != content:
                raise ValueError(
                    f"stored random projection changed: {manifest['projection_id']}"
                )
        else:
            temporary = root / f".{manifest['projection_id']}.tmp"
            temporary.write_bytes(content)
            temporary.replace(path)
            path.chmod(0o444)
        frozen[str(boundary["boundary_id"])] = manifest
    return frozen


def load_frozen_random_projections(
    projection_dir: Path | str,
    snapshot: EtiqEvidenceSnapshot,
    realized_boundaries: Iterable[Mapping[str, Any]],
    structural_selection: Mapping[str, Any],
    *,
    instance_id: str,
    handoffs: Iterable[Mapping[str, Any]] = (),
) -> dict[str, dict[str, Any]]:
    boundaries = [dict(value) for value in realized_boundaries]
    expected_ids = {
        str(boundary["boundary_id"]): _projection_id(
            instance_id=instance_id,
            job_id=snapshot.job_id,
            boundary_id=str(boundary["boundary_id"]),
        )
        for boundary in boundaries
    }
    root = Path(projection_dir).absolute()
    manifests: dict[str, dict[str, Any]] = {}
    handoff_values = [dict(value) for value in handoffs]
    for boundary in boundaries:
        boundary_id = str(boundary["boundary_id"])
        path = root / f"{expected_ids[boundary_id]}.json"
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"frozen random projection is missing: {boundary_id}")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifests[boundary_id] = verify_random_projection_manifest(
            snapshot,
            boundary,
            structural_selection,
            manifest,
            instance_id=instance_id,
            handoffs=handoff_values,
        )
    return manifests


def assemble_random_section_projection(
    boundary_ids: Iterable[str],
    frozen_by_boundary: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Union stored appearances without deriving, redrawing, or refilling."""
    ids = [str(value) for value in boundary_ids]
    missing = set(ids) - set(frozen_by_boundary)
    if missing:
        raise ValueError(f"section references an unfrozen random boundary: {sorted(missing)}")
    manifests = [frozen_by_boundary[boundary_id] for boundary_id in ids]
    return {
        "projection_ids": sorted({str(value["projection_id"]) for value in manifests}),
        "projection_hashes": sorted(
            {str(value["projection_sha256"]) for value in manifests}
        ),
        "node_refs": sorted(
            {str(ref) for value in manifests for ref in value["node_refs"]}
        ),
        "relationship_refs": sorted(
            {str(ref) for value in manifests for ref in value["relationship_refs"]}
        ),
        "resampled": False,
        "residual_budget_refilled": False,
    }


def random_projection_diagnostic(
    manifest: Mapping[str, Any],
    *,
    snapshot: EtiqEvidenceSnapshot | None = None,
    boundary: Mapping[str, Any] | None = None,
    structural_selection: Mapping[str, Any] | None = None,
    token_estimator: Callable[[str], int] | None = None,
) -> dict[str, Any]:
    structural_bytes = int(manifest["structural_residual_utf8_bytes"])
    random_bytes = int(manifest["random_residual_utf8_bytes"])
    result = {
        "structural_residual_utf8_bytes": structural_bytes,
        "random_residual_utf8_bytes": random_bytes,
        "absolute_byte_difference": abs(random_bytes - structural_bytes),
        "within_tolerance": abs(random_bytes - structural_bytes)
        <= int(manifest["budget_tolerance_utf8_bytes"]),
        "structural_estimated_tokens": None,
        "random_estimated_tokens": None,
    }
    if token_estimator is not None:
        if snapshot is None or boundary is None or structural_selection is None:
            raise ValueError(
                "token diagnostics require the frozen snapshot, boundary, and structural selection"
            )
        mandatory_nodes, mandatory_relationships = _mandatory_interface(snapshot, boundary)
        visible = structural_selection["visible_evidence_by_boundary"][str(boundary["boundary_id"])]
        structural_serialized = _serialized_evidence_bytes(
            snapshot,
            set(map(str, visible["node_refs"])) - mandatory_nodes,
            set(map(str, visible["relationship_refs"])) - mandatory_relationships,
        )
        random_serialized = _serialized_evidence_bytes(
            snapshot,
            manifest["residual_node_refs"],
            manifest["residual_relationship_refs"],
        )
        result["structural_estimated_tokens"] = token_estimator(
            structural_serialized.decode("utf-8")
        )
        result["random_estimated_tokens"] = token_estimator(
            random_serialized.decode("utf-8")
        )
    return result


def annotate_oracle_inclusion(
    frozen_manifest: Mapping[str, Any], oracle_node_ref: str | None
) -> dict[str, Any]:
    """Post-freeze analysis only; never call this while constructing a projection."""
    return {
        "projection_sha256": str(frozen_manifest["projection_sha256"]),
        "oracle_node_ref": oracle_node_ref,
        "oracle_node_included": bool(
            oracle_node_ref and oracle_node_ref in frozen_manifest["node_refs"]
        ),
        "recorded_after_projection_freeze": True,
    }
