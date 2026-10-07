"""N22 matched formal-semantics, SHACL, and SHACL-first experiment."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import time
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator
from pyshacl import validate as shacl_validate
from rdflib import BNode, Graph, Literal, Namespace, RDF, RDFS, SH, URIRef, XSD
from rdflib.compare import to_canonical_graph

from . import corrected_experiment as ce
from . import n20a_experiment as n20a
from . import n21_experiment as n21
from .n05_runner import create_bytes_exclusive, verify_record


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-039")
SOURCE_ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-038")
SEMANTIC_ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-037")
TASK = Path("instructions_between_agent_types/developer/current/N22_formal_semantics_shacl_hybrid_experiment.email.md")
TASK_SHA256 = "sha256:30d41444e8cd32bfb7caf3d2dce375a0405bf868e3c4e21d4a340541236fdea0"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N22_formal_semantics_shacl_hybrid_authorization.json")
AUTHORITY_SHA256 = "sha256:9f27d08f040b64740589a8e0ec88e8efcf6ba898ca48ff9fc253aeaa0bdc34f6"
SOURCE_TREE_SHA256 = "sha256:a2ddd9c32734bb8827e89c206448d87b802986cce16b9001e85af854f8fcf931"
SEMANTIC_TREE_SHA256 = "sha256:a7b8d11717d1cb3281757f1f0e2fae542b1b2ee238630a90f1c477bbb88a112c"
PROMPT = Path("prompts/v2_2/n22_formal_review.md")
FINAL_SCHEMA = n21.FINAL_SCHEMA
REQUIRED_SCHEMA = n21.REQUIRED_SCHEMA
INSTANCES = n21.INSTANCES
CLEAN_INSTANCE = n21.CLEAN_INSTANCE
UPSTREAM = n21.UPSTREAM
DOWNSTREAM = n21.DOWNSTREAM
DIRECT_MODES = (
    "llm_source",
    "llm_source_raw_graph",
    "llm_adaptive_native",
    "llm_formal_no_source",
    "llm_source_formal",
)
MODES = (*DIRECT_MODES, "shacl_only", "shacl_then_llm")
MODULE_CONFIGS = (
    ("M0", {"M0_core"}),
    ("M0-M1", {"M0_core", "M1_structure"}),
    ("M0-M2", {"M0_core", "M1_structure", "M2_behaviour"}),
    ("M0-M3", {"M0_core", "M1_structure", "M2_behaviour", "M3_lineage"}),
    ("M0-M4", {"M0_core", "M1_structure", "M2_behaviour", "M3_lineage", "M4_semantics"}),
)
EX = Namespace("urn:use-case-icp:n22:")
MODULE = EX.module
FALLBACK_ALLOWED_KEYS = {"processor_status", "conforms", "violated_shapes", "earliest_candidate_functions", "unevaluable_constraints"}


def _verify_authority(repo_root: Path) -> dict[str, Any]:
    for relative, expected in ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N22 authority input changed: {relative}")
    source_tree = ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT))
    semantic_tree = ce.sha256(ce._tree_hashes(repo_root / SEMANTIC_ATTEMPT))
    if source_tree != SOURCE_TREE_SHA256 or semantic_tree != SEMANTIC_TREE_SHA256:
        raise ValueError("N22 source attempt changed")
    for relative, expected in ce.N15_PROTECTED_FILE_SHA256.items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N22 protected execution surface changed: {relative}")
    return {
        "attempt_038_tree_sha256": source_tree,
        "attempt_037_tree_sha256": semantic_tree,
        "protected_hashes": deepcopy(ce.N15_PROTECTED_FILE_SHA256),
    }


def _iri(kind: str, value: Any) -> URIRef:
    return EX[f"{kind}/{ce.sha256(value)[7:]}"]


def _canonical_rdf(graph: Graph) -> str:
    canonical = Graph()
    for triple in to_canonical_graph(graph):
        canonical.add(triple)
    canonical.bind("ex", EX)
    canonical.bind("sh", SH)
    canonical.bind("rdf", RDF)
    canonical.bind("rdfs", RDFS)
    canonical.bind("xsd", XSD)
    return canonical.serialize(format="turtle")


def _parse_rdf(text: str) -> Graph:
    graph = Graph()
    graph.parse(data=text, format="turtle", publicID=str(EX))
    return graph


def _literal(value: Any) -> Literal:
    if isinstance(value, bool):
        return Literal(value, datatype=XSD.boolean)
    if isinstance(value, int):
        return Literal(value, datatype=XSD.integer)
    if isinstance(value, float):
        return Literal(value, datatype=XSD.double)
    if value is None:
        return Literal("null")
    return Literal(str(value))


def _function_name(node: Mapping[str, Any]) -> str | None:
    metadata = node.get("raw_metadata", {})
    name = metadata.get("v21_qualified_function_name")
    if name:
        return str(name)
    stack = list(node.get("func_stack", []))
    if len(stack) >= 2:
        return str(stack[1]).split(",", 1)[0]
    return None


def _function_resources(catalogue: Mapping[str, Any]) -> dict[tuple[str, str], URIRef]:
    resources = {}
    for job_id in catalogue["job_order"]:
        for node in catalogue["jobs"][job_id]["nodes"]:
            name = _function_name(node)
            if name in {"select_demand", "normalize", "assemble_provenance", "map_coverage", "prioritize", "synthesize"}:
                resources[(str(job_id), name)] = _iri("function", [job_id, name])
    if len(resources) != 6:
        raise ValueError("N22 could not bind all six captured functions")
    return resources


def _add_row(graph: Graph, collection: URIRef, row: Mapping[str, Any], index: int, identity: Any) -> URIRef:
    row_iri = _iri("record", [identity, index, row])
    graph.add((collection, EX.row, row_iri))
    graph.add((row_iri, RDF.type, EX.Record))
    graph.add((row_iri, EX.rowOrder, Literal(index, datatype=XSD.integer)))
    predicates = {
        "record_id": EX.recordId,
        "need": EX.needText,
        "demand_score": EX.demandScore,
        "source_id": EX.sourceId,
        "source_weight": EX.sourceWeight,
        "rank": EX.rank,
        "capability_id": EX.capabilityId,
        "coverage": EX.coverage,
        "unsupported": EX.unsupported,
        "upstream_rank": EX.upstreamRank,
        "priority_rank": EX.priorityRank,
    }
    unknown = set(row) - set(predicates)
    if unknown:
        raise ValueError(f"N22 has no frozen RDF predicate for fields: {sorted(unknown)}")
    for key, value in row.items():
        graph.add((row_iri, predicates[key], _literal(value)))
    return row_iri


def _add_collection(graph: Graph, case: URIRef, stage: str, rows: list[Mapping[str, Any]], stage_type: URIRef, producer: URIRef | None, *, complete: bool = True) -> URIRef:
    collection = _iri("collection", [str(case), stage])
    graph.add((case, EX.stageCollection, collection))
    graph.add((collection, RDF.type, EX.StageCollection))
    graph.add((collection, RDF.type, stage_type))
    graph.add((collection, EX.stageIdentity, Literal(stage)))
    graph.add((collection, EX.complete, Literal(complete, datatype=XSD.boolean)))
    graph.add((collection, EX.rowCount, Literal(len(rows), datatype=XSD.integer)))
    if producer is not None:
        graph.add((collection, EX.producedBy, producer))
    for index, row in enumerate(rows, 1):
        _add_row(graph, collection, row, index, [str(case), stage])
    return collection


def _selected_rows(catalogue: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]], bool]:
    candidates = [
        node for node in catalogue["jobs"][UPSTREAM]["nodes"]
        if node.get("state_type") == "DataframeState"
        and node.get("names") == ["selected"]
        and node.get("func_stack") == ["main"]
        and node.get("artifact_kind") == "table"
        and isinstance(node.get("artifact_content"), Mapping)
    ]
    if len(candidates) != 1:
        raise ValueError("N22 selected-stage capture is not unique")
    node = candidates[0]
    return deepcopy(node["artifact_content"]["rows"]), not bool(node.get("artifact_truncated"))


def build_abox(catalogue: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    graph = Graph()
    case = _iri("case", catalogue["catalogue_sha256"])
    graph.add((case, RDF.type, EX.ExecutionCase))
    graph.add((case, EX.catalogueDigest, Literal(catalogue["catalogue_sha256"])))
    function_resources = _function_resources(catalogue)
    node_iris: dict[str, URIRef] = {}
    relationship_iris: dict[str, URIRef] = {}
    artifact_iris: dict[str, URIRef] = {}
    mapping: dict[str, Any] = {"case_iri": str(case), "nodes": {}, "relationships": {}, "artifacts": {}, "handoffs": {}}
    jobs = {}
    for order, job_id in enumerate(catalogue["job_order"], 1):
        job = _iri("job", job_id)
        execution = _iri("job-execution", [catalogue["catalogue_sha256"], job_id])
        jobs[str(job_id)] = job
        graph.add((case, EX.jobExecution, execution))
        graph.add((execution, RDF.type, EX.JobExecution))
        graph.add((execution, EX.executesJob, job))
        graph.add((execution, EX.jobOrder, Literal(order, datatype=XSD.integer)))
        graph.add((job, RDF.type, EX.Job))
        graph.add((job, EX.jobIdentity, Literal(str(job_id))))
        for node in catalogue["jobs"][job_id]["nodes"]:
            ref = str(node["node_ref"])
            subject = _iri("node", ref)
            node_iris[ref] = subject
            graph.add((execution, EX.capturedNode, subject))
            graph.add((subject, RDF.type, EX.NativeNode))
            graph.add((subject, EX.withinJob, job))
            graph.add((subject, EX.nodeRef, Literal(ref)))
            graph.add((subject, EX.nodeDigest, Literal(str(node["node_sha256"]))))
            graph.add((subject, EX.stateType, Literal(str(node["state_type"]))))
            graph.add((subject, EX.scopeType, Literal(str(node["scope_type"]))))
            graph.add((subject, EX.rawFuncStack, Literal(ce.canonical_json(node.get("func_stack", [])).decode())))
            graph.add((subject, EX.namesJson, Literal(ce.canonical_json(node.get("names", [])).decode())))
            if node.get("line_no") is not None:
                graph.add((subject, EX.sourceLine, Literal(int(node["line_no"]), datatype=XSD.integer)))
            graph.add((subject, EX.sourceDigest, Literal(ce.sha256(str(node.get("source") or "").encode()))))
            name = _function_name(node)
            if node.get("state_type") == "FunctionMapping":
                graph.add((subject, RDF.type, EX.FunctionExecution))
            if len(node.get("func_stack", [])) >= 3:
                graph.add((subject, RDF.type, EX.NestedExecution))
            if name:
                graph.add((subject, EX.functionIdentity, Literal(name)))
            artifact_digest = node.get("artifact_value_sha256")
            if artifact_digest:
                artifact = artifact_iris.setdefault(str(artifact_digest), _iri("artifact", artifact_digest))
                graph.add((subject, EX.hasArtifact, artifact))
                graph.add((artifact, RDF.type, EX.ArtifactState))
                graph.add((artifact, EX.artifactDigest, Literal(str(artifact_digest))))
                graph.add((artifact, EX.artifactKind, Literal(str(node.get("artifact_kind") or ""))))
                graph.add((artifact, EX.complete, Literal(not bool(node.get("artifact_truncated")), datatype=XSD.boolean)))
                if node.get("artifact_kind") == "table":
                    graph.add((artifact, RDF.type, EX.TableArtifact))
                if str(artifact_digest) not in mapping["artifacts"]:
                    content = node.get("artifact_content")
                    if isinstance(content, Mapping) and isinstance(content.get("rows"), list):
                        graph.add((artifact, EX.columnsJson, Literal(ce.canonical_json(content.get("columns", [])).decode())))
                        for row_index, row in enumerate(content["rows"], 1):
                            _add_row(graph, artifact, row, row_index, artifact_digest)
                    else:
                        graph.add((artifact, EX.artifactValueJson, Literal(ce.canonical_json(content).decode())))
                    mapping["artifacts"][str(artifact_digest)] = {"iri": str(artifact), "value_sha256": ce.sha256(content)}
            mapping["nodes"][ref] = {
                "iri": str(subject),
                "node_sha256": node["node_sha256"],
                "source_sha256": ce.sha256(str(node.get("source") or "").encode()),
            }
        for (resource_job, function_name), resource in function_resources.items():
            if resource_job == job_id:
                graph.add((resource, RDF.type, EX.FunctionExecution))
                graph.add((resource, EX.functionIdentity, Literal(function_name)))
                graph.add((resource, EX.withinJob, job))
    for job_id in catalogue["job_order"]:
        execution = _iri("job-execution", [catalogue["catalogue_sha256"], job_id])
        for edge in catalogue["jobs"][job_id]["relationships"]:
            ref = str(edge["relationship_ref"])
            relation = _iri("relationship", ref)
            relationship_iris[ref] = relation
            source = node_iris[str(edge["source_ref"])]
            target = node_iris[str(edge["target_ref"])]
            kind = str(edge["relationship_type"])
            graph.add((execution, EX.capturedRelationship, relation))
            graph.add((relation, RDF.type, EX.CapturedRelationship))
            graph.add((relation, EX.relationshipRef, Literal(ref)))
            graph.add((relation, EX.relationshipDigest, Literal(str(edge["relationship_sha256"]))))
            graph.add((relation, EX.relationshipType, Literal(kind)))
            graph.add((relation, EX.sourceNode, source))
            graph.add((relation, EX.targetNode, target))
            graph.add((source, EX.influences, target))
            if kind == "function_argument":
                graph.add((source, EX.functionArgument, target))
                graph.add((source, EX.consumer, target))
            elif kind == "function_result":
                graph.add((source, EX.functionResult, target))
                graph.add((target, EX.producer, source))
            elif kind == "state_parent":
                graph.add((source, EX.stateParent, target))
            mapping["relationships"][ref] = {"iri": str(relation), "relationship_sha256": edge["relationship_sha256"]}
    for node in (n for job_id in catalogue["job_order"] for n in catalogue["jobs"][job_id]["nodes"]):
        stack = tuple(node.get("func_stack", []))
        if len(stack) < 3:
            continue
        job_id = next(job for job in catalogue["job_order"] if node in catalogue["jobs"][job]["nodes"])
        parent_name = str(stack[1]).split(",", 1)[0]
        parent = function_resources.get((str(job_id), parent_name))
        if parent is not None:
            graph.add((node_iris[str(node["node_ref"])], EX.nestedWithin, parent))
    for handoff in catalogue["handoffs"]:
        resource = _iri("handoff", [catalogue["catalogue_sha256"], handoff["handoff_id"]])
        graph.add((case, EX.controllerHandoff, resource))
        graph.add((resource, RDF.type, EX.ControllerRecordedHandoff))
        graph.add((resource, EX.handoffIdentity, Literal(str(handoff["handoff_id"]))))
        graph.add((resource, EX.artifactName, Literal(str(handoff["artifact_name"]))))
        graph.add((resource, EX.producerDigest, Literal(str(handoff["producer_sha256"]))))
        graph.add((resource, EX.consumerDigest, Literal(str(handoff["consumer_sha256"]))))
        graph.add((resource, EX.producerJob, jobs[str(handoff["upstream_job_id"])]))
        graph.add((resource, EX.consumerJob, jobs[str(handoff["downstream_job_id"])]))
        graph.add((resource, EX.controllerRecorded, Literal(True, datatype=XSD.boolean)))
        graph.add((resource, EX.nativeEtiqEdge, Literal(False, datatype=XSD.boolean)))
        mapping["handoffs"][str(handoff["handoff_id"])] = {"iri": str(resource), "record_sha256": ce.sha256(handoff)}
    upstream = catalogue["jobs"][UPSTREAM]
    downstream = catalogue["jobs"][DOWNSTREAM]
    selected, selected_complete = _selected_rows(catalogue)
    stages = {
        "corpus": _add_collection(graph, case, "corpus", deepcopy(upstream["input"]["corpus"]), EX.CorpusStage, None),
        "selection": _add_collection(graph, case, "selection", selected, EX.SelectionStage, function_resources[(UPSTREAM, "select_demand")], complete=selected_complete),
        "needs": _add_collection(graph, case, "needs", deepcopy(upstream["output"]["needs"]), EX.NeedsStage, function_resources[(UPSTREAM, "normalize")]),
        "provenance": _add_collection(graph, case, "provenance", deepcopy(upstream["output"]["evidence_sources"]), EX.ProvenanceStage, function_resources[(UPSTREAM, "assemble_provenance")]),
        "coverage": _add_collection(graph, case, "coverage", deepcopy(downstream["output"]["coverage"]), EX.CoverageStage, function_resources[(DOWNSTREAM, "map_coverage")]),
        "priorities": _add_collection(graph, case, "priorities", deepcopy(downstream["output"]["priorities"]), EX.PriorityStage, function_resources[(DOWNSTREAM, "prioritize")]),
    }
    recommendation = _iri("recommendation", catalogue["catalogue_sha256"])
    graph.add((case, EX.recommendation, recommendation))
    graph.add((recommendation, RDF.type, EX.RecommendationStage))
    graph.add((recommendation, EX.topNeed, Literal(str(downstream["output"]["recommendation"]["top_need"]))))
    graph.add((recommendation, EX.decision, Literal(str(downstream["output"]["recommendation"]["decision"]))))
    graph.add((recommendation, EX.producedBy, function_resources[(DOWNSTREAM, "synthesize")]))
    mapping["stages"] = {key: str(value) for key, value in stages.items()}
    mapping["recommendation"] = str(recommendation)
    mapping["mapping_sha256"] = ce.sha256(mapping)
    return _canonical_rdf(graph), mapping


def build_ontology() -> str:
    graph = Graph()
    classes = (
        "ExecutionCase", "Job", "JobExecution", "NativeNode", "FunctionExecution",
        "NestedExecution", "ArtifactState", "TableArtifact", "Record", "FieldValue",
        "CapturedRelationship", "ControllerRecordedHandoff", "StageCollection",
        "CorpusStage", "SelectionStage", "NeedsStage", "ProvenanceStage",
        "CoverageStage", "PriorityStage", "RecommendationStage",
    )
    for name in classes:
        graph.add((EX[name], RDF.type, RDFS.Class))
        graph.add((EX[name], MODULE, Literal("M0_core")))
    for child, parent in (
        ("FunctionExecution", "NativeNode"), ("NestedExecution", "NativeNode"),
        ("TableArtifact", "ArtifactState"), ("CorpusStage", "StageCollection"),
        ("SelectionStage", "StageCollection"), ("NeedsStage", "StageCollection"),
        ("ProvenanceStage", "StageCollection"), ("CoverageStage", "StageCollection"),
        ("PriorityStage", "StageCollection"),
    ):
        graph.add((EX[child], RDFS.subClassOf, EX[parent]))
    object_properties = (
        "jobExecution", "executesJob", "capturedNode", "capturedRelationship", "hasArtifact",
        "row", "field", "sourceNode", "targetNode", "functionArgument", "functionResult",
        "stateParent", "producer", "consumer", "influences", "nestedWithin", "withinJob",
        "controllerHandoff", "producerJob", "consumerJob", "stageCollection", "producedBy",
        "recommendation", "earliestProducer", "candidateJob",
    )
    datatype_properties = (
        "catalogueDigest", "jobOrder", "jobIdentity", "nodeRef", "nodeDigest", "stateType",
        "scopeType", "rawFuncStack", "namesJson", "sourceLine", "sourceDigest",
        "functionIdentity", "artifactDigest", "artifactKind", "artifactValueJson", "complete",
        "rowCount", "rowOrder", "columnsJson", "relationshipRef",
        "relationshipDigest", "relationshipType", "handoffIdentity", "artifactName",
        "producerDigest", "consumerDigest", "controllerRecorded", "nativeEtiqEdge", "stageIdentity",
        "recordId", "needText", "demandScore", "sourceId", "sourceWeight", "rank",
        "capabilityId", "coverage", "unsupported", "upstreamRank", "priorityRank", "topNeed",
        "decision", "pipelineRole", "expectedInput", "expectedOutput",
    )
    for name in object_properties:
        graph.add((EX[name], RDF.type, RDF.Property))
        graph.add((EX[name], MODULE, Literal("M0_core")))
    for name in datatype_properties:
        graph.add((EX[name], RDF.type, RDF.Property))
        graph.add((EX[name], MODULE, Literal("M0_core")))
    return _canonical_rdf(graph)


def _sparql_prefixes() -> str:
    return f"PREFIX ex: <{EX}>\nPREFIX xsd: <{XSD}>\n"


def _add_sparql_shape(graph: Graph, name: str, target_class: URIRef, query: str, message: str, module: str) -> None:
    shape = EX[name]
    constraint = BNode()
    graph.add((shape, RDF.type, SH.NodeShape))
    graph.add((shape, SH.targetClass, target_class))
    graph.add((shape, SH.sparql, constraint))
    graph.add((shape, MODULE, Literal(module)))
    graph.add((constraint, SH.select, Literal(_sparql_prefixes() + query.strip())))
    graph.add((constraint, SH.message, Literal(message)))


def build_shapes() -> str:
    graph = Graph()
    job_shape = EX.TwoJobExecutionShape
    graph.add((job_shape, RDF.type, SH.NodeShape))
    graph.add((job_shape, SH.targetClass, EX.ExecutionCase))
    graph.add((job_shape, MODULE, Literal("M1_structure")))
    prop = BNode()
    graph.add((job_shape, SH.property, prop))
    graph.add((prop, SH.path, EX.jobExecution))
    graph.add((prop, SH.minCount, Literal(2, datatype=XSD.integer)))
    graph.add((prop, SH.maxCount, Literal(2, datatype=XSD.integer)))
    graph.add((prop, SH.message, Literal("An execution case must contain exactly two job executions.")))
    _add_sparql_shape(
        graph, "RelationshipEndpointShape", EX.CapturedRelationship,
        """SELECT $this WHERE {
             { FILTER NOT EXISTS { $this ex:sourceNode ?source . ?source a ex:NativeNode . } }
             UNION
             { FILTER NOT EXISTS { $this ex:targetNode ?target . ?target a ex:NativeNode . } }
           }""",
        "Every captured relationship must retain valid native endpoints.", "M1_structure",
    )
    _add_sparql_shape(
        graph, "ExactHandoffContinuityShape", EX.ControllerRecordedHandoff,
        """SELECT $this ?producer WHERE {
             $this ex:producerDigest ?producer ; ex:consumerDigest ?consumer .
             FILTER (?producer != ?consumer)
           }""",
        "Controller-recorded producer and consumer handoff digests must match exactly.", "M1_structure",
    )
    _add_sparql_shape(
        graph, "SelectionCompletenessShape", EX.SelectionStage,
        """SELECT $this ?value WHERE {
             ?corpus a ex:CorpusStage ; ex:complete true ; ex:row ?input .
             $this ex:complete true .
             ?input ex:recordId ?rid ; ex:demandScore ?score .
             FILTER (?score >= 3 || ?rid IN ("n06-r07", "n06-r08"))
             FILTER NOT EXISTS { $this ex:row ?selected . ?selected ex:recordId ?rid . }
             BIND (?rid AS ?value)
           }""",
        "Every qualifying or explicit fallback corpus record must be selected.", "M2_behaviour",
    )
    _add_sparql_shape(
        graph, "SelectionFieldPreservationShape", EX.SelectionStage,
        """SELECT $this ?selected WHERE {
             ?corpus a ex:CorpusStage ; ex:row ?input .
             $this ex:row ?selected .
             ?input ex:recordId ?rid ; ex:needText ?need ; ex:demandScore ?score ; ex:sourceId ?source ; ex:sourceWeight ?weight .
             ?selected ex:recordId ?rid ; ex:needText ?actualNeed ; ex:demandScore ?actualScore ; ex:sourceId ?actualSource ; ex:sourceWeight ?actualWeight .
             FILTER (?need != ?actualNeed || ?score != ?actualScore || ?source != ?actualSource || ?weight != ?actualWeight)
           }""",
        "Selected records must preserve identity, text, score, source, and source weight.", "M2_behaviour",
    )
    _add_sparql_shape(
        graph, "AllowedIdentityRowLimitShape", EX.NeedsStage,
        """SELECT $this ?value WHERE {
             { $this ex:row ?row . ?row ex:recordId ?rid .
               FILTER (?rid NOT IN ("n06-r01", "n06-r02", "n06-r03", "n06-r04", "n06-r05", "n06-r06", "n06-r07", "n06-r08"))
               BIND (?rid AS ?value)
             }
             UNION
             { SELECT $this (COUNT(?row) AS ?value) WHERE { $this ex:row ?row . } GROUP BY $this HAVING (COUNT(?row) > 8) }
             UNION
             { ?selection a ex:SelectionStage ; ex:complete true ; ex:row ?selected .
               $this ex:complete true .
               ?selected ex:recordId ?rid ; ex:needText ?need ; ex:demandScore ?score ; ex:sourceId ?source ; ex:sourceWeight ?weight .
               FILTER NOT EXISTS {
                 $this ex:row ?row . ?row ex:recordId ?rid ; ex:needText ?need ; ex:demandScore ?score ; ex:sourceId ?source ; ex:sourceWeight ?weight .
               }
               BIND (?rid AS ?value)
             }
           }""",
        "Normalized needs must preserve allowed selected rows and the eight-row limit.", "M2_behaviour",
    )
    _add_sparql_shape(
        graph, "ProvenanceIdentityPreservationShape", EX.ProvenanceStage,
        """SELECT $this ?value WHERE {
             ?needs a ex:NeedsStage ; ex:complete true ; ex:row ?need .
             $this ex:complete true .
             ?need ex:recordId ?rid ; ex:sourceId ?source ; ex:sourceWeight ?weight .
             FILTER NOT EXISTS {
               $this ex:row ?provenance . ?provenance ex:recordId ?rid ; ex:sourceId ?source ; ex:sourceWeight ?weight .
             }
             BIND (?rid AS ?value)
           }""",
        "Provenance must preserve record identity, source identity, and source weight.", "M2_behaviour",
    )
    _add_sparql_shape(
        graph, "ProvenanceDemandOrderShape", EX.ProvenanceStage,
        """SELECT $this ?value WHERE {
             ?needs a ex:NeedsStage ; ex:row ?n1, ?n2 .
             ?n1 ex:recordId ?id1 ; ex:demandScore ?score1 .
             ?n2 ex:recordId ?id2 ; ex:demandScore ?score2 .
             $this ex:row ?p1, ?p2 .
             ?p1 ex:recordId ?id1 ; ex:rank ?rank1 .
             ?p2 ex:recordId ?id2 ; ex:rank ?rank2 .
             FILTER ((?score1 > ?score2 && ?rank1 > ?rank2) || (?score1 = ?score2 && STR(?id1) < STR(?id2) && ?rank1 > ?rank2))
             BIND (?p1 AS ?value)
           }""",
        "Provenance rank must follow demand-descending order with record identity tie-breaking.", "M2_behaviour",
    )
    _add_sparql_shape(
        graph, "CoveragePreservationShape", EX.CoverageStage,
        """SELECT $this ?value WHERE {
             ?needs a ex:NeedsStage ; ex:complete true ; ex:row ?need .
             $this ex:complete true .
             ?need ex:recordId ?rid ; ex:needText ?text .
             FILTER NOT EXISTS { $this ex:row ?coverage . ?coverage ex:recordId ?rid ; ex:needText ?text . }
             BIND (?rid AS ?value)
           }""",
        "Coverage must preserve every downstream need identity and text.", "M2_behaviour",
    )
    _add_sparql_shape(
        graph, "UnsupportedFirstPriorityShape", EX.PriorityStage,
        """SELECT $this ?value WHERE {
             $this ex:row ?p1, ?p2 .
             ?p1 ex:unsupported ?u1 ; ex:upstreamRank ?up1 ; ex:priorityRank ?rank1 .
             ?p2 ex:unsupported ?u2 ; ex:upstreamRank ?up2 ; ex:priorityRank ?rank2 .
             FILTER ((?u1 = true && ?u2 = false && ?rank1 > ?rank2) || (?u1 = ?u2 && ?up1 < ?up2 && ?rank1 > ?rank2))
             BIND (?p1 AS ?value)
           }""",
        "Priorities must place unsupported needs first and preserve upstream rank within each group.", "M2_behaviour",
    )
    _add_sparql_shape(
        graph, "RecommendationAgreementShape", EX.RecommendationStage,
        """SELECT $this ?value WHERE {
             $this ex:topNeed ?actualNeed ; ex:decision ?actualDecision .
             ?priorities a ex:PriorityStage ; ex:row ?first .
             ?first ex:priorityRank 1 ; ex:needText ?expectedNeed ; ex:unsupported ?unsupported .
             BIND (IF(?unsupported, "prioritize", "maintain") AS ?expectedDecision)
             FILTER (?actualNeed != ?expectedNeed || ?actualDecision != ?expectedDecision)
             BIND (?actualNeed AS ?value)
           }""",
        "The recommendation must agree with the first priority.", "M2_behaviour",
    )
    return _canonical_rdf(graph)


def _semantic_declarations(repo_root: Path) -> list[dict[str, Any]]:
    root = repo_root / SEMANTIC_ATTEMPT
    for path in sorted((root / "controller-manifests").glob("*.json")):
        manifest = ce._read_json(path)
        condition = manifest["controller_condition"]
        if condition["instance_id"] == CLEAN_INSTANCE and condition["evidence_mode"] == "compact_fixed_guided":
            package = ce._read_json(root / manifest["reviewer_package_path"])
            declarations = package["boundary_guidance"]["semantic_declarations"]
            return [
                {key: deepcopy(item[key]) for key in ("job_id", "function_name", "role", "expected_inputs", "expected_outputs")}
                for item in declarations
            ]
    raise ValueError("N22 neutral semantic declarations not found")


def build_rules(repo_root: Path) -> str:
    graph = Graph()
    lineage = EX.EarliestProducerRule
    lineage_shape = EX.EarliestProducerRuleShape
    graph.add((lineage_shape, RDF.type, SH.NodeShape))
    graph.add((lineage_shape, SH.targetClass, EX.StageCollection))
    graph.add((lineage_shape, SH.rule, lineage))
    graph.add((lineage_shape, MODULE, Literal("M3_lineage")))
    graph.add((lineage, RDF.type, SH.SPARQLRule))
    graph.add((lineage, SH.construct, Literal(_sparql_prefixes() + """
        CONSTRUCT { $this ex:earliestProducer ?function . $this ex:candidateJob ?job . }
        WHERE { $this ex:producedBy ?function . ?function ex:withinJob ?job . }
    """)))
    recommendation = EX.RecommendationEarliestProducerRule
    recommendation_shape = EX.RecommendationEarliestProducerRuleShape
    graph.add((recommendation_shape, RDF.type, SH.NodeShape))
    graph.add((recommendation_shape, SH.targetClass, EX.RecommendationStage))
    graph.add((recommendation_shape, SH.rule, recommendation))
    graph.add((recommendation_shape, MODULE, Literal("M3_lineage")))
    graph.add((recommendation, RDF.type, SH.SPARQLRule))
    graph.add((recommendation, SH.construct, Literal(_sparql_prefixes() + """
        CONSTRUCT { $this ex:earliestProducer ?function . $this ex:candidateJob ?job . }
        WHERE { $this ex:producedBy ?function . ?function ex:withinJob ?job . }
    """)))
    for declaration in _semantic_declarations(repo_root):
        name = declaration["function_name"]
        rule = _iri("semantic-rule", [declaration["job_id"], name])
        shape = _iri("semantic-rule-shape", [declaration["job_id"], name])
        graph.add((shape, RDF.type, SH.NodeShape))
        graph.add((shape, SH.targetClass, EX.FunctionExecution))
        graph.add((shape, SH.rule, rule))
        graph.add((shape, MODULE, Literal("M4_semantics")))
        graph.add((rule, RDF.type, SH.SPARQLRule))
        triples = [f'$this ex:pipelineRole {json.dumps(declaration["role"])} .']
        triples.extend(f'$this ex:expectedInput {json.dumps(value)} .' for value in declaration["expected_inputs"])
        triples.extend(f'$this ex:expectedOutput {json.dumps(value)} .' for value in declaration["expected_outputs"])
        construct = "\n".join(triples)
        query = _sparql_prefixes() + f"CONSTRUCT {{ {construct} }} WHERE {{ $this ex:functionIdentity {json.dumps(name)} . }}"
        graph.add((rule, SH.construct, Literal(query)))
    return _canonical_rdf(graph)


def build_rule_provenance(repo_root: Path) -> dict[str, Any]:
    source = repo_root / SOURCE_ATTEMPT
    clean_source_file = source / "source-bundles" / f"{CLEAN_INSTANCE}.json"
    clean_package = None
    for path in sorted((source / "controller-manifests").glob("*.json")):
        manifest = ce._read_json(path)
        condition = manifest["controller_condition"]
        if condition["instance_id"] == CLEAN_INSTANCE and condition["evidence_mode"] == "current_open":
            clean_package = ce._read_json(source / manifest["reviewer_package_path"])
            break
    if clean_package is None:
        raise ValueError("N22 clean Current package not found")
    criteria = deepcopy(clean_package["behavioural_criteria"])
    rules = [
        ("selection_completeness", 1), ("field_preservation", 1), ("allowed_identity_and_row_limit", 2),
        ("provenance_identity_and_weight", 3), ("provenance_demand_order", 3),
        ("exact_handoff_continuity", 4), ("coverage_preservation", 5),
        ("unsupported_first_priority", 6), ("recommendation_agreement", 6),
    ]
    record = {
        "schema_version": "n22-rule-provenance-1",
        "clean_source_bundle_file_sha256": ce.sha256(clean_source_file.read_bytes()),
        "criteria": criteria,
        "rules": [
            {
                "rule_id": rule_id,
                "source_kind": "reviewer_visible_clean_contract",
                "criterion": criteria[min(index, len(criteria) - 1)],
                "source_file": "source-bundles/n16-clean-control.json",
                "source_file_sha256": ce.sha256(clean_source_file.read_bytes()),
            }
            for rule_id, index in rules
        ],
        "constants": {
            "selection_threshold": {"value": 3, "source": "frozen clean Job-1 source"},
            "fallback_record_ids": {"value": ["n06-r07", "n06-r08"], "source": "frozen clean Job-1 source"},
            "allowed_record_ids": {"value": [f"n06-r0{i}" for i in range(1, 9)], "source": "frozen clean Job-1 and Job-2 source"},
            "row_limit": {"value": 8, "source": "frozen clean source and reviewer-visible criterion"},
        },
        "semantic_declarations": _semantic_declarations(repo_root),
    }
    record["provenance_sha256"] = ce.sha256(record)
    return record


def _active_shapes(shapes_text: str, rules_text: str, modules: set[str]) -> Graph:
    graph = _parse_rdf(shapes_text)
    for triple in _parse_rdf(rules_text):
        graph.add(triple)
    for subject, module in list(graph.subject_objects(MODULE)):
        if str(module) not in modules:
            graph.add((subject, SH.deactivated, Literal(True, datatype=XSD.boolean)))
            for rule in list(graph.objects(subject, SH.rule)):
                graph.remove((subject, SH.rule, rule))
    return graph


def _unevaluable_constraints(data: Graph, modules: set[str]) -> list[dict[str, Any]]:
    if "M2_behaviour" not in modules:
        return []
    requirements = {
        "selection_completeness": (EX.CorpusStage, EX.SelectionStage),
        "field_preservation": (EX.CorpusStage, EX.SelectionStage),
        "allowed_identity_and_row_limit": (EX.SelectionStage, EX.NeedsStage),
        "provenance_identity_and_weight": (EX.NeedsStage, EX.ProvenanceStage),
        "provenance_demand_order": (EX.NeedsStage, EX.ProvenanceStage),
        "coverage_preservation": (EX.NeedsStage, EX.CoverageStage),
        "unsupported_first_priority": (EX.PriorityStage,),
        "recommendation_agreement": (EX.PriorityStage, EX.RecommendationStage),
    }
    unevaluable = []
    for constraint, classes in requirements.items():
        missing = []
        for class_iri in classes:
            resources = list(data.subjects(RDF.type, class_iri))
            if not resources:
                missing.append(str(class_iri))
                continue
            for resource in resources:
                if class_iri != EX.RecommendationStage and (resource, EX.complete, Literal(True, datatype=XSD.boolean)) not in data:
                    missing.append(str(resource))
        if missing:
            unevaluable.append({"constraint": constraint, "missing_or_incomplete_evidence": sorted(set(missing))})
    return unevaluable


def _report_result(report: Graph, result: URIRef | BNode) -> dict[str, Any]:
    predicates = {
        "focus_node": SH.focusNode,
        "result_path": SH.resultPath,
        "source_shape": SH.sourceShape,
        "source_constraint_component": SH.sourceConstraintComponent,
        "value": SH.value,
        "result_message": SH.resultMessage,
        "result_severity": SH.resultSeverity,
    }
    output = {}
    for key, predicate in predicates.items():
        values = sorted(str(value) for value in report.objects(result, predicate))
        output[key] = values[0] if len(values) == 1 else values
    return output


def _diagnosis(report: Graph, data: Graph, processor_status: str, modules: set[str]) -> dict[str, Any]:
    report_nodes = list(report.subjects(RDF.type, SH.ValidationReport))
    conforms = bool(report_nodes and next(iter(report.objects(report_nodes[0], SH.conforms)), Literal(False)).toPython())
    result_nodes = sorted({result for node in report_nodes for result in report.objects(node, SH.result)}, key=str)
    results = [_report_result(report, result) for result in result_nodes]
    focus_nodes = sorted({str(value) for result in result_nodes for value in report.objects(result, SH.focusNode)})
    candidates: dict[tuple[str, str], dict[str, str]] = {}
    proof_paths = []
    for focus_text in focus_nodes:
        focus = URIRef(focus_text)
        for function in data.objects(focus, EX.earliestProducer):
            names = sorted(str(value) for value in data.objects(function, EX.functionIdentity))
            jobs = sorted(data.objects(function, EX.withinJob), key=str)
            for name in names:
                for job in jobs:
                    job_ids = sorted(str(value) for value in data.objects(job, EX.jobIdentity))
                    for job_id in job_ids:
                        candidates[(job_id, name)] = {"job_id": job_id, "function_name": name, "function_iri": str(function)}
                        proof_paths.append({"focus_node": focus_text, "predicate": str(EX.earliestProducer), "function_iri": str(function), "function_name": name, "job_id": job_id})
    candidate_records = [candidates[key] for key in sorted(candidates)]
    unevaluable = _unevaluable_constraints(data, modules)
    diagnosis = {
        "schema_version": "n22-shacl-diagnosis-1",
        "processor_status": processor_status,
        "conforms": conforms,
        "fault_detected": bool(result_nodes),
        "violated_shapes": sorted({value for item in results for value in ([item.get("source_shape")] if isinstance(item.get("source_shape"), str) else item.get("source_shape", []))}),
        "focus_nodes": focus_nodes,
        "suspect_jobs": sorted({item["job_id"] for item in candidate_records}),
        "earliest_candidate_functions": candidate_records,
        "singleton_exact_candidate": candidate_records[0] if len(candidate_records) == 1 else None,
        "proof_paths": sorted(proof_paths, key=ce.canonical_json),
        "unevaluable_constraints": unevaluable,
        "validation_results": results,
    }
    diagnosis["diagnosis_sha256"] = ce.sha256(diagnosis)
    return diagnosis


def run_shacl_texts(abox_text: str, ontology_text: str, shapes_text: str, rules_text: str, modules: set[str]) -> tuple[str, dict[str, Any]]:
    data = _parse_rdf(abox_text)
    ontology = _parse_rdf(ontology_text)
    shapes = _active_shapes(shapes_text, rules_text, modules)
    try:
        _, report, _ = shacl_validate(
            data,
            shacl_graph=shapes,
            ont_graph=ontology,
            inference="none",
            advanced=True,
            iterate_rules=True,
            inplace=True,
            do_owl_imports=False,
            js=False,
            meta_shacl=False,
        )
        for predicate in (EX.earliestProducer, EX.candidateJob, EX.pipelineRole, EX.expectedInput, EX.expectedOutput):
            for triple in data.triples((None, predicate, None)):
                report.add(triple)
        status = "ok"
    except Exception as exc:
        report = Graph()
        report_node = EX.ProcessorFailureReport
        report.add((report_node, RDF.type, SH.ValidationReport))
        report.add((report_node, SH.conforms, Literal(False, datatype=XSD.boolean)))
        report.add((report_node, EX.processorDiagnostic, Literal(f"{type(exc).__name__}: {exc}")))
        status = "failed"
    report_text = _canonical_rdf(report)
    return report_text, _diagnosis(_parse_rdf(report_text), data, status, modules)


def route_hybrid(diagnosis: Mapping[str, Any]) -> dict[str, Any]:
    visible = {key: deepcopy(diagnosis.get(key)) for key in FALLBACK_ALLOWED_KEYS}
    status = visible["processor_status"]
    violations = list(visible["violated_shapes"] or [])
    candidates = list(visible["earliest_candidate_functions"] or [])
    unevaluable = list(visible["unevaluable_constraints"] or [])
    if status != "ok" or unevaluable:
        return {"route": "llm_fallback", "reason": "processor_failure_or_unevaluable", "fixed_fault_detected": bool(violations), "unresolved_fields": ["fault_detected", "suspect_job", "suspect_function"], "routing_inputs": visible}
    if violations and len(candidates) == 1:
        return {"route": "shacl_final", "reason": "singleton_violation", "fixed_fault_detected": True, "unresolved_fields": [], "routing_inputs": visible}
    if violations:
        return {"route": "llm_fallback", "reason": "ambiguous_or_unmapped_violation", "fixed_fault_detected": True, "unresolved_fields": ["suspect_job", "suspect_function"], "routing_inputs": visible}
    return {"route": "llm_fallback", "reason": "conforms_true", "fixed_fault_detected": False, "unresolved_fields": ["fault_detected", "suspect_job", "suspect_function"], "routing_inputs": visible}


def _copy_exact(source: Path, target: Path) -> None:
    create_bytes_exclusive(target, source.read_bytes())


def _write_bytes_immutable(path: Path, value: str | bytes) -> None:
    content = value.encode() if isinstance(value, str) else value
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"immutable byte artifact differs: {path}")
        return
    create_bytes_exclusive(path, content)


def _source_package(source_root: Path, instance_id: str, mode: str) -> dict[str, Any]:
    for path in sorted((source_root / "controller-manifests").glob("*.json")):
        manifest = ce._read_json(path)
        condition = manifest["controller_condition"]
        if condition["instance_id"] == instance_id and condition["evidence_mode"] == mode:
            package = ce._read_json(source_root / manifest["reviewer_package_path"])
            if ce.sha256(package) != manifest["reviewer_package_sha256"]:
                raise ValueError("N22 source package hash mismatch")
            return package
    raise ValueError(f"N22 source package not found: {instance_id}: {mode}")


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N22 is authorized only for Attempt 039")
    bindings = _verify_authority(repo_root)
    source = repo_root / SOURCE_ATTEMPT
    for directory in ("captures", "catalogues", "instances", "qualification/mutations", "source-bundles", "native-group-index"):
        for source_path in sorted((source / directory).glob("*.json")):
            _copy_exact(source_path, target / directory / source_path.name)
    _copy_exact(source / "qualification/mutation-summary.json", target / "qualification/mutation-summary.json")
    catalogues = {path.stem: ce._read_json(path) for path in sorted((target / "catalogues").glob("*.json"))}
    instances = {path.stem: ce._read_json(path) for path in sorted((target / "instances").glob("*.json"))}
    indexes = {path.stem: ce._read_json(path) for path in sorted((target / "native-group-index").glob("*.json"))}
    if set(catalogues) != set(INSTANCES) or set(instances) != set(INSTANCES) or set(indexes) != set(INSTANCES):
        raise ValueError("N22 reused record set changed")
    ontology = build_ontology()
    shapes = build_shapes()
    rules = build_rules(repo_root)
    provenance = build_rule_provenance(repo_root)
    _write_bytes_immutable(target / "formal/ontology.ttl", ontology)
    _write_bytes_immutable(target / "formal/shapes.ttl", shapes)
    _write_bytes_immutable(target / "formal/rules.ttl", rules)
    ce._write_immutable(target / "formal/rule-provenance.json", provenance)
    aboxes = {}
    mappings = {}
    source_freeze = ce._read_json(source / "experiment-freeze.json")
    for instance_id in INSTANCES:
        if catalogues[instance_id]["catalogue_sha256"] != source_freeze["catalogue_hashes"][instance_id]:
            raise ValueError(f"N22 catalogue hash changed: {instance_id}")
        if instances[instance_id]["instance_sha256"] != source_freeze["instance_hashes"][instance_id]:
            raise ValueError(f"N22 instance hash changed: {instance_id}")
        abox, mapping = build_abox(catalogues[instance_id])
        aboxes[instance_id] = abox
        mappings[instance_id] = mapping
        _write_bytes_immutable(target / "formal/data" / f"{instance_id}.ttl", abox)
        ce._write_immutable(target / "formal/mappings" / f"{instance_id}.json", mapping)
    return {
        "bindings": bindings,
        "catalogues": catalogues,
        "instances": instances,
        "indexes": indexes,
        "ontology": ontology,
        "shapes": shapes,
        "rules": rules,
        "provenance": provenance,
        "aboxes": aboxes,
        "mappings": mappings,
        "source_packages": {(instance_id, mode): _source_package(source, instance_id, mode) for instance_id in INSTANCES for mode in ("current_open", "adaptive_required_one_native")},
    }


def _formal_evidence(prepared: Mapping[str, Any], instance_id: str, *, complete: bool) -> dict[str, Any]:
    evidence = {
        "abox": prepared["aboxes"][instance_id],
        "predicate_legend": {
            "namespace": str(EX),
            "native_nodes": "capturedNode, nodeRef, stateType, scopeType, rawFuncStack, withinJob",
            "captured_edges": "sourceNode, targetNode, relationshipType; direction is preserved",
            "artifacts": "hasArtifact, artifactValueJson, row, field, rowOrder, complete",
            "lineage": "producer, consumer, influences, nestedWithin",
            "handoffs": "controllerHandoff marks controller-recorded exact hash continuity, not a native edge",
        },
    }
    if complete:
        evidence.update({
            "ontology": prepared["ontology"],
            "shapes": prepared["shapes"],
            "rules": prepared["rules"],
            "rule_provenance": deepcopy(prepared["provenance"]),
        })
    return evidence


def build_package(prepared: Mapping[str, Any], instance_id: str, mode: str) -> dict[str, Any]:
    current = deepcopy(prepared["source_packages"][(instance_id, "current_open")])
    current["schema_version"] = "n22-review-package-1"
    if mode == "llm_source":
        return current
    if mode == "llm_source_raw_graph":
        current["formal_evidence"] = _formal_evidence(prepared, instance_id, complete=False)
        return current
    if mode == "llm_adaptive_native":
        adaptive = deepcopy(prepared["source_packages"][(instance_id, "adaptive_required_one_native")])
        adaptive["schema_version"] = "n22-review-package-1"
        return adaptive
    if mode in {"llm_formal_no_source", "llm_source_formal", "shacl_only", "shacl_then_llm"}:
        current["formal_evidence"] = _formal_evidence(prepared, instance_id, complete=True)
        if mode in {"llm_formal_no_source", "shacl_only"}:
            current.pop("source_bundle", None)
        return current
    raise ValueError(f"unknown N22 mode: {mode}")


def render_request(package: Mapping[str, Any], extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    request = {"reviewer_package": deepcopy(dict(package))}
    if extra is not None:
        request["validated_formal_result"] = deepcopy(dict(extra))
    visible = ce.canonical_json(request).decode()
    forbidden = ("designation", "truth_job", "truth_function", "fault_id", "fault_group", "mutation_span", "mutant_snippet", "evidence_mode", "branch_id", "trial_id", "repetition", "seed", "qualification")
    if any(f'"{key}"' in visible for key in forbidden):
        raise ValueError("N22 rendered request leaks controller state")
    return request


def schedule() -> dict[str, Any]:
    conditions = [
        {"instance_id": instance_id, "evidence_mode": mode, "branch_id": f"brn-{ce.sha256(['n22', instance_id, mode])[7:23]}"}
        for instance_id in INSTANCES for mode in MODES
    ]
    by = {(item["instance_id"], item["evidence_mode"]): item for item in conditions}
    direct = []
    block = 0
    for repetition in range(1, 4):
        rotated_instances = INSTANCES[repetition - 1:] + INSTANCES[:repetition - 1]
        for instance_id in rotated_instances:
            rotation = block % len(DIRECT_MODES)
            for position, mode in enumerate(DIRECT_MODES[rotation:] + DIRECT_MODES[:rotation], 1):
                condition = by[(instance_id, mode)]
                direct.append({
                    **condition,
                    "repetition": repetition,
                    "trial_id": f"trial-{ce.sha256(['n22-direct', condition['branch_id'], repetition])[7:23]}",
                    "schedule_position": len(direct) + 1,
                    "local_block": block + 1,
                    "mode_position": position,
                })
            block += 1
    hybrid = []
    for instance_id in INSTANCES:
        for repetition in range(1, 4):
            condition = by[(instance_id, "shacl_then_llm")]
            hybrid.append({
                **condition,
                "repetition": repetition,
                "trial_id": f"hybrid-{ce.sha256(['n22-hybrid', condition['branch_id'], repetition])[7:23]}",
                "schedule_position": len(hybrid) + 1,
            })
    if (len(conditions), len(direct), len(hybrid), len({x["trial_id"] for x in [*direct, *hybrid]})) != (49, 105, 21, 126):
        raise AssertionError("N22 schedule changed")
    return {"conditions": conditions, "direct_review_trials": direct, "hybrid_outcome_trials": hybrid, "repair_traces": []}


def _contains_key(value: Any, keys: set[str]) -> bool:
    if isinstance(value, Mapping):
        return any(str(key) in keys or _contains_key(child, keys) for key, child in value.items())
    if isinstance(value, list):
        return any(_contains_key(child, keys) for child in value)
    return False


def verify_abox_lossless(catalogue: Mapping[str, Any], abox_text: str, mapping: Mapping[str, Any]) -> dict[str, int]:
    graph = _parse_rdf(abox_text)
    expected_nodes = [node for job_id in catalogue["job_order"] for node in catalogue["jobs"][job_id]["nodes"]]
    expected_relationships = [edge for job_id in catalogue["job_order"] for edge in catalogue["jobs"][job_id]["relationships"]]
    node_refs = {str(value) for value in graph.objects(None, EX.nodeRef)}
    relationship_refs = {str(value) for value in graph.objects(None, EX.relationshipRef)}
    if node_refs != {str(node["node_ref"]) for node in expected_nodes}:
        raise ValueError("N22 ABox node set is not lossless")
    if relationship_refs != {str(edge["relationship_ref"]) for edge in expected_relationships}:
        raise ValueError("N22 ABox relationship set is not lossless")
    for node in expected_nodes:
        subject = URIRef(mapping["nodes"][str(node["node_ref"])]["iri"])
        required = {
            (subject, EX.nodeDigest, Literal(str(node["node_sha256"]))),
            (subject, EX.stateType, Literal(str(node["state_type"]))),
            (subject, EX.scopeType, Literal(str(node["scope_type"]))),
            (subject, EX.rawFuncStack, Literal(ce.canonical_json(node.get("func_stack", [])).decode())),
            (subject, EX.sourceDigest, Literal(ce.sha256(str(node.get("source") or "").encode()))),
        }
        if any(triple not in graph for triple in required):
            raise ValueError("N22 ABox changed captured node metadata")
        digest = node.get("artifact_value_sha256")
        if digest:
            artifact = URIRef(mapping["artifacts"][str(digest)]["iri"])
            if (subject, EX.hasArtifact, artifact) not in graph or (artifact, EX.artifactDigest, Literal(str(digest))) not in graph:
                raise ValueError("N22 ABox changed an artifact binding")
            content = node.get("artifact_content")
            if isinstance(content, Mapping) and isinstance(content.get("rows"), list):
                encoded_rows = sorted(str(value) for row in graph.objects(artifact, EX.row) for value in graph.objects(row, EX.recordId))
                expected_ids = sorted(str(row["record_id"]) for row in content["rows"] if "record_id" in row)
                if encoded_rows != expected_ids:
                    raise ValueError("N22 ABox changed table row identities")
            elif (artifact, EX.artifactValueJson, Literal(ce.canonical_json(content).decode())) not in graph:
                raise ValueError("N22 ABox changed a scalar artifact value")
    for edge in expected_relationships:
        relation = URIRef(mapping["relationships"][str(edge["relationship_ref"])]["iri"])
        if (relation, EX.relationshipType, Literal(str(edge["relationship_type"]))) not in graph:
            raise ValueError("N22 ABox changed a relationship type")
        if (relation, EX.sourceNode, _iri("node", edge["source_ref"])) not in graph or (relation, EX.targetNode, _iri("node", edge["target_ref"])) not in graph:
            raise ValueError("N22 ABox changed relationship direction")
    for handoff in catalogue["handoffs"]:
        resource = URIRef(mapping["handoffs"][str(handoff["handoff_id"])]["iri"])
        if (resource, EX.producerDigest, Literal(str(handoff["producer_sha256"]))) not in graph or (resource, EX.consumerDigest, Literal(str(handoff["consumer_sha256"]))) not in graph:
            raise ValueError("N22 ABox changed a controller handoff")
    return {"nodes": len(expected_nodes), "relationships": len(expected_relationships), "artifacts": len(mapping["artifacts"]), "handoffs": len(catalogue["handoffs"])}


def qualify_packages(repo_root: Path, records: list[Mapping[str, Any]], prepared: Mapping[str, Any], design: Mapping[str, Any]) -> dict[str, Any]:
    if (len(records), len(design["conditions"]), len(design["direct_review_trials"]), len(design["hybrid_outcome_trials"]), len(design["repair_traces"])) != (49, 49, 105, 21, 0):
        raise ValueError("N22 package or schedule count changed")
    hidden_tokens = set(INSTANCES[:-1]) | {"truth_function", "truth_job", "fault_id", "fault_group", "mutation_span", "mutant_snippet", "designation", "suspect"}
    formal_text = "\n".join((prepared["ontology"], prepared["shapes"], prepared["rules"], ce.canonical_json(prepared["provenance"]).decode(), *prepared["aboxes"].values()))
    for token in hidden_tokens:
        if token in formal_text:
            raise ValueError(f"N22 formal artifact leaks hidden material: {token}")
    for text in (prepared["ontology"], prepared["shapes"], prepared["rules"]):
        _parse_rdf(text)
    by = {(record["controller_condition"]["instance_id"], record["controller_condition"]["evidence_mode"]): record["reviewer_package"] for record in records}
    lossless = {}
    for instance_id in INSTANCES:
        packages = {mode: by[(instance_id, mode)] for mode in MODES}
        source = packages["llm_source"]
        raw = packages["llm_source_raw_graph"]
        adaptive = packages["llm_adaptive_native"]
        no_source = packages["llm_formal_no_source"]
        source_formal = packages["llm_source_formal"]
        raw_without_formal = deepcopy(raw)
        raw_evidence = raw_without_formal.pop("formal_evidence")
        if raw_without_formal != source or set(raw_evidence) != {"abox", "predicate_legend"}:
            raise ValueError("N22 Raw Graph differs from Source beyond its ABox and legend")
        formal_base = deepcopy(source_formal)
        formal_evidence = formal_base.pop("formal_evidence")
        if formal_base != source or {key: formal_evidence[key] for key in ("abox", "predicate_legend")} != raw_evidence:
            raise ValueError("N22 Source Formal does not hold Source and ABox constant")
        if set(formal_evidence) != {"abox", "predicate_legend", "ontology", "shapes", "rules", "rule_provenance"}:
            raise ValueError("N22 formal bundle changed")
        expected_no_source = deepcopy(source_formal)
        expected_no_source.pop("source_bundle")
        if no_source != expected_no_source:
            raise ValueError("N22 formal source factor differs by more than source")
        if adaptive["runtime_evidence"] != prepared["source_packages"][(instance_id, "adaptive_required_one_native")]["runtime_evidence"] or adaptive.get("available_operations") != ["expand_execution_group"]:
            raise ValueError("N22 Adaptive Native comparator changed")
        for mode in DIRECT_MODES:
            package = packages[mode]
            if _contains_key(package, {"validation_results", "shacl_validation_report", "inferred_triples", "singleton_exact_candidate", "proof_paths"}):
                raise ValueError(f"N22 direct package contains a validation result: {mode}")
            render_request(package)
        lossless[instance_id] = verify_abox_lossless(prepared["catalogues"][instance_id], prepared["aboxes"][instance_id], prepared["mappings"][instance_id])
    return {
        "status": "passed",
        "model_calls": 0,
        "condition_instance_count": 49,
        "direct_review_count": 105,
        "adaptive_follow_up_count": 21,
        "shacl_validation_count": 7,
        "hybrid_outcome_count": 21,
        "provider_call_maximum": 147,
        "repair_count": 0,
        "lossless_counts": lossless,
    }


def build_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    prepared = prepare_attempt(repo_root, target)
    design = schedule()
    records = []
    for condition in design["conditions"]:
        instance_id = str(condition["instance_id"])
        package = build_package(prepared, instance_id, str(condition["evidence_mode"]))
        record = {
            "schema_version": "n22-frozen-package-1",
            "controller_condition": deepcopy(condition),
            "catalogue_sha256": prepared["catalogues"][instance_id]["catalogue_sha256"],
            "source_bundle_file_sha256": ce.sha256((target / "source-bundles" / f"{instance_id}.json").read_bytes()),
            "abox_file_sha256": ce.sha256((target / "formal/data" / f"{instance_id}.ttl").read_bytes()),
            "native_group_index_file_sha256": ce.sha256((target / "native-group-index" / f"{instance_id}.json").read_bytes()),
            "reviewer_package": package,
        }
        record["package_sha256"] = ce.sha256(record)
        records.append(record)
    qualification = qualify_packages(repo_root, records, prepared, design)
    return {**prepared, "packages": records, "schedule": design, "qualification": qualification}


def _code_paths() -> tuple[Path, ...]:
    return (
        Path("src/use_case_icp/n22_experiment.py"),
        Path("src/use_case_icp/n21_experiment.py"),
        Path("tests/test_n22_experiment.py"),
        Path("pyproject.toml"),
        PROMPT,
        FINAL_SCHEMA,
        REQUIRED_SCHEMA,
    )


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    from importlib.metadata import version

    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if (target / "experiment-freeze.json").exists():
        raise ValueError("Attempt 039 is already frozen")
    if any((target / directory).exists() for directory in ("packages", "controller-manifests", "reviews", "shacl")):
        raise ValueError("Attempt 039 contains pre-freeze scientific outcomes")
    source_before = ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT))
    semantic_before = ce.sha256(ce._tree_hashes(repo_root / SEMANTIC_ATTEMPT))
    built = build_attempt(repo_root, target)
    for record in built["packages"]:
        branch = record["controller_condition"]["branch_id"]
        ce._write_immutable(target / "packages" / branch / "reviewer-package.json", record["reviewer_package"])
        manifest = {key: deepcopy(value) for key, value in record.items() if key != "reviewer_package"}
        manifest.update({"reviewer_package_path": f"packages/{branch}/reviewer-package.json", "reviewer_package_sha256": ce.sha256(record["reviewer_package"])})
        ce._write_immutable(target / "controller-manifests" / f"{branch}.json", manifest)
    ce._write_immutable(target / "review-design.json", {"direct_review_trials": built["schedule"]["direct_review_trials"], "hybrid_outcome_trials": built["schedule"]["hybrid_outcome_trials"]})
    ce._write_immutable(target / "repair-design.json", {"repair_traces": []})
    ce._write_immutable(target / "shacl-design.json", {"instances": list(INSTANCES), "module_configurations": [{"label": label, "modules": sorted(modules)} for label, modules in MODULE_CONFIGS]})
    if ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT)) != source_before or ce.sha256(ce._tree_hashes(repo_root / SEMANTIC_ATTEMPT)) != semantic_before:
        raise RuntimeError("N22 source attempt changed during freeze")
    formal_files = sorted(path for path in (target / "formal").rglob("*") if path.is_file())
    freeze = {
        "schema_version": "n22-formal-semantics-freeze-1",
        "status": "frozen_before_first_shacl_validation_or_provider_call",
        "attempt": "attempt-039",
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "source_bindings": built["bindings"],
        "protected_boundaries": deepcopy(ce.N15_PROTECTED_FILE_SHA256),
        "code_hashes": {path.as_posix(): ce.sha256((repo_root / path).read_bytes()) for path in _code_paths()},
        "dependency_versions": {"rdflib": version("rdflib"), "pyshacl": version("pyshacl")},
        "formal_file_hashes": {path.relative_to(target).as_posix(): ce.sha256(path.read_bytes()) for path in formal_files},
        "package_hashes": sorted(record["package_sha256"] for record in built["packages"]),
        "package_tree_sha256": ce.sha256(ce._tree_hashes(target / "packages")),
        "direct_review_design_sha256": ce.sha256(built["schedule"]["direct_review_trials"]),
        "hybrid_design_sha256": ce.sha256(built["schedule"]["hybrid_outcome_trials"]),
        "expected_counts": {"conditions": 49, "direct_reviews": 105, "adaptive_follow_ups": 21, "shacl_validations": 7, "module_runs": 35, "hybrid_outcomes": 21, "provider_calls_maximum": 147, "repairs": 0},
        "qualification": built["qualification"],
        "model": ce.PROVIDER_MODEL,
        "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "scientific_outcomes_at_freeze": 0,
    }
    freeze["freeze_sha256"] = ce.sha256(freeze)
    path = target / "experiment-freeze.json"
    ce._write_immutable(path, freeze)
    return path


def _load_frozen(attempt_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    catalogues = {path.stem: ce._read_json(path) for path in sorted((attempt_root / "catalogues").glob("*.json"))}
    indexes = {path.stem: ce._read_json(path) for path in sorted((attempt_root / "native-group-index").glob("*.json"))}
    packages = {}
    records = []
    for path in sorted((attempt_root / "controller-manifests").glob("*.json")):
        manifest = ce._read_json(path)
        package = ce._read_json(attempt_root / manifest["reviewer_package_path"])
        if ce.sha256(package) != manifest["reviewer_package_sha256"]:
            raise ValueError("N22 reviewer package hash mismatch")
        record = {**manifest, "reviewer_package": package}
        unsigned = deepcopy(record)
        observed = unsigned.pop("package_sha256")
        unsigned.pop("reviewer_package_path")
        unsigned.pop("reviewer_package_sha256")
        if ce.sha256(unsigned) != observed:
            raise ValueError("N22 package record hash mismatch")
        packages[str(manifest["controller_condition"]["branch_id"])] = record
        records.append(record)
    return catalogues, indexes, packages, records


def verify_frozen_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    from importlib.metadata import version

    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    _verify_authority(repo_root)
    freeze = ce._read_json(target / "experiment-freeze.json")
    observed = ce._verified_self_hash(freeze, "freeze_sha256")
    for relative, expected in freeze["code_hashes"].items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N22 frozen code changed: {relative}")
    for relative, expected in freeze["protected_boundaries"].items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N22 protected execution surface changed: {relative}")
    for dependency, expected in freeze["dependency_versions"].items():
        if version(dependency) != expected:
            raise ValueError(f"N22 dependency changed: {dependency}")
    for relative, expected in freeze["formal_file_hashes"].items():
        if ce.sha256((target / relative).read_bytes()) != expected:
            raise ValueError(f"N22 formal artifact changed: {relative}")
    prepared = prepare_attempt(repo_root, target)
    _, _, _, records = _load_frozen(target)
    design_file = ce._read_json(target / "review-design.json")
    design = {
        "conditions": [deepcopy(record["controller_condition"]) for record in records],
        "direct_review_trials": design_file["direct_review_trials"],
        "hybrid_outcome_trials": design_file["hybrid_outcome_trials"],
        "repair_traces": ce._read_json(target / "repair-design.json")["repair_traces"],
    }
    qualification = qualify_packages(repo_root, records, prepared, design)
    if sorted(record["package_sha256"] for record in records) != freeze["package_hashes"]:
        raise ValueError("N22 frozen packages changed")
    if ce.sha256(design["direct_review_trials"]) != freeze["direct_review_design_sha256"] or ce.sha256(design["hybrid_outcome_trials"]) != freeze["hybrid_design_sha256"]:
        raise ValueError("N22 frozen schedule changed")
    return {"status": "verified", "freeze_sha256": observed, "qualification": qualification, **freeze["expected_counts"]}


def create_live_consumption(repo_root: Path, attempt_root: Path) -> Path:
    path = attempt_root / "live-consumption.json"
    if path.exists():
        ce._verified_self_hash(ce._read_json(path), "consumption_sha256")
        return path
    if list((attempt_root / "reviews").glob("*.json")) or list((attempt_root / "shacl").rglob("diagnosis.json")):
        raise ValueError("N22 scientific outcome exists before live consumption")
    verified = verify_frozen_attempt(repo_root, attempt_root)
    record = {
        "schema_version": "n22-live-consumption-1",
        "status": "live_authority_consumed_before_first_shacl_validation_or_provider_call",
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "freeze_sha256": verified["freeze_sha256"],
        "package_tree_sha256": ce.sha256(ce._tree_hashes(attempt_root / "packages")),
        "formal_tree_sha256": ce.sha256(ce._tree_hashes(attempt_root / "formal")),
        "protected_file_hashes": deepcopy(ce.N15_PROTECTED_FILE_SHA256),
        "model": ce.PROVIDER_MODEL,
        "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "expected_counts": {"direct_reviews": 105, "adaptive_follow_ups": 21, "shacl_validations": 7, "module_runs": 35, "hybrid_outcomes": 21, "provider_calls_maximum": 147, "repairs": 0},
    }
    record["consumption_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return path


def _bind_report(diagnosis: Mapping[str, Any], report_text: str) -> dict[str, Any]:
    bound = deepcopy(dict(diagnosis))
    bound.pop("diagnosis_sha256", None)
    bound["validation_report_file_sha256"] = ce.sha256(report_text.encode())
    bound["diagnosis_sha256"] = ce.sha256(bound)
    return bound


def run_formal_outputs(attempt_root: Path, instance_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    abox = (attempt_root / "formal/data" / f"{instance_id}.ttl").read_text()
    ontology = (attempt_root / "formal/ontology.ttl").read_text()
    shapes = (attempt_root / "formal/shapes.ttl").read_text()
    rules = (attempt_root / "formal/rules.ttl").read_text()
    report_path = attempt_root / "shacl" / instance_id / "validation-report.ttl"
    diagnosis_path = attempt_root / "shacl" / instance_id / "diagnosis.json"
    timing_path = attempt_root / "shacl" / instance_id / "timing.json"
    if diagnosis_path.exists():
        diagnosis = ce._read_json(diagnosis_path)
        ce._verified_self_hash(diagnosis, "diagnosis_sha256")
        if diagnosis["validation_report_file_sha256"] != ce.sha256(report_path.read_bytes()):
            raise ValueError("N22 SHACL report binding changed")
    else:
        started = time.perf_counter()
        report_text, unbound = run_shacl_texts(abox, ontology, shapes, rules, MODULE_CONFIGS[-1][1])
        elapsed = time.perf_counter() - started
        diagnosis = _bind_report(unbound, report_text)
        _write_bytes_immutable(report_path, report_text)
        ce._write_immutable(diagnosis_path, diagnosis)
        ce._write_immutable(timing_path, {"schema_version": "n22-shacl-timing-1", "elapsed_seconds": elapsed})
    module_records = {}
    for label, modules in MODULE_CONFIGS:
        path = attempt_root / "formal/module-runs" / instance_id / f"{label}.json"
        if path.exists():
            record = ce._read_json(path)
            ce._verified_self_hash(record, "module_run_sha256")
        else:
            report_text, unbound = run_shacl_texts(abox, ontology, shapes, rules, modules)
            bound = _bind_report(unbound, report_text)
            record = {
                "schema_version": "n22-module-run-1",
                "configuration": label,
                "active_modules": sorted(modules),
                "report_sha256": ce.sha256(report_text.encode()),
                "diagnosis": bound,
            }
            record["module_run_sha256"] = ce.sha256(record)
            ce._write_immutable(path, record)
        module_records[label] = record
    return diagnosis, module_records


def _normalized_function(value: Any) -> str | None:
    if value is None:
        return None
    names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", str(value).strip().lower())
    return names[-1] if names else None


def validate_response(repo_root: Path, visible_request: Mapping[str, Any], response: Mapping[str, Any], schema_path: Path) -> dict[str, Any]:
    schema = ce._read_json(repo_root / schema_path)
    receipt = {key: deepcopy(response.get(key)) for key in schema["required"]}
    Draft202012Validator(schema).validate(receipt)
    visible = ce.canonical_json(visible_request).decode()
    return {
        "valid": True,
        "receipt": receipt,
        "fault_detected": bool(receipt["fault_detected"]),
        "suspect_job": receipt["suspect_job"],
        "normalized_suspect_function": _normalized_function(receipt["suspect_function"]),
        "invalid_evidence_refs": [str(value) for value in receipt["evidence_refs"] if str(value) not in visible],
    }


def _provider_review(repo_root: Path, attempt_root: Path, request: Mapping[str, Any], parent_id: str, schema_path: Path) -> dict[str, Any]:
    return ce._provider_call(repo_root, attempt_root, kind="review", model_request=request, controller_parent_id=parent_id, review_prompt=PROMPT, review_schema=schema_path)


def _call_record(response: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(response.get(key)) for key in ("request_sha256", "call_ids", "retry_lineage", "attempt_count") if response.get(key) is not None}


def _score(instance: Mapping[str, Any], detected: bool, suspect_jobs: Iterable[str], candidates: Iterable[str]) -> dict[str, Any]:
    jobs = sorted(set(map(str, suspect_jobs)))
    functions = sorted(set(filter(None, (_normalized_function(value) for value in candidates))))
    truth = instance.get("truth_function")
    if truth is None:
        return {"designation": "matched_clean_control", "fault_detected": detected, "false_positive": detected, "correct_job_attribution": False, "truth_function_in_candidate_set": False, "singleton_exact_function": False, "truth_job": None, "truth_function": None, "candidate_functions": functions, "suspect_jobs": jobs}
    correct_job = detected and UPSTREAM in jobs
    truth_present = detected and truth in functions
    return {"designation": "upstream_fault", "fault_detected": detected, "false_positive": False, "correct_job_attribution": correct_job, "truth_function_in_candidate_set": truth_present, "singleton_exact_function": correct_job and functions == [truth], "truth_job": UPSTREAM, "truth_function": truth, "candidate_functions": functions, "suspect_jobs": jobs}


def run_direct_session(repo_root: Path, attempt_root: Path, catalogue: Mapping[str, Any], index: Mapping[str, Any], package: Mapping[str, Any], trial_id: str, mode: str) -> dict[str, Any]:
    started = time.perf_counter()
    request = render_request(package)
    schema = REQUIRED_SCHEMA if mode == "llm_adaptive_native" else FINAL_SCHEMA
    initial = _provider_review(repo_root, attempt_root, request, trial_id, schema)
    pre = validate_response(repo_root, request, initial, schema)
    usage = [ce.actual_usage_record(initial, purpose="initial_review", phase="n22_direct_review")]
    calls = [_call_record(initial)]
    final = pre
    event = None
    diagnostic = None
    if mode == "llm_adaptive_native":
        action = pre["receipt"]["next_action"]
        try:
            expanded, event = n21.expand_execution_group(catalogue, index, package, str(action["execution_group_id"]))
        except ValueError as exc:
            diagnostic = {"status": "invalid_operation_reference", "error": str(exc), "request": deepcopy(action)}
        if event is not None:
            expanded.pop("available_operations", None)
            expanded.pop("action_contract", None)
            follow_request = n21.render_request(expanded, event)
            response = _provider_review(repo_root, attempt_root, follow_request, f"{trial_id}-follow-up-01", FINAL_SCHEMA)
            final = validate_response(repo_root, follow_request, response, FINAL_SCHEMA)
            usage.append(ce.actual_usage_record(response, purpose="native_group_follow_up", phase="n22_direct_review"))
            calls.append(_call_record(response))
    return {
        "pre_validation": pre,
        "final_validation": final,
        "operation_event": event,
        "operation_diagnostic": diagnostic,
        "completed_expansion_count": 1 if event else 0,
        "call_records": calls,
        "usage": ce.aggregate_actual_usage_records(usage),
        "latency_seconds": time.perf_counter() - started,
    }


def run_hybrid_session(repo_root: Path, attempt_root: Path, package: Mapping[str, Any], diagnosis: Mapping[str, Any], report_text: str, trial_id: str) -> dict[str, Any]:
    route = route_hybrid(diagnosis)
    started = time.perf_counter()
    validated_candidates = deepcopy(diagnosis["earliest_candidate_functions"])
    if route["route"] == "shacl_final":
        candidate = validated_candidates[0]
        return {
            "route": route,
            "fault_detected": True,
            "suspect_jobs": [candidate["job_id"]],
            "candidate_functions": [candidate["function_name"]],
            "validated_candidate_functions": validated_candidates,
            "receipt": None,
            "invalid_evidence_refs": [],
            "call_records": [],
            "usage": ce.aggregate_actual_usage_records([]),
            "latency_seconds": time.perf_counter() - started,
        }
    extra = {
        "shacl_validation_report": report_text,
        "shacl_diagnosis": deepcopy(dict(diagnosis)),
        "fixed_validated_conclusions": {
            "fault_detected": True if route["fixed_fault_detected"] else None,
            "validated_candidate_functions": validated_candidates,
        },
        "unresolved_fields": deepcopy(route["unresolved_fields"]),
        "routing_reason": route["reason"],
    }
    request = render_request(package, extra)
    response = _provider_review(repo_root, attempt_root, request, trial_id, FINAL_SCHEMA)
    validation = validate_response(repo_root, request, response, FINAL_SCHEMA)
    detected = True if route["fixed_fault_detected"] else validation["fault_detected"]
    candidate_functions = [validation["normalized_suspect_function"]] if validation["normalized_suspect_function"] else []
    suspect_jobs = [str(validation["suspect_job"])] if validation["suspect_job"] else []
    usage = ce.actual_usage_record(response, purpose="shacl_hybrid_fallback", phase="n22_hybrid")
    return {
        "route": route,
        "fault_detected": detected,
        "suspect_jobs": suspect_jobs,
        "candidate_functions": candidate_functions,
        "validated_candidate_functions": validated_candidates,
        "receipt": deepcopy(validation["receipt"]),
        "invalid_evidence_refs": deepcopy(validation["invalid_evidence_refs"]),
        "call_records": [_call_record(response)],
        "usage": ce.aggregate_actual_usage_records([usage]),
        "latency_seconds": time.perf_counter() - started,
    }


def _mode_summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    faults = [row for row in rows if row["designation"] == "upstream_fault"]
    controls = [row for row in rows if row["designation"] == "matched_clean_control"]
    calls = [call for row in rows for call in row.get("raw_calls", [])]
    return {
        "outcomes": len(rows),
        "fault_detection": {"numerator": sum(row["fault_detected"] for row in faults), "denominator": len(faults)},
        "correct_job_attribution": {"numerator": sum(row["correct_job_attribution"] for row in faults), "denominator": len(faults)},
        "truth_function_in_candidate_set": {"numerator": sum(row["truth_function_in_candidate_set"] for row in faults), "denominator": len(faults)},
        "singleton_exact_function": {"numerator": sum(row["singleton_exact_function"] for row in faults), "denominator": len(faults)},
        "control_false_positives": {"numerator": sum(row["false_positive"] for row in controls), "denominator": len(controls)},
        "mean_candidate_set_size": sum(len(row["candidate_functions"]) for row in rows) / len(rows) if rows else 0.0,
        "unevaluable_constraint_count": sum(len(row.get("unevaluable_constraints", [])) for row in rows),
        "provider_calls": len(calls),
        "input_tokens": sum(int(call.get("input_tokens") or 0) for call in calls),
        "cached_input_tokens": sum(int(call.get("cached_input_tokens") or 0) for call in calls),
        "output_tokens": sum(int(call.get("output_tokens") or 0) for call in calls),
        "latency_seconds": sum(float(row.get("latency_seconds") or 0.0) for row in rows),
        "shacl_seconds": sum(float(row.get("shacl_seconds") or 0.0) for row in rows),
    }


def _rate(summary: Mapping[str, Any], key: str) -> float:
    metric = summary[key]
    return metric["numerator"] / metric["denominator"] if metric["denominator"] else 0.0


def write_module_attribution(attempt_root: Path, module_runs: Mapping[str, Mapping[str, Mapping[str, Any]]], instances: Mapping[str, Mapping[str, Any]]) -> Path:
    metrics = ("any_behavioural_violation", "correct_job_attribution", "truth_function_in_candidate_set", "singleton_exact_function")
    rows = []
    for instance_id in INSTANCES:
        truth = instances[instance_id].get("truth_function")
        if truth is None:
            continue
        first = {metric: None for metric in metrics}
        configurations = []
        for label, _ in MODULE_CONFIGS:
            diagnosis = module_runs[instance_id][label]["diagnosis"]
            functions = [item["function_name"] for item in diagnosis["earliest_candidate_functions"]]
            values = {
                "any_behavioural_violation": diagnosis["fault_detected"],
                "correct_job_attribution": UPSTREAM in diagnosis["suspect_jobs"],
                "truth_function_in_candidate_set": truth in functions,
                "singleton_exact_function": diagnosis["suspect_jobs"] == [UPSTREAM] and functions == [truth],
            }
            configurations.append({"configuration": label, "diagnosis_sha256": diagnosis["diagnosis_sha256"], **values})
            for metric, value in values.items():
                if value and first[metric] is None:
                    first[metric] = label
        rows.append({"instance_id": instance_id, "truth_function": truth, "first_configuration": first, "configurations": configurations})
    record = {"schema_version": "n22-module-attribution-1", "rows": rows}
    record["module_attribution_sha256"] = ce.sha256(record)
    path = attempt_root / "analysis/module-attribution.json"
    ce._write_immutable(path, record)
    return path


def write_analysis(repo_root: Path, attempt_root: Path, direct_reviews: Mapping[str, Mapping[str, Any]], hybrid_reviews: Mapping[str, Mapping[str, Any]], diagnoses: Mapping[str, Mapping[str, Any]], timings: Mapping[str, float], module_runs: Mapping[str, Mapping[str, Mapping[str, Any]]], instances: Mapping[str, Mapping[str, Any]]) -> Path:
    direct_rows = []
    raw_calls = []
    for record in direct_reviews.values():
        trial = record["controller_trial"]
        calls = []
        for index, call in enumerate(record["usage"].get("calls", []), 1):
            tagged = {"trial_id": trial["trial_id"], "call_index": index, **deepcopy(call)}
            calls.append(tagged)
            raw_calls.append(tagged)
        direct_rows.append({
            **deepcopy(trial),
            **{key: deepcopy(record[key]) for key in ("designation", "fault_detected", "false_positive", "correct_job_attribution", "truth_function_in_candidate_set", "singleton_exact_function", "truth_job", "truth_function", "candidate_functions", "suspect_jobs")},
            "unevaluable_constraints": [],
            "completed_expansion_count": record["completed_expansion_count"],
            "selected_execution_group": deepcopy(record["selected_execution_group"]),
            "latency_seconds": record["latency_seconds"],
            "shacl_seconds": 0.0,
            "raw_calls": calls,
        })
    shacl_rows = []
    for instance_id in INSTANCES:
        diagnosis = diagnoses[instance_id]
        scored = _score(instances[instance_id], diagnosis["fault_detected"], diagnosis["suspect_jobs"], [item["function_name"] for item in diagnosis["earliest_candidate_functions"]])
        shacl_rows.append({
            "instance_id": instance_id,
            "evidence_mode": "shacl_only",
            **scored,
            "unevaluable_constraints": deepcopy(diagnosis["unevaluable_constraints"]),
            "proof_paths": deepcopy(diagnosis["proof_paths"]),
            "latency_seconds": timings[instance_id],
            "shacl_seconds": timings[instance_id],
            "raw_calls": [],
        })
    hybrid_rows = []
    for record in hybrid_reviews.values():
        trial = record["controller_trial"]
        calls = []
        for index, call in enumerate(record["usage"].get("calls", []), 1):
            tagged = {"trial_id": trial["trial_id"], "call_index": index, **deepcopy(call)}
            calls.append(tagged)
            raw_calls.append(tagged)
        hybrid_rows.append({
            **deepcopy(trial),
            **{key: deepcopy(record[key]) for key in ("designation", "fault_detected", "false_positive", "correct_job_attribution", "truth_function_in_candidate_set", "singleton_exact_function", "truth_job", "truth_function", "candidate_functions", "suspect_jobs")},
            "validated_candidate_functions": deepcopy(record["validated_candidate_functions"]),
            "route": deepcopy(record["route"]),
            "unevaluable_constraints": deepcopy(diagnoses[trial["instance_id"]]["unevaluable_constraints"]),
            "proof_paths": deepcopy(diagnoses[trial["instance_id"]]["proof_paths"]),
            "latency_seconds": record["latency_seconds"],
            "shacl_seconds": timings[trial["instance_id"]],
            "raw_calls": calls,
        })
    all_rows = [*direct_rows, *shacl_rows, *hybrid_rows]
    mode_rows = {mode: [row for row in all_rows if row["evidence_mode"] == mode] for mode in MODES}
    summaries = {mode: _mode_summary(rows) for mode, rows in mode_rows.items()}
    pairs = (
        ("raw_graph_vs_source", "llm_source", "llm_source_raw_graph"),
        ("formal_vs_raw_graph", "llm_source_raw_graph", "llm_source_formal"),
        ("source_on_formal", "llm_formal_no_source", "llm_source_formal"),
        ("shacl_vs_formal_llm", "llm_formal_no_source", "shacl_only"),
        ("hybrid_vs_shacl", "shacl_only", "shacl_then_llm"),
        ("adaptive_vs_raw", "llm_source_raw_graph", "llm_adaptive_native"),
        ("adaptive_vs_formal", "llm_source_formal", "llm_adaptive_native"),
    )
    contrasts = []
    for name, left, right in pairs:
        contrasts.append({
            "name": name,
            "left": left,
            "right": right,
            **{f"{metric}_rate_difference_right_minus_left": _rate(summaries[right], metric) - _rate(summaries[left], metric) for metric in ("fault_detection", "correct_job_attribution", "truth_function_in_candidate_set", "singleton_exact_function", "control_false_positives")},
            "provider_call_difference_right_minus_left": summaries[right]["provider_calls"] - summaries[left]["provider_calls"],
            "input_token_difference_right_minus_left": summaries[right]["input_tokens"] - summaries[left]["input_tokens"],
        })
    fallback_rows = [row for row in hybrid_rows if row["route"]["route"] == "llm_fallback"]
    route_reasons = {}
    for row in hybrid_rows:
        reason = row["route"]["reason"]
        route_reasons[reason] = route_reasons.get(reason, 0) + 1
    attempt_038 = ce._read_json(repo_root / SOURCE_ATTEMPT / "analysis/summary.json")
    analysis = {
        "schema_version": "n22-formal-semantics-analysis-1",
        "unit_of_independence": "The seven instances are the independent units; three LLM repetitions are averaged within instance.",
        "cross_attempt_limit": "Attempt 039 versus Attempt 038 is descriptive only.",
        "condition_instance_count": 49,
        "direct_review_count": len(direct_rows),
        "shacl_result_count": len(shacl_rows),
        "hybrid_outcome_count": len(hybrid_rows),
        "repair_count": 0,
        "mode_summaries": summaries,
        "prespecified_contrasts": contrasts,
        "hybrid": {
            "instances_finalized_by_shacl": sorted(instance_id for instance_id in INSTANCES if route_hybrid(diagnoses[instance_id])["route"] == "shacl_final"),
            "instances_escalated": sorted(instance_id for instance_id in INSTANCES if route_hybrid(diagnoses[instance_id])["route"] == "llm_fallback"),
            "outcome_route_counts": route_reasons,
            "fallback_provider_calls": len(fallback_rows),
            "llm_calls_avoided": 21 - len(fallback_rows),
            "accuracy_before_fallback": _mode_summary(shacl_rows),
            "accuracy_after_fallback": summaries["shacl_then_llm"],
            "fallback_tokens": {key: summaries["shacl_then_llm"][key] for key in ("input_tokens", "cached_input_tokens", "output_tokens")},
            "end_to_end_latency_seconds": summaries["shacl_then_llm"]["latency_seconds"] + sum(timings.values()),
        },
        "formal_module_runs": {instance_id: {label: record["diagnosis"] for label, record in runs.items()} for instance_id, runs in module_runs.items()},
        "attempt_038_descriptive": {"current_open": attempt_038["mode_summaries"]["current_open"], "adaptive_required_one_native": attempt_038["mode_summaries"]["adaptive_required_one_native"]},
        "direct_rows": sorted(direct_rows, key=lambda row: row["schedule_position"]),
        "shacl_rows": shacl_rows,
        "hybrid_rows": sorted(hybrid_rows, key=lambda row: row["schedule_position"]),
        "raw_per_call_tokens": raw_calls,
        "actual_usage": ce.aggregate_actual_usage_records(raw_calls),
    }
    analysis["analysis_sha256"] = ce.sha256(analysis)
    path = attempt_root / "analysis/summary.json"
    ce._write_immutable(path, analysis)
    write_module_attribution(attempt_root, module_runs, instances)
    return path


def _write_report(attempt_root: Path) -> Path:
    analysis = ce._read_json(attempt_root / "analysis/summary.json")
    replay = ce._read_json(attempt_root / "replay/reconciliation.json")
    lines = [
        "# Attempt 039 — formal semantics, SHACL, and SHACL-first hybrid",
        "",
        f"Completed {analysis['direct_review_count']} direct LLM reviews, {analysis['shacl_result_count']} deterministic full SHACL validations, {analysis['hybrid_outcome_count']} hybrid outcomes, {replay['observed_counts']['logical_provider_calls']} provider calls, and zero repairs.",
        "",
        "SHACL outcomes are one deterministic result per instance. LLM and hybrid fallback arms use three fresh calls per condition where routing requires a call; they are not pooled with symbolic results as independent observations.",
        "",
        "## Mode results",
        "",
        "| Mode | Outcomes | Detection | Job 1 | Truth in candidates | Singleton exact | Control FP | Calls | Input | Cached | Output |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        value = analysis["mode_summaries"][mode]
        lines.append(
            f"| {mode} | {value['outcomes']} | {value['fault_detection']['numerator']}/{value['fault_detection']['denominator']} | "
            f"{value['correct_job_attribution']['numerator']}/{value['correct_job_attribution']['denominator']} | "
            f"{value['truth_function_in_candidate_set']['numerator']}/{value['truth_function_in_candidate_set']['denominator']} | "
            f"{value['singleton_exact_function']['numerator']}/{value['singleton_exact_function']['denominator']} | "
            f"{value['control_false_positives']['numerator']}/{value['control_false_positives']['denominator']} | "
            f"{value['provider_calls']} | {value['input_tokens']} | {value['cached_input_tokens']} | {value['output_tokens']} |"
        )
    hybrid = analysis["hybrid"]
    lines += [
        "",
        "## Hybrid routing",
        "",
        f"- Instances finalized by singleton SHACL result without an LLM: {len(hybrid['instances_finalized_by_shacl'])}.",
        f"- Instances escalated mechanically: {len(hybrid['instances_escalated'])}.",
        f"- Fallback calls: {hybrid['fallback_provider_calls']}; calls avoided: {hybrid['llm_calls_avoided']}.",
        f"- Route outcome counts: `{json.dumps(hybrid['outcome_route_counts'], sort_keys=True)}`.",
        "",
        "## Direct LLM repetitions",
        "",
        "| Pos | Trial | Instance | Mode | Rep | Detected | Job 1 | Candidate functions | Truth present | Singleton | Calls | Input | Cached | Output |",
        "|---:|---|---|---|---:|---|---|---|---|---|---:|---:|---:|---:|",
    ]
    for row in analysis["direct_rows"]:
        calls = row["raw_calls"]
        lines.append(
            f"| {row['schedule_position']} | {row['trial_id']} | {row['instance_id']} | {row['evidence_mode']} | {row['repetition']} | "
            f"{row['fault_detected']} | {row['correct_job_attribution']} | {json.dumps(row['candidate_functions'], separators=(',', ':'))} | "
            f"{row['truth_function_in_candidate_set']} | {row['singleton_exact_function']} | {len(calls)} | "
            f"{sum(int(x.get('input_tokens') or 0) for x in calls)} | {sum(int(x.get('cached_input_tokens') or 0) for x in calls)} | {sum(int(x.get('output_tokens') or 0) for x in calls)} |"
        )
    lines += [
        "",
        "## Deterministic SHACL outcomes",
        "",
        "| Instance | Detected | Job 1 | Candidates | Truth present | Singleton | Unevaluable | SHACL seconds |",
        "|---|---|---|---|---|---|---:|---:|",
    ]
    for row in analysis["shacl_rows"]:
        lines.append(f"| {row['instance_id']} | {row['fault_detected']} | {row['correct_job_attribution']} | {json.dumps(row['candidate_functions'], separators=(',', ':'))} | {row['truth_function_in_candidate_set']} | {row['singleton_exact_function']} | {len(row['unevaluable_constraints'])} | {row['shacl_seconds']:.6f} |")
    lines += [
        "",
        "## Hybrid outcomes",
        "",
        "| Pos | Trial | Instance | Rep | Route | Detected | Job 1 | Candidates | Truth present | Singleton | Calls |",
        "|---:|---|---|---:|---|---|---|---|---|---|---:|",
    ]
    for row in analysis["hybrid_rows"]:
        lines.append(f"| {row['schedule_position']} | {row['trial_id']} | {row['instance_id']} | {row['repetition']} | {row['route']['reason']} | {row['fault_detected']} | {row['correct_job_attribution']} | {json.dumps(row['candidate_functions'], separators=(',', ':'))} | {row['truth_function_in_candidate_set']} | {row['singleton_exact_function']} | {len(row['raw_calls'])} |")
    lines += ["", "Primary contrasts are within Attempt 039. Attempt 038 is retained only as a descriptive comparator.", ""]
    path = attempt_root / "report.md"
    _write_bytes_immutable(path, "\n".join(lines))
    return path


def _write_handoff(repo_root: Path, attempt_root: Path) -> Path:
    freeze = ce._read_json(attempt_root / "experiment-freeze.json")
    analysis = ce._read_json(attempt_root / "analysis/summary.json")
    replay = ce._read_json(attempt_root / "replay/reconciliation.json")
    terminal = ce._read_json(attempt_root / "terminal-state.json")
    artifacts = {
        "freeze": attempt_root / "experiment-freeze.json",
        "formal": attempt_root / "formal",
        "shacl": attempt_root / "shacl",
        "packages": attempt_root / "packages",
        "reviews": attempt_root / "reviews",
        "analysis": attempt_root / "analysis/summary.json",
        "module_attribution": attempt_root / "analysis/module-attribution.json",
        "replay": attempt_root / "replay/reconciliation.json",
        "terminal": attempt_root / "terminal-state.json",
        "report": attempt_root / "report.md",
    }
    hashes = {name: ce.sha256(ce._tree_hashes(path)) if path.is_dir() else ce.sha256(path.read_bytes()) for name, path in artifacts.items()}
    lines = [
        "To: Overseer", "From: Developer", "Subject: N22 Attempt 039 formal-semantics and SHACL-hybrid results", "",
        f"Status: {terminal['status']}",
        f"Authority: `{AUTHORITY}` (`{AUTHORITY_SHA256}`)",
        f"Freeze logical SHA-256: `{freeze['freeze_sha256']}`", "",
        "Counts",
        f"- Conditions: 49; direct reviews: 105; Adaptive follow-ups: 21; full SHACL validations: 7; module runs: 35; hybrid outcomes: 21; repairs: 0.",
        f"- Logical provider calls: {replay['observed_counts']['logical_provider_calls']}.",
        f"- SHACL-finalized instances: {len(analysis['hybrid']['instances_finalized_by_shacl'])}; escalated instances: {len(analysis['hybrid']['instances_escalated'])}; calls avoided: {analysis['hybrid']['llm_calls_avoided']}.", "",
        "Mode results", "",
    ]
    for mode in MODES:
        value = analysis["mode_summaries"][mode]
        lines.append(f"- {mode}: detected {value['fault_detection']['numerator']}/{value['fault_detection']['denominator']}; Job 1 {value['correct_job_attribution']['numerator']}/{value['correct_job_attribution']['denominator']}; truth in candidates {value['truth_function_in_candidate_set']['numerator']}/{value['truth_function_in_candidate_set']['denominator']}; singleton exact {value['singleton_exact_function']['numerator']}/{value['singleton_exact_function']['denominator']}; control FP {value['control_false_positives']['numerator']}/{value['control_false_positives']['denominator']}; calls {value['provider_calls']}; input/output {value['input_tokens']}/{value['output_tokens']}.")
    lines += ["", "Exact artifact hashes", ""] + [f"- `{artifacts[name].relative_to(repo_root)}`: `{digest}`" for name, digest in hashes.items()] + [
        "", "Attempts 037 and 038 remained unchanged. No pipeline, mutation, capture, catalogue, prior response, call ID, or live authority was reused as an Attempt-039 outcome. Protected provider, authentication, sandbox, isolation, and artifact-execution code was unchanged.", "",
    ]
    path = repo_root / "instructions_between_agent_types/developer/handoffs/N22_attempt_039_results_to_overseer.email.md"
    _write_bytes_immutable(path, "\n".join(lines))
    return path


def _replay_formal(attempt_root: Path, diagnoses: Mapping[str, Mapping[str, Any]], module_runs: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> dict[str, Any]:
    ontology = (attempt_root / "formal/ontology.ttl").read_text()
    shapes = (attempt_root / "formal/shapes.ttl").read_text()
    rules = (attempt_root / "formal/rules.ttl").read_text()
    full_matches = {}
    module_matches = {}
    for instance_id in INSTANCES:
        abox = (attempt_root / "formal/data" / f"{instance_id}.ttl").read_text()
        report_text, diagnosis = run_shacl_texts(abox, ontology, shapes, rules, MODULE_CONFIGS[-1][1])
        bound = _bind_report(diagnosis, report_text)
        full_matches[instance_id] = report_text.encode() == (attempt_root / "shacl" / instance_id / "validation-report.ttl").read_bytes() and bound == diagnoses[instance_id]
        module_matches[instance_id] = {}
        for label, modules in MODULE_CONFIGS:
            module_report, module_diagnosis = run_shacl_texts(abox, ontology, shapes, rules, modules)
            recreated = {
                "schema_version": "n22-module-run-1",
                "configuration": label,
                "active_modules": sorted(modules),
                "report_sha256": ce.sha256(module_report.encode()),
                "diagnosis": _bind_report(module_diagnosis, module_report),
            }
            recreated["module_run_sha256"] = ce.sha256(recreated)
            module_matches[instance_id][label] = recreated == module_runs[instance_id][label]
    if not all(full_matches.values()) or not all(value for runs in module_matches.values() for value in runs.values()):
        raise ValueError("N22 deterministic formal replay changed")
    return {"full_shacl_byte_matches": full_matches, "module_run_byte_matches": module_matches}


def execute_lifecycle(repo_root: Path, attempt_root: Path) -> Path:
    repo_root = repo_root.resolve()
    attempt_root = attempt_root.resolve()
    verified = verify_frozen_attempt(repo_root, attempt_root)
    create_live_consumption(repo_root, attempt_root)
    catalogues, indexes, packages, package_records = _load_frozen(attempt_root)
    instances = {instance_id: ce._read_json(attempt_root / "instances" / f"{instance_id}.json") for instance_id in INSTANCES}
    diagnoses = {}
    module_runs = {}
    timings = {}
    for instance_id in INSTANCES:
        diagnosis, runs = run_formal_outputs(attempt_root, instance_id)
        diagnoses[instance_id] = diagnosis
        module_runs[instance_id] = runs
        timings[instance_id] = float(ce._read_json(attempt_root / "shacl" / instance_id / "timing.json")["elapsed_seconds"])
    review_design = ce._read_json(attempt_root / "review-design.json")
    direct_reviews = {}
    for trial in review_design["direct_review_trials"]:
        path = attempt_root / "reviews" / f"{trial['trial_id']}.json"
        if path.exists():
            record = ce._read_json(path)
            ce._verified_self_hash(record, "review_sha256")
            if record.get("controller_trial") != trial or record.get("status") != "complete":
                raise ValueError("invalid N22 partial direct review")
        else:
            instance_id = str(trial["instance_id"])
            package_record = packages[str(trial["branch_id"])]
            session = run_direct_session(repo_root, attempt_root, catalogues[instance_id], indexes[instance_id], package_record["reviewer_package"], str(trial["trial_id"]), str(trial["evidence_mode"]))
            final = session["final_validation"]
            scored = _score(instances[instance_id], final["fault_detected"], [final["suspect_job"]] if final["suspect_job"] else [], [final["normalized_suspect_function"]] if final["normalized_suspect_function"] else [])
            event = session["operation_event"]
            record = {
                "schema_version": "n22-direct-review-record-1",
                "controller_trial": deepcopy(trial),
                "package_sha256": package_record["package_sha256"],
                "receipt": deepcopy(final["receipt"]),
                "pre_receipt": deepcopy(session["pre_validation"]["receipt"]),
                "invalid_evidence_refs": deepcopy(final["invalid_evidence_refs"]),
                **scored,
                "completed_expansion_count": session["completed_expansion_count"],
                "selected_execution_group": ({key: deepcopy(event.get(key)) for key in ("execution_group_id", "job_id", "func_stack", "nodes_added", "relationships_added")} if event else None),
                "operation_diagnostic": deepcopy(session["operation_diagnostic"]),
                "call_records": session["call_records"],
                "usage": session["usage"],
                "latency_seconds": session["latency_seconds"],
                "status": "complete",
            }
            record["review_sha256"] = ce.sha256(record)
            ce._write_immutable(path, record)
        direct_reviews[str(trial["trial_id"])] = record
    adaptive = [record for record in direct_reviews.values() if record["controller_trial"]["evidence_mode"] == "llm_adaptive_native"]
    if len(direct_reviews) != 105 or len(adaptive) != 21 or any(record["completed_expansion_count"] != 1 or len(record["call_records"]) != 2 for record in adaptive):
        raise RuntimeError("N22 direct review or Adaptive invariant failed")
    hybrid_reviews = {}
    hybrid_branches = {(record["controller_condition"]["instance_id"], record["controller_condition"]["evidence_mode"]): record for record in package_records}
    for trial in review_design["hybrid_outcome_trials"]:
        path = attempt_root / "reviews" / f"{trial['trial_id']}.json"
        if path.exists():
            record = ce._read_json(path)
            ce._verified_self_hash(record, "review_sha256")
            if record.get("controller_trial") != trial or record.get("status") != "complete":
                raise ValueError("invalid N22 partial hybrid outcome")
        else:
            instance_id = str(trial["instance_id"])
            package_record = hybrid_branches[(instance_id, "shacl_then_llm")]
            report_text = (attempt_root / "shacl" / instance_id / "validation-report.ttl").read_text()
            session = run_hybrid_session(repo_root, attempt_root, package_record["reviewer_package"], diagnoses[instance_id], report_text, str(trial["trial_id"]))
            scored = _score(instances[instance_id], session["fault_detected"], session["suspect_jobs"], session["candidate_functions"])
            record = {
                "schema_version": "n22-hybrid-outcome-record-1",
                "controller_trial": deepcopy(trial),
                "package_sha256": package_record["package_sha256"],
                "shacl_diagnosis_sha256": diagnoses[instance_id]["diagnosis_sha256"],
                "route": deepcopy(session["route"]),
                "receipt": deepcopy(session["receipt"]),
                "invalid_evidence_refs": deepcopy(session["invalid_evidence_refs"]),
                "validated_candidate_functions": deepcopy(session["validated_candidate_functions"]),
                **scored,
                "call_records": session["call_records"],
                "usage": session["usage"],
                "latency_seconds": session["latency_seconds"],
                "status": "complete",
            }
            record["review_sha256"] = ce.sha256(record)
            ce._write_immutable(path, record)
        hybrid_reviews[str(trial["trial_id"])] = record
    if len(hybrid_reviews) != 21:
        raise RuntimeError("N22 hybrid outcome count changed")
    all_reviews = [*direct_reviews.values(), *hybrid_reviews.values()]
    logical_calls = sum(len(record["call_records"]) for record in all_reviews)
    call_ids = [str(call_id) for record in all_reviews for call in record["call_records"] for call_id in call.get("call_ids", [])]
    if not 126 <= logical_calls <= 147 or len(call_ids) != len(set(call_ids)):
        raise ValueError("N22 provider call count or lineage changed")
    for call_id in call_ids:
        verify_record(attempt_root / "ledger", record_type="call-attempt", record_id=call_id)
    analysis = ce._read_json(write_analysis(repo_root, attempt_root, direct_reviews, hybrid_reviews, diagnoses, timings, module_runs, instances))
    deterministic = _replay_formal(attempt_root, diagnoses, module_runs)
    replay = {
        "schema_version": "n22-replay-1",
        "freeze_sha256": verified["freeze_sha256"],
        "review_hashes": sorted(record["review_sha256"] for record in all_reviews),
        "shacl_diagnosis_hashes": {instance_id: diagnosis["diagnosis_sha256"] for instance_id, diagnosis in diagnoses.items()},
        "module_run_hashes": {instance_id: {label: record["module_run_sha256"] for label, record in runs.items()} for instance_id, runs in module_runs.items()},
        "observed_counts": {"conditions": len(package_records), "direct_reviews": len(direct_reviews), "adaptive_follow_ups": sum(record["completed_expansion_count"] for record in adaptive), "shacl_validations": len(diagnoses), "module_runs": sum(len(runs) for runs in module_runs.values()), "hybrid_outcomes": len(hybrid_reviews), "logical_provider_calls": logical_calls, "provider_attempt_call_ids": len(call_ids), "repairs": 0},
        "deterministic_formal_replay": deterministic,
        "all_record_hashes_recomputed": True,
        "duplicate_logical_calls": False,
        "attempt_038_unchanged": ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT)) == SOURCE_TREE_SHA256,
        "attempt_037_unchanged": ce.sha256(ce._tree_hashes(repo_root / SEMANTIC_ATTEMPT)) == SEMANTIC_TREE_SHA256,
    }
    if not replay["attempt_038_unchanged"] or not replay["attempt_037_unchanged"]:
        raise ValueError("N22 source attempt changed during live execution")
    replay["replay_sha256"] = ce.sha256(replay)
    ce._write_immutable(attempt_root / "replay/reconciliation.json", replay)
    terminal = {
        "schema_version": "n22-terminal-1",
        "status": "completed_experiment_and_analysis",
        "condition_instance_count": 49,
        "direct_review_count": 105,
        "shacl_validation_count": 7,
        "module_run_count": 35,
        "hybrid_outcome_count": 21,
        "repair_trace_count": 0,
        "analysis_sha256": analysis["analysis_sha256"],
        "replay_sha256": replay["replay_sha256"],
    }
    terminal["terminal_sha256"] = ce.sha256(terminal)
    path = attempt_root / "terminal-state.json"
    ce._write_immutable(path, terminal)
    _write_report(attempt_root)
    _write_handoff(repo_root, attempt_root)
    return path


def run_lifecycle(repo_root: Path, attempt_root: Path | None = None) -> Path:
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    try:
        return execute_lifecycle(repo_root, target)
    except Exception as exc:
        terminal = {
            "schema_version": "n22-terminal-1",
            "status": "terminal_incomplete",
            "failure_stage": "n22_resumable_lifecycle",
            "error": f"{type(exc).__name__}: {exc}",
            "completed_direct_review_records": len([path for path in (target / "reviews").glob("trial-*.json")]),
            "completed_hybrid_records": len([path for path in (target / "reviews").glob("hybrid-*.json")]),
            "completed_shacl_records": len(list((target / "shacl").rglob("diagnosis.json"))),
            "completed_repair_records": 0,
        }
        terminal["terminal_sha256"] = ce.sha256(terminal)
        path = target / "terminal" / f"terminal-incomplete-{terminal['terminal_sha256'][7:23]}.json"
        ce._write_immutable(path, terminal)
        return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("build", "freeze", "verify", "live"))
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--attempt-root", default=ATTEMPT.as_posix())
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    attempt = Path(args.attempt_root)
    attempt = attempt if attempt.is_absolute() else repo / attempt
    try:
        if args.operation == "build":
            built = build_attempt(repo, attempt)
            print(json.dumps({"qualification": built["qualification"], "counts": {"conditions": len(built["packages"]), "direct_reviews": len(built["schedule"]["direct_review_trials"]), "hybrid_outcomes": len(built["schedule"]["hybrid_outcome_trials"]), "shacl_validations": 7, "module_runs": 35, "repairs": 0}}, indent=2))
        elif args.operation == "freeze":
            print(freeze_attempt(repo, attempt))
        elif args.operation == "verify":
            print(json.dumps(verify_frozen_attempt(repo, attempt), indent=2))
        else:
            path = run_lifecycle(repo, attempt)
            print(path)
            return 0 if ce._read_json(path).get("status") == "completed_experiment_and_analysis" else 1
    except Exception as exc:
        print(f"N22 experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
