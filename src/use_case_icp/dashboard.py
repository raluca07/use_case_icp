from __future__ import annotations

import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .job_store import JobStore


STYLE = """
body{font:14px system-ui,sans-serif;margin:0;background:#f6f8fb;color:#182230}
header{background:#fff;border-bottom:1px solid #d8dee8;padding:16px 24px}main{padding:24px;max-width:1800px;margin:auto}
a{color:#1459b8;text-decoration:none}table{width:100%;border-collapse:collapse;background:#fff}
th,td{text-align:left;padding:10px;border-bottom:1px solid #e4e9f0}.card{background:#fff;border:1px solid #d8dee8;border-radius:8px;padding:16px;margin-bottom:16px}
.badge{display:inline-block;padding:3px 8px;border-radius:12px;background:#e8edf4}.completed{background:#dff5e7}.failed{background:#ffe1e1}.running{background:#fff2c9}
.grid{display:grid;grid-template-columns:260px minmax(500px,1fr) 330px;gap:14px}.scroll{max-height:72vh;overflow:auto}pre{white-space:pre-wrap;word-break:break-word;background:#f5f7fa;padding:10px}
.graph{height:68vh;min-height:520px;background:#fff;border:1px solid #d8dee8;border-radius:8px;overflow:hidden;position:relative}.graph svg{display:block;width:100%;height:100%;touch-action:none;cursor:grab}.graph svg.dragging{cursor:grabbing}
.graph-toolbar{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:0 0 8px}.graph-toolbar button{border:1px solid #aeb8c6;background:#fff;border-radius:6px;padding:6px 10px;cursor:pointer}.graph-toolbar button:hover{background:#eef5ff}
.lineage-node{cursor:pointer}.lineage-node rect{transition:stroke-width .12s,filter .12s}.lineage-node:hover rect,.lineage-node:focus rect{stroke:#1459b8;stroke-width:3;filter:drop-shadow(0 2px 3px #aeb8c6)}.lineage-node.selected rect{stroke:#0b4a9e;stroke-width:4}
.captured-edge{opacity:.35;transition:opacity .12s,stroke-width .12s}.captured-edge.incident{opacity:1;stroke:#1459b8;stroke-width:3}
.lane-label{font-weight:700;fill:#344054}.detail-list{padding-left:18px}.detail-list li{margin:6px 0}.detail-section{border-top:1px solid #e4e9f0;padding-top:10px;margin-top:10px}.detail-section pre{max-height:220px;overflow:auto}
.unit-summary{background:#eef5ff;border:1px solid #b9d2f5;border-radius:7px;padding:10px;margin-bottom:8px}.unit-link small{color:#667085}.unit-link.selected a{font-weight:700}
.trusted{color:#176b38}.suspect{color:#9a6700}.failed-text{color:#b42318}.muted{color:#667085}
.summary{display:flex;gap:8px;flex-wrap:wrap}.metric{background:#f8fafc;border:1px solid #e4e9f0;border-radius:6px;padding:8px 10px}
.legend{display:flex;gap:12px;flex-wrap:wrap;margin:10px 0}.swatch{display:inline-block;width:12px;height:12px;border:1px solid #667085;margin-right:4px;vertical-align:-1px}
.unit-list{list-style:none;padding:0}.unit-list li{padding:8px 4px;border-bottom:1px solid #eef1f5}.unit-list .selected{background:#eef5ff}
input{box-sizing:border-box;width:100%;padding:8px;border:1px solid #cbd3df;border-radius:6px}.notice{border-left:4px solid #1459b8}
.bar{height:10px;background:#d8e7fb;border-radius:5px;min-width:2px}.nowrap{white-space:nowrap}
@media(max-width:950px){.grid{grid-template-columns:1fr}.graph{height:62vh}.scroll{max-height:none}}
"""


def _page(title: str, body: str) -> bytes:
    return (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
        f"<title>{html.escape(title)}</title><style>{STYLE}</style></head><body>"
        f"<header><strong>{html.escape(title)}</strong> · <a href='/'>dashboard</a></header><main>{body}</main></body></html>"
    ).encode("utf-8")


def _status_by_unit(annotations: list[dict]) -> dict[str, str]:
    status: dict[str, str] = {}
    for annotation in annotations:
        status[str(annotation.get("unit_id"))] = str(annotation.get("status"))
    return status


