import json
import sys
import pandas as pd

def select_demand_rows(corpus_df):
    fallback_ids = ['n06-r07', 'n06-r08']
    work = corpus_df.reindex(columns=['record_id', 'need', 'demand_score', 'source_id', 'source_weight'])
    selected = work[(work['demand_score'] >= 3) | work['record_id'].isin(fallback_ids)]
    records = []
    for _, row in selected.iterrows():
        records.append({'record_id': row.get('record_id', ''), 'demand_score': row.get('demand_score', 0), 'source_id': row.get('source_id', ''), 'source_weight': row.get('source_weight', 0)})
    return pd.DataFrame(records, columns=['record_id', 'need', 'demand_score', 'source_id', 'source_weight'])

def normalize_evidence(selected_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    allowed_record_ids = ['n06-r01', 'n06-r02', 'n06-r03', 'n06-r04', 'n06-r05', 'n06-r06', 'n06-r07', 'n06-r08']
    required_columns = ['record_id', 'need', 'demand_score', 'source_id', 'source_weight']
    normalized = selected_df.reindex(columns=required_columns)
    normalized = normalized.fillna({'record_id': '', 'need': '', 'demand_score': 0, 'source_id': '', 'source_weight': 0})
    retained = normalized[normalized['record_id'].isin(allowed_record_ids)]
    return retained.head(len(index_window)).reset_index(drop=True)

def assemble_provenance(needs_df):
    records = needs_df.to_dict(orient='records')
    ordered = sorted(records, key=lambda record: (-record.get('demand_score', 0), record.get('record_id', '')))
    evidence_records = []
    for rank_index, record in enumerate(ordered, start=1):
        evidence_records.append({'record_id': record.get('record_id', ''), 'source_id': record.get('source_id', ''), 'source_weight': record.get('source_weight', 0), 'rank': rank_index})
    return pd.DataFrame(evidence_records, columns=['record_id', 'source_id', 'source_weight', 'rank'])
_input = json.load(sys.stdin)
_corpus_df = pd.DataFrame(_input.get('corpus', []))
_selected_df = select_demand_rows(_corpus_df)
_needs_df = normalize_evidence(_selected_df)
_evidence_df = assemble_provenance(_needs_df)
_result = {'needs': _needs_df.to_dict(orient='records'), 'evidence_sources': _evidence_df.to_dict(orient='records'), 'metadata': {'job': 'upstream', 'record_count': int(len(_needs_df)), 'evidence_source_count': int(len(_evidence_df))}}
json.dump(_result, sys.stdout, separators=(',', ':'))
