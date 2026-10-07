"""Independent controller-only oracle for the Attempt-055 workload."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json


def _decimal(value):
    return Decimal(str(value))


def _quantize(value, places):
    return value.quantize(Decimal("1").scaleb(-places), rounding=ROUND_HALF_EVEN)


def compute_clean_result(root):
    policy = root["planning_policy"]
    snapshot = date.fromisoformat(policy["as_of_date"])
    usable = [
        dict(row) for row in root["market_observations"]
        if date.fromisoformat(row["effective_date"]) <= snapshot
        and date.fromisoformat(row["recorded_at"][:10]) <= snapshot
        and date.fromisoformat(row["valid_until"]) >= snapshot
    ]
    configured_basis = root["repeat_resolution_policy"]["basis"]
    survivors = {}
    for row in usable:
        key = (row["opportunity_id"], row["source_id"])
        if key not in survivors or row[configured_basis] > survivors[key][configured_basis]:
            survivors[key] = row
    reliability = {
        (row["source_id"], row["segment"]): _decimal(row["reliability"])
        for row in root["source_reliability"]
    }
    weighted = []
    for row in survivors.values():
        item = dict(row)
        item["reliability"] = float(reliability[(row["source_id"], row["segment"])])
        item["weighted_contribution"] = (
            float(row["evidence_value"])
            * float(reliability[(row["source_id"], row["segment"])])
        )
        weighted.append(item)
    grouped = defaultdict(list)
    for row in weighted:
        grouped[(row["opportunity_id"], row["segment"], row["campaign_id"], row["channel"])].append(row)
    decisions = []
    opportunities = []
    eligible_ids = set()
    for key in sorted(grouped):
        rows = grouped[key]
        score = sum(float(row["weighted_contribution"]) for row in rows)
        display = _quantize(_decimal(score), int(policy["display_precision"]))
        threshold = _decimal(policy["eligibility_thresholds"][key[1]])
        eligible = _decimal(score) >= threshold and len({row["source_id"] for row in rows}) >= int(policy["minimum_sources"])
        decision = {
            "opportunity_id": key[0], "segment": key[1], "campaign_id": key[2], "channel": key[3],
            "full_precision_score": float(score), "source_count": len({row["source_id"] for row in rows}),
            "estimated_revenue": max(row["estimated_revenue"] for row in rows),
            "display_score": float(display), "eligibility_threshold": float(threshold), "eligible": eligible,
        }
        decisions.append(decision)
        if eligible:
            eligible_ids.add(key[0])
            opportunities.append({name: decision[name] for name in (
                "opportunity_id", "segment", "campaign_id", "channel", "full_precision_score",
                "display_score", "source_count", "estimated_revenue",
            )})
    attribution = [{name: row[name] for name in (
        "contribution_id", "opportunity_id", "source_id", "segment", "campaign_id",
        "effective_date", "recorded_at", "evidence_value", "reliability", "weighted_contribution",
    )} for row in weighted if row["opportunity_id"] in eligible_ids]
    attribution.sort(key=lambda row: (row["opportunity_id"], row["source_id"], row["effective_date"]))
    job1 = {
        "opportunities": opportunities,
        "evidence_attribution": attribution,
        "metadata": {
            "applicable_count": len(usable), "normalized_count": len(survivors),
            "weighted_count": len(weighted), "decision_count": len(decisions),
            "eligible_count": len(opportunities),
        },
    }

    coverage = {row["segment"]: row for row in root["capability_coverage"]}
    commercial = {row["opportunity_id"]: row for row in root["commercial_context"]}
    by_opportunity = defaultdict(list)
    for row in attribution:
        by_opportunity[row["opportunity_id"]].append(row)
    portfolio = []
    for opportunity in opportunities:
        rows = by_opportunity[opportunity["opportunity_id"]]
        retained_total = sum(_decimal(row["weighted_contribution"]) for row in rows)
        if _quantize(retained_total, 12) != _quantize(_decimal(opportunity["full_precision_score"]), 12):
            raise ValueError("oracle single-count contribution mismatch")
        priority = _quantize(
            _decimal(opportunity["full_precision_score"]) * _decimal(coverage[opportunity["segment"]]["coverage_multiplier"])
            + _decimal(opportunity["estimated_revenue"]) * _decimal(commercial[opportunity["opportunity_id"]]["margin_rate"]) / Decimal("100000"),
            4,
        )
        portfolio.append({
            "opportunity_id": opportunity["opportunity_id"], "segment": opportunity["segment"],
            "campaign_id": opportunity["campaign_id"], "channel": opportunity["channel"],
            "priority_score": float(priority), "estimated_revenue": opportunity["estimated_revenue"],
            "coverage_tier": coverage[opportunity["segment"]]["coverage_tier"],
            "attributed_source_count": len({row["source_id"] for row in rows}),
            "display_score": opportunity["display_score"],
        })
    portfolio.sort(key=lambda row: (-row["priority_score"], -row["display_score"], row["opportunity_id"]))
    for position, row in enumerate(portfolio, 1):
        row["portfolio_position"] = position
        row.pop("display_score")
    job2 = {
        "priority_portfolio": portfolio,
        "evidence_attribution": attribution,
        "metadata": {"joined_count": len(opportunities), "portfolio_count": len(portfolio), "attribution_count": len(attribution)},
    }

    campaigns = defaultdict(list)
    for row in portfolio:
        campaigns[(row["campaign_id"], row["segment"], row["channel"])].append(row)
    audience = {row["segment"]: row for row in root["audience_economics"]}
    channel_economics = {row["channel"]: row for row in root["channel_economics"]}
    candidates = []
    for key in sorted(campaigns):
        rows = campaigns[key]
        combined = sum(_decimal(row["priority_score"]) for row in rows)
        impact = _quantize(
            combined * _decimal(audience[key[1]]["audience_size"]) / Decimal("10000")
            * _decimal(channel_economics[key[2]]["conversion_rate"]), 4,
        )
        candidates.append({
            "campaign_id": key[0], "segment": key[1], "channel": key[2],
            "opportunity_count": len({row["opportunity_id"] for row in rows}),
            "combined_priority": float(combined),
            "campaign_revenue": sum(row["estimated_revenue"] for row in rows),
            "expected_impact": float(impact),
        })
    candidates.sort(key=lambda row: (-row["expected_impact"], row["campaign_id"]))
    budget = root["budget_policy"]
    total_used = Decimal("0")
    channel_used = defaultdict(lambda: Decimal("0"))
    allocations = []
    for row in candidates:
        requested = _quantize(
            _decimal(budget["base_campaign_budget"]) + _decimal(row["expected_impact"]) * _decimal(budget["impact_budget_multiplier"]), 2
        )
        channel = row["channel"]
        amount = max(Decimal("0"), min(
            requested,
            _decimal(budget["total_budget"]) - total_used,
            _decimal(budget["channel_caps"][channel]) - channel_used[channel],
        ))
        amount = _quantize(amount, 2)
        total_used += amount
        channel_used[channel] += amount
        allocations.append({
            "campaign_id": row["campaign_id"], "segment": row["segment"], "channel": channel,
            "allocated_budget": float(amount), "expected_impact": row["expected_impact"],
            "opportunity_count": row["opportunity_count"],
        })
    identity = {row["opportunity_id"]: row["campaign_id"] for row in portfolio}
    audit = [dict(row, campaign_id=identity[row["opportunity_id"]]) for row in attribution]
    audit.sort(key=lambda row: (row["campaign_id"], row["opportunity_id"], row["source_id"], row["effective_date"]))
    payload = json.dumps(audit, sort_keys=True, separators=(",", ":")).encode()
    commitment = {"logical_sha256": "sha256:" + hashlib.sha256(payload).hexdigest(), "record_count": len(audit)}
    job3 = {
        "campaign_allocations": allocations,
        "attribution_commitment": commitment,
        "metadata": {
            "candidate_count": len(candidates), "allocation_count": len(allocations),
            "allocated_budget_total": float(_quantize(sum((_decimal(row["allocated_budget"]) for row in allocations), Decimal("0")), 2)),
            "expected_impact_total": float(_quantize(sum((_decimal(row["expected_impact"]) for row in allocations), Decimal("0")), 4)),
        },
    }

    calendar = defaultdict(list)
    for row in root["activation_calendar"]:
        calendar[row["channel"]].append(row)
    capacity = {(row["channel"], row["window_id"]): row["available_slots"] for row in root["channel_capacity"]}
    candidates_windows = []
    for allocation in allocations:
        for window in calendar[allocation["channel"]]:
            if capacity[(allocation["channel"], window["window_id"])] > 0:
                candidates_windows.append(dict(allocation, **window, available_slots=capacity[(allocation["channel"], window["window_id"])]))
    candidates_windows.sort(key=lambda row: (-row["expected_impact"], row["campaign_id"], row["window_start"]))
    remaining = dict(capacity)
    selected = []
    counts = defaultdict(int)
    limit = int(root["scheduling_policy"]["max_windows_per_campaign"])
    for row in candidates_windows:
        key = (row["channel"], row["window_id"])
        if counts[row["campaign_id"]] < limit and remaining[key] > 0:
            selected.append(row)
            counts[row["campaign_id"]] += 1
            remaining[key] -= 1
    budget_unit = int(root["scheduling_policy"]["budget_precision"])
    impact_unit = int(root["scheduling_policy"]["impact_precision"])
    seen = defaultdict(int)
    assigned_budget = defaultdict(lambda: Decimal("0"))
    assigned_impact = defaultdict(lambda: Decimal("0"))
    actions = []
    for row in selected:
        campaign = row["campaign_id"]
        seen[campaign] += 1
        if seen[campaign] == counts[campaign]:
            part_budget = _decimal(row["allocated_budget"]) - assigned_budget[campaign]
            part_impact = _decimal(row["expected_impact"]) - assigned_impact[campaign]
        else:
            part_budget = _quantize(_decimal(row["allocated_budget"]) / counts[campaign], budget_unit)
            part_impact = _quantize(_decimal(row["expected_impact"]) / counts[campaign], impact_unit)
        assigned_budget[campaign] += part_budget
        assigned_impact[campaign] += part_impact
        actions.append({
            "activation_id": f"activation-{len(actions) + 1:02d}", "campaign_id": campaign,
            "segment": row["segment"], "channel": row["channel"], "window_id": row["window_id"],
            "window_start": row["window_start"], "scheduled_budget": float(part_budget),
            "expected_impact": float(part_impact),
        })
    windows = defaultdict(list)
    for row in actions:
        windows[(row["window_id"], row["window_start"], row["channel"])].append(row)
    forecasts = [{
        "window_id": key[0], "window_start": key[1], "channel": key[2],
        "scheduled_budget": sum(row["scheduled_budget"] for row in rows),
        "expected_impact": sum(row["expected_impact"] for row in rows),
        "activation_count": len(rows),
    } for key, rows in sorted(windows.items())]
    job4 = {
        "activation_plan": {
            "activation_actions": actions, "window_forecast": forecasts,
            "aggregate_forecast": {
                "scheduled_budget": round(sum(row["scheduled_budget"] for row in actions), budget_unit),
                "expected_impact": round(sum(row["expected_impact"] for row in actions), impact_unit),
                "activation_count": len(actions),
            },
            "attribution_commitment": commitment,
        },
        "metadata": {
            "campaign_count": len({row["campaign_id"] for row in allocations}),
            "activation_count": len(actions), "window_count": len({row["window_id"] for row in actions}),
        },
    }
    return {"job_1": job1, "job_2": job2, "job_3": job3, "job_4": job4, "contribution_audit": audit, "decisions": decisions}