def _graph_svg(
    nodes: list[dict],
    relationships: list[dict],
    units: list[dict],
    statuses: dict[str, str],
    selected_unit_id: str | None = None,
) -> str:
    unit_by_id = {
        str(unit.get("unit_id")): unit
        for unit in units
    }
    owner_by_node: dict[str, str] = {}
    for unit in units:
        for node_ref in unit.get("node_refs", []):
            owner_by_node[str(node_ref)] = str(unit.get("unit_id"))

    def ordinal(node_ref: str) -> int:
        try:
            return int(node_ref.rsplit(":", 1)[-1])
        except ValueError:
            return 0

    owned = [
        (ordinal(node_ref), owner)
        for node_ref, owner in owner_by_node.items()
    ]
    layout_owner_by_node = dict(owner_by_node)
    for node in nodes:
        ref = str(node["node_ref"])
        if ref not in layout_owner_by_node and owned:
            node_ordinal = ordinal(ref)
            layout_owner_by_node[ref] = min(
                owned,
                key=lambda item: abs(item[0] - node_ordinal),
            )[1]

    visible_owner_ids = [
        str(unit.get("unit_id"))
        for unit in units
        if any(
            layout_owner_by_node.get(str(node.get("node_ref")))
            == str(unit.get("unit_id"))
            for node in nodes
        )
    ]
    if not visible_owner_ids:
        visible_owner_ids = [""]
    lane_index = {
        unit_id: index
        for index, unit_id in enumerate(visible_owner_ids)
    }
    positions: dict[str, tuple[int, int]] = {}
    max_rows = 1
    for unit_id in visible_owner_ids:
        lane_nodes = [
            node
            for node in nodes
            if layout_owner_by_node.get(str(node.get("node_ref")), "") == unit_id
        ]
        lane_ordinals = sorted(
            {ordinal(str(node.get("node_ref"))) for node in lane_nodes}
        )
        row_by_ordinal = {
            value: index
            for index, value in enumerate(lane_ordinals)
        }
        max_rows = max(max_rows, len(lane_ordinals))
        for node in lane_nodes:
            ref = str(node["node_ref"])
            function_node = str(node.get("state_type")) == "FunctionMapping"
            x = 25 + lane_index[unit_id] * 470 + (0 if function_node else 225)
            y = 70 + row_by_ordinal[ordinal(ref)] * 78
            positions[ref] = (x, y)
    height = max(540, 100 + max_rows * 78)
    width = max(760, 20 + len(visible_owner_ids) * 470)
    lanes: list[str] = []
    for unit_id in visible_owner_ids:
        index = lane_index[unit_id]
        unit = unit_by_id.get(unit_id, {})
        label = str(unit.get("function_name") or "Captured lineage")
        x = 8 + index * 470
        fill = "#f8fbff" if index % 2 == 0 else "#fbfcfe"
        lanes.append(
            f"<rect x='{x}' y='8' width='454' height='{height - 16}' rx='8' "
            f"fill='{fill}' stroke='#d8dee8' stroke-dasharray='5 4'/>"
            f"<text class='lane-label' x='{x + 14}' y='34' font-size='13'>"
            f"{html.escape(label)}</text>"
            f"<text x='{x + 14}' y='52' font-size='10' fill='#667085'>"
            "function calls → observed artifacts</text>"
        )
    lines: list[str] = []
    for relationship in relationships:
        source = positions.get(str(relationship.get("source_ref")))
        target = positions.get(str(relationship.get("target_ref")))
        if source is None or target is None:
            continue
        x1, y1 = source
        x2, y2 = target
        relationship_ref = html.escape(
            str(relationship.get("relationship_ref") or ""),
            quote=True,
        )
        source_ref = html.escape(str(relationship.get("source_ref")), quote=True)
        target_ref = html.escape(str(relationship.get("target_ref")), quote=True)
        lines.append(
            f"<line class='captured-edge' data-relationship-ref='{relationship_ref}' "
            f"data-source-ref='{source_ref}' data-target-ref='{target_ref}' "
            f"x1='{x1 + 102}' y1='{y1 + 30}' x2='{x2 + 102}' y2='{y2 + 30}' "
            "stroke='#98a2b3' stroke-width='1.5' vector-effect='non-scaling-stroke' "
            "marker-end='url(#arrow)'>"
            f"<title>{html.escape(str(relationship.get('relationship_type')))}</title></line>"
        )
    boxes: list[str] = []
    colors = {
        "trusted_for_reuse": "#dff5e7",
        "trusted_for_reporting": "#e6f0ff",
        "provisionally_trusted": "#fff2c9",
        "failed": "#ffe1e1",
        "suspect": "#fff2c9",
        "invalidated_pending_repair": "#f3e8ff",
    }
    for node in nodes:
        ref = str(node["node_ref"])
        x, y = positions[ref]
        owner = owner_by_node.get(ref, "")
        function_node = str(node.get("state_type")) == "FunctionMapping"
        default_fill = "#eaf2ff" if function_node else "#ffffff"
        fill = colors.get(statuses.get(owner, ""), default_fill)
        label = ", ".join(node.get("names") or [ref.rsplit(":", 1)[-1]])[:29]
        kind = "function call" if function_node else "observed artifact"
        owner_label = str(
            unit_by_id.get(owner, {}).get("function_name")
            or "pipeline hand-off"
        )[:29]
        escaped_ref = html.escape(ref, quote=True)
        selected_class = " selected-unit" if owner == selected_unit_id else ""
        boxes.append(
            f"<g class='lineage-node{selected_class}' data-node-ref='{escaped_ref}' "
            f"tabindex='0' role='button' aria-label='{html.escape(label, quote=True)}'>"
            f"<rect x='{x}' y='{y}' width='205' height='60' rx='7' fill='{fill}' "
            "stroke='#667085' vector-effect='non-scaling-stroke'/>"
            f"<text x='{x + 9}' y='{y + 18}' font-size='12'>{html.escape(label)}</text>"
            f"<text x='{x + 9}' y='{y + 36}' font-size='10' fill='#475467'>{html.escape(kind)}</text>"
            f"<text x='{x + 9}' y='{y + 52}' font-size='9' fill='#667085'>{html.escape(owner_label)}</text>"
            f"<title>{html.escape(ref)}</title></g>"
        )
    return (
        f"<svg id='lineage-svg' viewBox='0 0 {width} {height}' "
        f"data-home-viewbox='0 0 {width} {height}' preserveAspectRatio='xMidYMid meet' "
        "xmlns='http://www.w3.org/2000/svg' aria-label='Captured Etiq lineage'>"
        "<defs><marker id='arrow' markerWidth='8' markerHeight='8' refX='7' refY='4' "
        "orient='auto'><path d='M0,0 L8,4 L0,8 z' fill='context-stroke'/></marker></defs>"
        + "".join(lanes)
        + "".join(lines)
        + "".join(boxes)
        + "</svg>"
    )


