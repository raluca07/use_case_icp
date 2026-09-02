import json
import sys
import pandas as pd

def map_capability_coverage(handoff_df, capabilities_df):
    allowed_record_ids = ['n06-r01', 'n06-r02', 'n06-r03', 'n06-r04', 'n06-r05', 'n06-r06', 'n06-r07', 'n06-r08']
    capability_rows = capabilities_df.to_dict('records')
    retained = handoff_df[handoff_df.get('record_id', '').isin(allowed_record_ids)]
    coverage_records = []
    for _, row in retained.iterrows():
        need = row.get('need', '') or ''
        matched_capability_id = ''
        for capability in capability_rows:
            if (capability.get('need', '') or '') == need:
                matched_capability_id = capability.get('capability_id', '') or ''
                break
        coverage_records.append({'record_id': row.get('record_id', '') or '', 'need': need, 'capability_id': matched_capability_id, 'coverage': 'direct' if matched_capability_id else 'none'})
    return pd.DataFrame(coverage_records)

def prioritize_needs(coverage_df, evidence_sources_df):
    rank_map = {}
    for source in evidence_sources_df.to_dict('records'):
        record_id = source.get('record_id', '') or ''
        rank_map[record_id] = int(source.get('rank', 0) or 0)
    priority_records = []
    for row in coverage_df.to_dict('records'):
        record_id = row.get('record_id', '') or ''
        coverage = row.get('coverage', '') or ''
        unsupported = coverage != 'direct'
        priority_records.append({'record_id': record_id, 'need': row.get('need', '') or '', 'capability_id': row.get('capability_id', '') or '', 'coverage': coverage, 'unsupported': unsupported, 'rank': rank_map.get(record_id, 0)})
    ordered = sorted(priority_records, key=lambda row: (0 if row.get('unsupported', False) else 1, int(row.get('rank', 0) or 0), str(row.get('record_id', '') or '')))
    return pd.DataFrame(ordered)

def synthesize_recommendation(priorities_df):
    index_window = [0]
    retained = priorities_df.head(len(index_window)).reset_index(drop=True)
    priority_records = retained.to_dict('records')
    first_priority = priority_records[0] if priority_records else {}
    recommendation = {'top_need': first_priority.get('need', '') or '', 'decision': 'prioritize' if first_priority.get('unsupported', False) else 'maintain'}
    return (retained, recommendation)
payload = json.load(sys.stdin)
needs_df = pd.DataFrame(payload.get('needs', []))
evidence_sources_df = pd.DataFrame(payload.get('evidence_sources', []))
capabilities_df = pd.DataFrame(payload.get('capabilities', []))
coverage_df = map_capability_coverage(needs_df, capabilities_df)
priorities_df = prioritize_needs(coverage_df, evidence_sources_df)
retained_priorities_df, recommendation = synthesize_recommendation(priorities_df)
result = {'coverage': coverage_df.to_dict('records'), 'priorities': retained_priorities_df.to_dict('records'), 'recommendation': recommendation, 'metadata': {'coverage_count': int(len(coverage_df)), 'priority_count': int(len(retained_priorities_df))}}
json.dump(result, sys.stdout, separators=(',', ':'))
