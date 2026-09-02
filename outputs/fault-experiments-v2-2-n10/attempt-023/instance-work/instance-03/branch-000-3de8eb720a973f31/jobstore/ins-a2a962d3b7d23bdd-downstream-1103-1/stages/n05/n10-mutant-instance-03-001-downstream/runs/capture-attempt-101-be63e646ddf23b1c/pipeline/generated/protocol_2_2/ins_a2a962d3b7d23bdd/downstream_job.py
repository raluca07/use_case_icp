import json
import sys
import pandas as pd

def map_coverage(needs_df, capabilities_df):
    allowed_record_ids = ['n06-r01', 'n06-r02', 'n06-r03', 'n06-r04', 'n06-r05', 'n06-r06', 'n06-r07', 'n06-r08']
    required_need_columns = ['record_id', 'need', 'demand_score', 'source_id', 'source_weight']
    prepared_needs = needs_df.reindex(columns=required_need_columns).fillna({'record_id': '', 'need': '', 'demand_score': 0, 'source_id': '', 'source_weight': 0})
    retained_needs = prepared_needs[prepared_needs['record_id'].isin(allowed_record_ids)]
    capability_rows = capabilities_df.reindex(columns=['capability_id', 'need']).fillna({'capability_id': '', 'need': ''})
    capability_by_need = {}
    for _, capability in capability_rows.iterrows():
        need = capability.get('need', '')
        if need not in capability_by_need:
            capability_by_need[need] = capability.get('capability_id', '')
    coverage_records = []
    for _, row in retained_needs.iterrows():
        need = row.get('need', '')
        capability_id = capability_by_need.get(need, '')
        coverage_records.append({'record_id': row.get('record_id', ''), 'need': need, 'capability_id': capability_id, 'coverage': 'direct' if capability_id != '' else 'unsupported'})
    return pd.DataFrame(coverage_records)

def prioritize_needs(coverage_df, evidence_sources_df):
    evidence_rows = evidence_sources_df.reindex(columns=['record_id', 'source_id', 'source_weight', 'rank']).fillna({'record_id': '', 'source_id': '', 'source_weight': 0, 'rank': 0})
    rank_by_record_id = {}
    for _, row in evidence_rows.iterrows():
        rank_by_record_id[row.get('record_id', '')] = row.get('rank', 0)
    priority_inputs = []
    for _, row in coverage_df.iterrows():
        coverage = row.get('coverage', '')
        unsupported = coverage == 'direct'
        record_id = row.get('record_id', '')
        priority_inputs.append({'record_id': record_id, 'need': row.get('need', ''), 'capability_id': row.get('capability_id', ''), 'coverage': coverage, 'unsupported': unsupported, 'upstream_rank': rank_by_record_id.get(record_id, 0)})
    ordered = sorted(priority_inputs, key=lambda item: (0 if item.get('unsupported', False) else 1, item.get('upstream_rank', 0), item.get('record_id', '')))
    priority_records = []
    for priority, item in enumerate(ordered, start=1):
        priority_records.append({'priority': priority, 'record_id': item.get('record_id', ''), 'need': item.get('need', ''), 'capability_id': item.get('capability_id', ''), 'coverage': item.get('coverage', ''), 'unsupported': bool(item.get('unsupported', False)), 'upstream_rank': item.get('upstream_rank', 0)})
    return pd.DataFrame(priority_records)

def synthesize_recommendation(priorities_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    retained_priorities = priorities_df.head(len(index_window)).reset_index(drop=True)
    if len(retained_priorities) == 0:
        first_priority = {'need': '', 'unsupported': False}
    else:
        first_priority = retained_priorities.iloc[0].to_dict()
    recommendation = {'top_need': first_priority.get('need', ''), 'decision': 'prioritize' if bool(first_priority.get('unsupported', False)) else 'maintain'}
    return (retained_priorities, recommendation)
_payload = json.load(sys.stdin)
_needs_df = pd.DataFrame(_payload.get('needs', []))
_evidence_sources_df = pd.DataFrame(_payload.get('evidence_sources', []))
_capabilities_df = pd.DataFrame(_payload.get('capabilities', []))
_coverage_df = map_coverage(_needs_df, _capabilities_df)
_priorities_df = prioritize_needs(_coverage_df, _evidence_sources_df)
_retained_priorities_df, _recommendation = synthesize_recommendation(_priorities_df)
_result = {'coverage': _coverage_df.to_dict(orient='records'), 'priorities': _retained_priorities_df.to_dict(orient='records'), 'recommendation': _recommendation, 'metadata': {'instance_id': 'ins-a2a962d3b7d23bdd', 'job': 'downstream', 'candidate_number': 1, 'priority_count': int(len(_retained_priorities_df))}}
json.dump(_result, sys.stdout, sort_keys=True, separators=(',', ':'))