def _lineage_interaction_script(payload: dict) -> str:
    encoded = (
        json.dumps(payload, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return (
        f"<script id='lineage-data' type='application/json'>{encoded}</script>"
        """
<script>
const lineageData = JSON.parse(document.getElementById('lineage-data').textContent);
const lineageSvg = document.getElementById('lineage-svg');
const lineageDetails = document.getElementById('lineage-details');
const nodesByRef = new Map(lineageData.nodes.map(node => [String(node.node_ref), node]));
const unitsById = new Map(lineageData.units.map(unit => [String(unit.unit_id), unit]));
const nodeLabel = ref => {
  const node = nodesByRef.get(String(ref));
  return node && node.names && node.names.length ? node.names.join(', ') : String(ref);
};
const element = (tag, text, className) => {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
};
const detailSection = title => {
  const section = element('section', undefined, 'detail-section');
  section.append(element('h4', title));
  lineageDetails.append(section);
  return section;
};
const appendJson = (parent, value) => {
  const pre = element('pre', JSON.stringify(value, null, 2));
  parent.append(pre);
};
function showNodeDetails(ref) {
  const node = nodesByRef.get(String(ref));
  if (!node) return;
  document.querySelectorAll('.lineage-node').forEach(item => item.classList.remove('selected'));
  document.querySelectorAll('.captured-edge').forEach(item => item.classList.remove('incident'));
  const selected = document.querySelector(`.lineage-node[data-node-ref="${CSS.escape(String(ref))}"]`);
  if (selected) selected.classList.add('selected');
  document.querySelectorAll('.captured-edge').forEach(edge => {
    if (edge.dataset.sourceRef === String(ref) || edge.dataset.targetRef === String(ref)) {
      edge.classList.add('incident');
    }
  });

  lineageDetails.replaceChildren();
  lineageDetails.append(element('h3', nodeLabel(ref)));
  lineageDetails.append(element(
    'p',
    node.state_type === 'FunctionMapping' ? 'Captured function invocation' : 'Captured runtime artifact',
    'muted'
  ));
  const identity = detailSection('Captured node');
  identity.append(element('code', String(ref)));
  identity.append(element('p', `Type: ${node.state_type || 'unknown'}${node.value_type ? ` · value: ${node.value_type}` : ''}`));
  identity.append(element('p', `Execution stack: ${(node.func_stack || []).join(' → ') || 'not recorded'}`));

  const memberships = lineageData.units.filter(unit => (unit.node_refs || []).includes(String(ref)));
  const unitSection = detailSection('Derived review-unit membership');
  if (!memberships.length) {
    unitSection.append(element('p', 'Pipeline hand-off node; it is incident to a unit boundary but is not owned by a review unit.'));
  } else {
    const list = element('ul', undefined, 'detail-list');
    memberships.forEach(unit => {
      const status = lineageData.statuses[String(unit.unit_id)] || 'unreviewed';
      list.append(element('li', `${unit.function_name} · ${status}`));
    });
    unitSection.append(list);
  }

  const incident = lineageData.relationships.filter(
    relationship => String(relationship.source_ref) === String(ref) || String(relationship.target_ref) === String(ref)
  );
  const relationshipSection = detailSection(`Captured relationships (${incident.length})`);
  if (!incident.length) {
    relationshipSection.append(element('p', 'No captured relationship is incident to this node.'));
  } else {
    const list = element('ul', undefined, 'detail-list');
    incident.forEach(relationship => {
      const outgoing = String(relationship.source_ref) === String(ref);
      const otherRef = outgoing ? relationship.target_ref : relationship.source_ref;
      const item = element(
        'li',
        `${outgoing ? 'outgoing' : 'incoming'} ${relationship.relationship_type} ${outgoing ? '→' : '←'} ${nodeLabel(otherRef)}`
      );
      item.append(element('br'));
      item.append(element('code', String(relationship.relationship_ref || 'relationship ref unavailable')));
      list.append(item);
    });
    relationshipSection.append(list);
  }

  const membershipIds = new Set(memberships.map(unit => String(unit.unit_id)));
  const relatedAnnotations = lineageData.annotations.filter(annotation => {
    const direct = (annotation.evidence_refs || []).map(String).includes(String(ref));
    return direct || membershipIds.has(String(annotation.unit_id));
  });
  const annotationSection = detailSection(`Derived annotations (${relatedAnnotations.length})`);
  if (!relatedAnnotations.length) {
    annotationSection.append(element('p', 'No valid derived annotation is tied to this node or its review unit in this run.'));
  } else {
    relatedAnnotations.forEach(annotation => {
      const direct = (annotation.evidence_refs || []).map(String).includes(String(ref));
      const unit = unitsById.get(String(annotation.unit_id));
      const item = element('div', undefined, 'card');
      item.append(element('strong', `${annotation.status} · ${unit ? unit.function_name : annotation.unit_id}`));
      item.append(element('p', direct ? 'Direct evidence reference to this node.' : 'Unit-level annotation applied through review-unit membership.'));
      item.append(element('code', String(annotation.annotation_id)));
      annotationSection.append(item);
    });
  }

  const previewSection = detailSection('Stored value preview');
  if (node.value_preview === null || node.value_preview === undefined) {
    previewSection.append(element('p', 'No value preview was stored for this node.'));
  } else {
    appendJson(previewSection, node.value_preview);
    if (node.preview_truncated) previewSection.append(element('p', 'Preview is bounded and truncated.', 'muted'));
  }
}
document.querySelectorAll('.lineage-node').forEach(node => {
  node.addEventListener('click', event => {
    event.stopPropagation();
    showNodeDetails(node.dataset.nodeRef);
  });
  node.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      showNodeDetails(node.dataset.nodeRef);
    }
  });
});

const homeView = lineageSvg.dataset.homeViewbox.split(' ').map(Number);
let view = [...homeView];
const applyView = () => lineageSvg.setAttribute('viewBox', view.join(' '));
const zoom = factor => {
  const centerX = view[0] + view[2] / 2;
  const centerY = view[1] + view[3] / 2;
  view[2] *= factor;
  view[3] *= factor;
  view[0] = centerX - view[2] / 2;
  view[1] = centerY - view[3] / 2;
  applyView();
};
document.getElementById('graph-fit').addEventListener('click', () => {
  view = [...homeView];
  applyView();
});
document.getElementById('graph-zoom-in').addEventListener('click', () => zoom(0.75));
document.getElementById('graph-zoom-out').addEventListener('click', () => zoom(1.33));
lineageSvg.addEventListener('wheel', event => {
  event.preventDefault();
  zoom(event.deltaY < 0 ? 0.88 : 1.14);
}, {passive: false});
let drag = null;
lineageSvg.addEventListener('pointerdown', event => {
  if (event.target.closest('.lineage-node')) return;
  drag = {x: event.clientX, y: event.clientY, view: [...view]};
  lineageSvg.classList.add('dragging');
  lineageSvg.setPointerCapture(event.pointerId);
});
lineageSvg.addEventListener('pointermove', event => {
  if (!drag) return;
  const rect = lineageSvg.getBoundingClientRect();
  view[0] = drag.view[0] - (event.clientX - drag.x) * drag.view[2] / rect.width;
  view[1] = drag.view[1] - (event.clientY - drag.y) * drag.view[3] / rect.height;
  applyView();
});
const stopDrag = () => {
  drag = null;
  lineageSvg.classList.remove('dragging');
};
lineageSvg.addEventListener('pointerup', stopDrag);
lineageSvg.addEventListener('pointercancel', stopDrag);
</script>
"""
    )


def experiment_page_body(
    job_id: str,
    experiment_id: str,
    result: dict,
) -> str:
    summary = result.get("summary", {})
    arms = summary.get("arms", {})
    max_chars = max(
        (int(arm.get("average_package_chars") or 0) for arm in arms.values()),
        default=1,
    )
    rows = []
    for key, arm in sorted(arms.items()):
        package_chars = int(arm.get("average_package_chars") or 0)
        width = max(1, round(100 * package_chars / max_chars))
        core_recall = arm.get("verified_core_recall")
        precision = arm.get("verified_issue_precision")
        node_count = arm.get("average_etiq_node_count")
        history_count = arm.get("average_history_artifact_count")
        secondary = arm.get("secondary_findings", [])
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(arm.get('run_label')))}</td>"
            f"<td><code>{html.escape(str(arm.get('mode')))}</code></td>"
            f"<td class='nowrap'>{package_chars:,}<div class='bar' style='width:{width}%'></div></td>"
            f"<td>{html.escape(str(arm.get('average_input_tokens') or '—'))}</td>"
            f"<td>{html.escape('—' if node_count is None else str(node_count))}</td>"
            f"<td>{html.escape('—' if history_count is None else str(history_count))}</td>"
            f"<td>{html.escape(str(arm.get('issue_count') or 0))}</td>"
            f"<td>{html.escape('—' if core_recall is None else f'{arm.get('verified_core_issue_count', 0)}/{len(summary.get('verified_core_issue_keys', []))} ({100 * float(core_recall):.0f}%)')}</td>"
            f"<td>{html.escape('—' if precision is None else f'{100 * float(precision):.0f}%')}</td>"
            f"<td>{html.escape(str(arm.get('misattributed_issue_count', '—')))}</td>"
            f"<td>{html.escape(str(arm.get('false_positive_issue_count', '—')))}</td>"
            f"<td>{html.escape(', '.join(str(item) for item in secondary) or '—')}</td>"
            "</tr>"
        )
    assessment = result.get("issue_assessment", {})
    core_descriptions = assessment.get("core_issue_descriptions", {})
    core_issues = summary.get("verified_core_issue_keys", [])
    core_block = "".join(
        "<li><code>"
        f"{html.escape(str(issue))}</code>"
        + (
            f" — {html.escape(str(core_descriptions[issue]))}"
            if issue in core_descriptions
            else ""
        )
        + "</li>"
        for issue in core_issues
    )
    consensus_blocks = "".join(
        f"<h4>{html.escape(run_label)}</h4>"
        "<p><strong>All-arm consensus:</strong> "
        + html.escape(
            ", ".join(values.get("consensus_core_issue_keys", [])) or "none"
        )
        + "<br><strong>Disputed attribution:</strong> "
        + html.escape(", ".join(values.get("disputed_issue_keys", [])) or "none")
        + "</p>"
        for run_label, values in sorted(
            summary.get("consensus_by_run", {}).items()
        )
    )
    control_findings = assessment.get("control_plane_findings", {})
    control_block = ""
    if control_findings:
        control_block = (
            "<div class='card'><h3>Control-plane review quality</h3>"
            f"<p>Workflow-review false positives: <strong>{html.escape(str(control_findings.get('false_positive_count', 0)))}</strong>"
            f" ({html.escape(', '.join(control_findings.get('false_positive_issue_keys', [])) or 'none')}). "
            f"Valid receipts: <strong>{html.escape(str(control_findings.get('valid_receipts', '—')))}</strong> / "
            f"{html.escape(str(control_findings.get('total_receipts', '—')))}.</p>"
            f"<p class='muted'>{html.escape(str(control_findings.get('note', '')))}</p></div>"
        )
    resolved = summary.get("resolved_issue_keys", {})
    resolved_blocks = "".join(
        f"<h4>{html.escape(mode)}</h4><ul>"
        + "".join(f"<li>{html.escape(str(issue))}</li>" for issue in issues)
        + ("<li>None recorded</li>" if not issues else "")
        + "</ul>"
        for mode, issues in sorted(resolved.items())
    )
    artifact = f"experiments/{experiment_id}/result.json"
    status = "executed" if result.get("execute") else "planned only — no Codex tokens spent"
    return (
        f"<div class='card'><h2>Review-context comparison</h2>"
        f"<p><span class='badge'>{html.escape(status)}</span></p>"
        f"<p>Experiment <code>{html.escape(experiment_id)}</code> · model "
        f"<code>{html.escape(str(result.get('model')))}</code> · repetitions "
        f"{html.escape(str(result.get('repetitions')))}</p>"
        f"<p><a href='/jobs/{html.escape(job_id)}/experiments'>all comparisons</a> · "
        f"<a href='/jobs/{html.escape(job_id)}/artifact?path={html.escape(artifact)}'>result JSON</a></p></div>"
        "<div class='card notice'><h3>Controlled variable</h3>"
        "<p>All arms use the same immutable runtime input and result, source, assigned units, model, prompt contract, and schema. "
        "<code>semantic_only</code> omits Etiq nodes and edges; <code>history_full</code> adds accumulated non-Etiq job artifacts; "
        "<code>etiq_full</code> supplies all captured nodes and edges; "
        "<code>etiq_selected</code> supplies the graph-selected subset.</p>"
        "<p><strong>Node means an Etiq-captured runtime state or function invocation.</strong> "
        "It is not a document, text chunk, or token. The two non-Etiq modes therefore have zero graph nodes by design; "
        "compare their package characters and actual input tokens instead. Node count is relevant within the Etiq arms because "
        "it shows how much execution evidence graph selection retained.</p>"
        "<p>Package construction is deterministic. Codex decisions and token usage are measured outputs and are not assumed deterministic.</p></div>"
        + (
            "<div class='card'><h3>Verified issue assessment</h3>"
            f"<p>{html.escape(str(assessment.get('basis', 'Manual source and runtime assessment.')))}</p>"
            f"<ul>{core_block}</ul>{consensus_blocks}</div>"
            if core_issues
            else (
                "<div class='card notice'><h3>Issue interpretation</h3>"
                "<p>Consensus and disputed paths are shown, but no source-verified assessment has been attached. "
                "Do not treat one comparison arm as ground truth.</p>"
                f"{consensus_blocks}</div>"
            )
        )
        + "<div class='card'><h3>Cost and issue quality</h3><table>"
        "<tr><th>Run</th><th>Mode</th><th>Average package chars</th><th>Average input tokens</th>"
        "<th>Etiq nodes</th><th>History artifacts</th>"
        "<th>Raw paths</th><th>Verified core recall</th><th>Verified precision</th>"
        "<th>Misattributed</th><th>False positive</th><th>Useful secondary detail</th></tr>"
        f"{''.join(rows)}</table></div>{control_block}"
        f"<div class='card'><h3>Issues absent after repair</h3>{resolved_blocks or '<p>Execute both runs to calculate this.</p>'}</div>"
    )


class DashboardHandler(BaseHTTPRequestHandler):
    store: JobStore

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        try:
            if parsed.path == "/":
                self._dashboard()
            elif parsed.path == "/api/jobs":
                self._api_jobs()
            elif len(parts) == 2 and parts[0] == "jobs":
                self._job(parts[1])
            elif len(parts) == 3 and parts[0] == "jobs" and parts[2] == "lineage":
                query = parse_qs(parsed.query)
                self._lineage(
                    parts[1],
                    query.get("run", [None])[0],
                    query.get("unit", [None])[0],
                )
            elif (
                len(parts) == 3
                and parts[0] == "jobs"
                and parts[2] == "controlled-experiments"
            ):
                self._controlled_experiments(parts[1])
            elif (
                len(parts) == 4
                and parts[0] == "jobs"
                and parts[2] == "controlled-experiments"
            ):
                self._controlled_experiment(parts[1], parts[3])
            elif len(parts) == 3 and parts[0] == "jobs" and parts[2] == "artifact":
                self._artifact(parts[1], parse_qs(parsed.query).get("path", [""])[0])
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, FileNotFoundError) as exc:
            self.send_error(HTTPStatus.NOT_FOUND, str(exc))

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, payload: bytes, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _jobs(self) -> list[tuple[str, dict]]:
        jobs: list[tuple[str, dict]] = []
        for path in sorted(self.store.output_root.iterdir(), reverse=True):
            if path.is_dir():
                jobs.append((path.name, self.store.read_json(path / "state.json", {})))
        return jobs

    def _dashboard(self) -> None:
        rows = []
        for job_id, state in self._jobs():
            status = str(state.get("status") or "unknown")
            rows.append(
                "<tr>"
                f"<td><a href='/jobs/{html.escape(job_id)}'>{html.escape(job_id)}</a></td>"
                f"<td><span class='badge {html.escape(status)}'>{html.escape(status)}</span></td>"
                f"<td>{html.escape(str(state.get('active_segment_id') or '—'))}</td>"
                f"<td>{html.escape(str(state.get('authoring_retry_count') or 0))}</td>"
                f"<td>{html.escape(str(state.get('repair_count') or 0))}</td>"
                "</tr>"
            )
        body = "<div class='card'><table><thead><tr><th>Job</th><th>Status</th><th>Active segment</th><th>Authoring retries</th><th>Repairs</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
        self._send(_page("Use-Case and ICP Agent", body))

    def _api_jobs(self) -> None:
        payload = json.dumps([{"job_id": job_id, **state} for job_id, state in self._jobs()]).encode()
        self._send(payload, "application/json")

    def _job(self, job_id: str) -> None:
        root = self.store.job_dir(job_id)
        if not root.exists():
            raise FileNotFoundError(job_id)
        state = self.store.read_json(root / "state.json", {})
        request = self.store.read_json(root / "request.json", {})
        segments = self.store.read_json(root / "segments.json", {})
        usage = self.store.read_json(root / "usage-summary.json", {"totals": {}})
        repair_metric_files = sorted(root.glob("stages/*/*/repair-metrics.json"))
        repair_metrics = [
            self.store.read_json(path, {})
            for path in repair_metric_files
        ]
        events = self.store.read_events(job_id)[-50:]
        runs = sorted(root.glob("stages/*/*/runs/*"), key=lambda item: item.stat().st_mtime, reverse=True)
        lineage_link = f"<a href='/jobs/{job_id}/lineage'>latest lineage</a>" if runs else "no lineage yet"
        experiment_link = (
            f"<a href='/jobs/{job_id}/controlled-experiments'>controlled comparisons</a>"
            if (root / "controlled-experiments").exists()
            else "no controlled comparisons"
        )
        event_rows = "".join(
            f"<tr><td>{html.escape(str(item.get('sequence')))}</td><td>{html.escape(str(item.get('event_type')))}</td><td>{html.escape(str(item.get('summary')))}</td></tr>"
            for item in events
        )
        repair_rows = "".join(
            "<tr>"
            f"<td>{html.escape(str(attempt.get('attempt')))}</td>"
            f"<td>{html.escape(str(attempt.get('target_function')))}</td>"
            f"<td>{html.escape(str(attempt.get('status')))}</td>"
            f"<td>{html.escape(str(attempt.get('source_run_id')))}</td>"
            f"<td>{html.escape(str(attempt.get('result_run_id') or '—'))}</td>"
            "</tr>"
            for metric in repair_metrics
            for attempt in metric.get("attempts", [])
        )
        accepted_repairs = (
            sum(
                int(metric.get("accepted_repair_count") or 0)
                for metric in repair_metrics
            )
            if repair_metrics
            else int(state.get("repair_count") or 0)
        )
        evaluated_repairs = sum(
            int(metric.get("evaluated_repair_count") or 0)
            for metric in repair_metrics
        )
        effective_repairs = sum(
            int(metric.get("effective_repair_count") or 0)
            for metric in repair_metrics
        )
        effectiveness = (
            f"{100 * effective_repairs / evaluated_repairs:.1f}%"
            if evaluated_repairs
            else "—"
        )
        body = (
            f"<div class='card'><h2>{html.escape(job_id)}</h2><p>Status: <span class='badge {html.escape(str(state.get('status')))}'>{html.escape(str(state.get('status')))}</span> · {lineage_link} · {experiment_link}</p>"
            f"<p>Tokens: input {usage.get('totals', {}).get('input_tokens', 0)}, output {usage.get('totals', {}).get('output_tokens', 0)}"
            f" · complete: {html.escape(str(usage.get('complete', False)))}</p></div>"
            "<div class='card'><h3>Repair effectiveness</h3>"
            f"<div class='summary'><span class='metric'><strong>{accepted_repairs}</strong> accepted</span>"
            f"<span class='metric'><strong>{evaluated_repairs}</strong> evaluated</span>"
            f"<span class='metric'><strong>{effective_repairs}</strong> target resolved</span>"
            f"<span class='metric'><strong>{effectiveness}</strong> effectiveness</span></div>"
            "<p class='muted'>Effective means the targeted function was no longer failed or suspect after rerun; it does not require the whole stage to pass.</p>"
            "<table><tr><th>Attempt</th><th>Boundary</th><th>Outcome</th><th>Source run</th><th>Result run</th></tr>"
            f"{repair_rows or '<tr><td colspan=5>No repairs yet</td></tr>'}</table></div>"
            f"<div class='card'><h3>Request</h3><pre>{html.escape(json.dumps(request, indent=2))}</pre></div>"
            f"<div class='card'><h3>Segments</h3><pre>{html.escape(json.dumps(segments, indent=2))}</pre></div>"
            f"<div class='card'><h3>Events</h3><table><tr><th>#</th><th>Type</th><th>Summary</th></tr>{event_rows}</table></div>"
        )
        self._send(_page(f"Job {job_id}", body))

    def _controlled_experiments(self, job_id: str) -> None:
        root = self.store.job_dir(job_id) / "controlled-experiments"
        rows = []
        if root.exists():
            for path in sorted(root.iterdir(), reverse=True):
                result = self.store.read_json(path / "result.json", {})
                arms = result.get("arms", []) if isinstance(result, dict) else []
                trusted = sum(bool(arm.get("judge_trusted")) for arm in arms)
                rows.append(
                    "<tr>"
                    f"<td><a href='/jobs/{html.escape(job_id)}/controlled-experiments/{html.escape(path.name)}'>{html.escape(path.name)}</a></td>"
                    f"<td>{len(arms)}</td><td>{trusted}</td>"
                    f"<td>{html.escape(str(result.get('cassette_hash', 'running')))}</td>"
                    "</tr>"
                )
        self._send(
            _page(
                "Controlled repair comparisons",
                f"<div class='card'><h2>Controlled repair comparisons</h2>"
                f"<p><a href='/jobs/{html.escape(job_id)}'>back to job</a></p>"
                "<table><tr><th>Experiment</th><th>Arms</th>"
                "<th>Blind-judge trusted</th><th>Frozen cassette</th></tr>"
                f"{''.join(rows) or '<tr><td colspan=4>No controlled comparisons yet</td></tr>'}"
                "</table></div>",
            ),
        )

    def _controlled_experiment(self, job_id: str, experiment_id: str) -> None:
        if not experiment_id or "/" in experiment_id or ".." in experiment_id:
            raise FileNotFoundError(experiment_id)
        result = self.store.read_json(
            self.store.job_dir(job_id)
            / "controlled-experiments"
            / experiment_id
            / "result.json"
        )
        if not isinstance(result, dict):
            raise FileNotFoundError(experiment_id)
        rows = []
        for arm in result.get("arms", []):
            input_tokens = arm.get("input_tokens")
            cached_tokens = arm.get("cached_input_tokens")
            duration = arm.get("duration_seconds")
            targets = [
                str(repair.get("target_function"))
                for repair in arm.get("repairs", [])
            ]
            rows.append(
                "<tr>"
                f"<td><code>{html.escape(str(arm.get('mode')))}</code></td>"
                f"<td>{html.escape(str(arm.get('status', 'running')))}</td>"
                f"<td>{len(arm.get('repairs', []))}</td>"
                f"<td>{int(arm.get('effective_repair_count') or 0)}/{int(arm.get('evaluated_repair_count') or len(arm.get('repairs', [])))}</td>"
                f"<td>{html.escape(' → '.join(targets) or 'none')}</td>"
                f"<td>{html.escape(str(arm.get('judge_trusted')))}</td>"
                f"<td>{html.escape(', '.join(arm.get('judge_issue_keys', [])) or 'none')}</td>"
                f"<td>{f'{int(input_tokens):,}' if input_tokens is not None else '—'}</td>"
                f"<td>{f'{int(cached_tokens):,}' if cached_tokens is not None else '—'}</td>"
                f"<td>{f'{float(duration):,.1f}s' if duration is not None else '—'}</td>"
                f"<td>{html.escape(str(arm.get('error') or '—'))}</td>"
                "</tr>"
            )
        isolation = result.get("isolation", {})
        self._send(
            _page(
                f"Controlled comparison {experiment_id}",
                f"<div class='card'><h2>Controlled repair comparison</h2>"
                f"<p><a href='/jobs/{html.escape(job_id)}/controlled-experiments'>all controlled comparisons</a></p>"
                f"<p>Frozen run: <code>{html.escape(str(result.get('frozen_run_id')))}</code> · "
                f"cassette: <code>{html.escape(str(result.get('cassette_hash')))}</code></p>"
                "<p class='muted'>Every invocation is an ephemeral session. Branch history is isolated; "
                "network responses are recorded once and replayed; final outcomes use the same fresh blind "
                "graph-selected judge with on-demand expansion. Token values are reported by Codex, not estimated.</p>"
                "<table><tr><th>Arm</th><th>Status</th><th>Repairs</th><th>Effective</th><th>Repair targets</th><th>Blind trusted</th>"
                "<th>Blind-judge issues</th><th>Input tokens</th><th>Cached input</th>"
                f"<th>Time</th><th>Error</th></tr>{''.join(rows)}</table>"
                "<p class='muted'>Repairs are accepted scoped code changes that were re-executed against the frozen corpus. "
                "Blind-judge issues are the unresolved function boundaries in the final replay, so fewer is better.</p>"
                f"<details><summary>Isolation receipt</summary><pre>{html.escape(json.dumps(isolation, indent=2))}</pre></details>"
                "</div>",
            ),
        )

    def _latest_run(self, root: Path, run: str | None) -> Path:
        candidates = [path for path in root.glob("stages/*/*/runs/*") if not run or path.name == run]
        if not candidates:
            raise FileNotFoundError("run not found")
        return max(candidates, key=lambda item: item.stat().st_mtime)

    def _lineage(self, job_id: str, run: str | None, selected_unit_id: str | None) -> None:
        root = self.store.job_dir(job_id)
        run_dir = self._latest_run(root, run)
        nodes = self.store.read_json(run_dir / "etiq-nodes.json", [])
        relationships = self.store.read_json(run_dir / "etiq-relationships.json", [])
        units = self.store.read_json(run_dir / "review-boundaries.json", [])
        annotations = [
            annotation
            for annotation in self.store.read_trust_annotations(job_id)
            if str(annotation.get("run_id")) == run_dir.name
        ]
        statuses = _status_by_unit(annotations)
        frontier = self.store.read_json(
            run_dir / "trusted-frontier.json",
            {"frontier_unit_ids": [], "trusted_unit_ids": []},
        )
        context_accounting = self.store.read_json(
            run_dir / "context-accounting.json",
            [],
        )
        runs = sorted(
            root.glob("stages/*/*/runs/*"),
            key=lambda item: item.stat().st_mtime,
        )
        run_links = " · ".join(
            (
                f"<strong>{html.escape(item.name)}</strong>"
                if item == run_dir
                else f"<a href='/jobs/{html.escape(job_id)}/lineage?run={html.escape(item.name)}'>"
                f"{html.escape(item.name)}</a>"
            )
            for item in runs
        )
        unit_links = "".join(
            f"<li data-unit='{html.escape(str(item.get('function_name')).lower())}'"
            f" class='unit-link {'selected' if item.get('unit_id') == selected_unit_id else ''}'>"
            f"<a href='/jobs/{html.escape(job_id)}/lineage?run={html.escape(run_dir.name)}"
            f"&unit={html.escape(str(item.get('unit_id')))}'>{html.escape(str(item.get('function_name')))}</a>"
            f"<br><small>{html.escape(statuses.get(str(item.get('unit_id')), 'unreviewed'))}"
            f" · {len(item.get('node_refs', []))} nodes · "
            f"{len(item.get('relationship_refs', []))} edges</small></li>"
            for item in units
        )
        selected_unit = next(
            (item for item in units if item.get("unit_id") == selected_unit_id),
            None,
        )
        if selected_unit is not None:
            relationship_refs = set(selected_unit.get("relationship_refs", []))
            shown_relationships = [
                item
                for item in relationships
                if item.get("relationship_ref") in relationship_refs
            ]
            shown_node_refs = set(selected_unit.get("node_refs", []))
            for relationship in shown_relationships:
                shown_node_refs.add(relationship.get("source_ref"))
                shown_node_refs.add(relationship.get("target_ref"))
            shown_nodes = [item for item in nodes if item.get("node_ref") in shown_node_refs]
        else:
            shown_nodes = nodes
            shown_refs = {item.get("node_ref") for item in shown_nodes}
            shown_relationships = [
                item
                for item in relationships
                if item.get("source_ref") in shown_refs and item.get("target_ref") in shown_refs
            ]
        graph = _graph_svg(
            shown_nodes,
            shown_relationships,
            units,
            statuses,
            selected_unit_id,
        )
        accounting_rows = "".join(
            "<tr>"
            f"<td>{html.escape(str(item.get('section_id')))}</td>"
            f"<td>{html.escape(str(item.get('selected_node_count')))} / {html.escape(str(item.get('available_node_count')))}</td>"
            f"<td>{html.escape(str(item.get('selected_relationship_count')))} / {html.escape(str(item.get('available_relationship_count')))}</td>"
            f"<td>{html.escape(str(round(100 * float(item.get('selected_to_available_ratio') or 0), 1)))}%</td>"
            f"<td>{html.escape(str(item.get('reported_input_tokens') or '—'))}</td>"
            "</tr>"
            for item in context_accounting
        )
        artifact_root = run_dir.relative_to(root)
        artifact_links = " · ".join(
            f"<a href='/jobs/{html.escape(job_id)}/artifact?path={html.escape(str(artifact_root / name))}'>{html.escape(label)}</a>"
            for name, label in (
                ("etiq-nodes.json", "nodes JSON"),
                ("etiq-relationships.json", "relationships JSON"),
                ("review-boundaries.json", "review units"),
                ("trusted-frontier.json", "trusted frontier"),
                ("context-accounting.json", "context accounting"),
            )
            if (run_dir / name).exists()
        )
        comparison_link = (
            f"<a href='/jobs/{html.escape(job_id)}/controlled-experiments'>controlled repair comparisons</a>"
            if (root / "controlled-experiments").exists()
            else ""
        )
        unit_by_id = {
            str(item.get("unit_id")): item
            for item in units
        }
        if selected_unit is not None:
            upstream = [
                str(unit_by_id.get(str(unit_id), {}).get("function_name") or unit_id)
                for unit_id in selected_unit.get("upstream_unit_ids", [])
            ]
            downstream = [
                str(unit_by_id.get(str(unit_id), {}).get("function_name") or unit_id)
                for unit_id in selected_unit.get("downstream_unit_ids", [])
            ]
            unit_summary = (
                "<div class='unit-summary'><strong>Selected review unit: "
                f"{html.escape(str(selected_unit.get('function_name')))}</strong>"
                f"<p>Derived from captured stack <code>{html.escape(' → '.join(selected_unit.get('func_stack_prefix') or []))}</code>. "
                f"It owns {len(selected_unit.get('node_refs', []))} nodes and "
                f"{len(selected_unit.get('relationship_refs', []))} captured relationships. "
                f"Upstream: {html.escape(', '.join(upstream) or 'none')}; "
                f"downstream: {html.escape(', '.join(downstream) or 'none')}.</p>"
                "<p>Only this unit and its boundary hand-offs are shown. Click a box for its exact relationships, "
                "review-unit membership, derived annotations, and value preview.</p></div>"
            )
        else:
            unit_summary = (
                "<div class='unit-summary'><strong>Complete stored lineage</strong>"
                f"<p>All {len(nodes)} captured nodes and {len(relationships)} captured relationships are shown. "
                "The dashed lanes are derived review units; the third line inside each box names its unit. "
                "Click a review unit to isolate it, or click a box to inspect only evidence tied to that node.</p></div>"
            )
        annotation_notice = (
            "<div class='card notice'><strong>No valid derived annotations exist for this run.</strong> "
            "All boxes are therefore shown as unreviewed. This is recorded state, not missing lineage: "
            "the workflow review receipts were rejected by validation, so no trust annotation was promoted.</div>"
            if not annotations
            else ""
        )
        lineage_payload = {
            "nodes": [
                {
                    key: node.get(key)
                    for key in (
                        "node_ref",
                        "names",
                        "state_type",
                        "value_type",
                        "func_stack",
                        "value_preview",
                        "preview_truncated",
                    )
                }
                for node in shown_nodes
            ],
            "relationships": shown_relationships,
            "units": units,
            "annotations": annotations,
            "statuses": statuses,
        }
        interaction_script = _lineage_interaction_script(lineage_payload)
        overview_text = (
            f"Complete overview: {len(shown_nodes)} nodes and {len(shown_relationships)} captured relationships."
            if selected_unit is None
            else (
                f"Filtered review-unit view: {len(shown_nodes)} nodes and "
                f"{len(shown_relationships)} captured relationships."
            )
        )
        body = (
            f"<div class='card'><h2>Run {html.escape(run_dir.name)}</h2>"
            f"<p>Runs: {run_links}</p><div class='summary'>"
            f"<span class='metric'><strong>{len(nodes)}</strong> captured nodes</span>"
            f"<span class='metric'><strong>{len(relationships)}</strong> captured relationships</span>"
            f"<span class='metric'><strong>{len(units)}</strong> derived review units</span>"
            f"<span class='metric'><strong>{len(frontier.get('frontier_unit_ids', []))}</strong> frontier units</span>"
            f"<span class='metric'><strong>{len(shown_nodes)}</strong> nodes visible</span>"
            f"</div><p>{artifact_links}"
            f"{' · ' + comparison_link if comparison_link else ''}</p></div>"
            "<div class='card notice'><h3>What is deterministic?</h3>"
            "<p><strong>Captured nodes and edges:</strong> direct Etiq observations and immutable once this run is stored. "
            "A fresh execution may differ when runtime inputs or external sources differ.</p>"
            "<p><strong>Review-unit selection, sections, filtering, and layout:</strong> deterministic functions of this stored snapshot and its limits.</p>"
            "<p><strong>Trust, suspect, and failure labels:</strong> Codex review judgments. They are persisted and auditable, but model output is not assumed deterministic.</p>"
            "<p><strong>Edges shown below are captured Etiq edges.</strong> Review membership and trust colors are overlays, not inferred execution edges.</p></div>"
            "<div class='card notice'><h3>How the layers connect</h3><div class='summary'>"
            "<span class='metric'><strong>1. Review unit</strong><br>Derived from a captured function-stack boundary.</span>"
            "<span class='metric'><strong>→ 2. Lineage boxes</strong><br>Function invocations and observed artifacts owned by that unit.</span>"
            "<span class='metric'><strong>→ 3. Captured relationships</strong><br>Etiq input, output, and parent edges between boxes.</span>"
            "<span class='metric'><strong>→ 4. Derived annotations</strong><br>Validated review judgments tied to a unit and evidence references.</span>"
            "</div><p>Unit selection filters the lineage. Box selection highlights incident captured edges and reveals only "
            "the relationships and annotations tied to that box or its owning review unit.</p></div>"
            f"{annotation_notice}"
            "<div class='card'><h3>Review context</h3><table><tr><th>Section</th><th>Nodes</th><th>Relationships</th><th>Selected package</th><th>Actual input tokens</th></tr>"
            f"{accounting_rows or '<tr><td colspan=5>Not reviewed yet</td></tr>'}</table></div>"
            "<div class='legend'>"
            "<span><i class='swatch' style='background:#eaf2ff'></i>function invocation</span>"
            "<span><i class='swatch' style='background:#fff'></i>observed artifact</span>"
            "<span><i class='swatch' style='background:#dff5e7'></i>trusted for reuse</span>"
            "<span><i class='swatch' style='background:#fff2c9'></i>suspect/provisional</span>"
            "<span><i class='swatch' style='background:#ffe1e1'></i>failed</span>"
            "<span><i class='swatch' style='background:#fff'></i>unreviewed trust state</span>"
            "</div>"
            "<div class='grid'>"
            f"<aside class='card scroll'><h3>Review units</h3>"
            f"<p><a href='/jobs/{html.escape(job_id)}/lineage?run={html.escape(run_dir.name)}'>show complete lineage</a></p>"
            "<input id='unit-filter' placeholder='Filter function names' oninput=\""
            "for(const x of document.querySelectorAll('.unit-list li'))"
            "{x.style.display=x.dataset.unit.includes(this.value.toLowerCase())?'':'none'}\">"
            f"<ul class='unit-list'>{unit_links}</ul></aside>"
            f"<section>{unit_summary}<div class='graph-toolbar'>"
            "<button id='graph-fit' type='button'>Fit complete graph</button>"
            "<button id='graph-zoom-in' type='button'>Zoom in</button>"
            "<button id='graph-zoom-out' type='button'>Zoom out</button>"
            f"<span class='muted'>{html.escape(overview_text)} Drag to pan; use the wheel to zoom.</span>"
            f"</div><div class='graph'>{graph}</div></section>"
            "<aside class='card scroll'><div id='lineage-details'><h3>Node evidence</h3>"
            "<p>Click a lineage box to inspect it.</p>"
            "<p class='muted'>Captured relationships, derived annotations, review-unit membership, and value previews "
            "remain hidden until a box is selected.</p></div></aside>"
            f"</div>{interaction_script}"
        )
        self._send(_page(f"Lineage {run_dir.name}", body))

    def _artifact(self, job_id: str, relative: str) -> None:
        root = self.store.job_dir(job_id).resolve()
        target = (root / relative).resolve()
        if root not in target.parents or not target.is_file():
            raise FileNotFoundError(relative)
        self._send(target.read_bytes(), "application/json" if target.suffix in {".json", ".jsonl"} else "text/plain")


def serve(store: JobStore, host: str = "127.0.0.1", port: int = 8000) -> None:
    handler = type("ConfiguredDashboardHandler", (DashboardHandler,), {"store": store})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Dashboard: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
