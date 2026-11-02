"""Step 1 of Q14: does Etiq's DebuggerCodeScanner capture plain-Python data flow?

Run in .venv-etiq (no AppWorld, all values synthetic):
  .venv-etiq/bin/python spikes/etiq_plain_python_check.py [OUT_JSON]

Scans three synthetic sources and prints counts per source:
  a_plain      stub `apis` with dict/list returns, later call consumes an earlier value
  b_wrapped    same flow inside solution(apis, requester), called at the end (gold shape)
  c_pandas     responses turned into DataFrames (positive control)
"""
import json
import sys
from pathlib import Path

from etiq_copilot.engine.implementations.scanner import DebuggerCodeScanner

STUB = '''
class _Venmo:
    def login(self, username=None, password=None):
        return {"access_token": "tok-synthetic"}
    def show_transactions(self, access_token=None, page_index=0):
        return [{"transaction_id": 1, "amount": 5.0, "note": "synthetic"},
                {"transaction_id": 2, "amount": 7.5, "note": "synthetic"}]
    def show_transaction(self, transaction_id=None, access_token=None):
        return {"transaction_id": transaction_id, "amount": 5.0}
    def update_transaction(self, transaction_id=None, description=None, access_token=None):
        return {"message": "ok"}

class _Apis:
    venmo = _Venmo()

apis = _Apis()
requester = object()
'''

PLAIN_BODY = '''
token = apis.venmo.login(username="u", password="p")["access_token"]
txs = apis.venmo.show_transactions(access_token=token)
first_id = txs[0]["transaction_id"]
detail = apis.venmo.show_transaction(transaction_id=first_id, access_token=token)
result = apis.venmo.update_transaction(transaction_id=detail["transaction_id"], description="d", access_token=token)
print(result)
'''

SRC_A = STUB + PLAIN_BODY
indented = "".join("    " + line + "\n" for line in PLAIN_BODY.strip("\n").split("\n"))
SRC_B = STUB + "\ndef solution(apis, requester):\n" + indented + "\nsolution(apis, requester)\n"
SRC_C = STUB + '''
import pandas as pd
token = apis.venmo.login(username="u", password="p")["access_token"]
txs = pd.DataFrame(apis.venmo.show_transactions(access_token=token))
first_id = int(txs.iloc[0]["transaction_id"])
detail = pd.DataFrame([apis.venmo.show_transaction(transaction_id=first_id, access_token=token)])
big = detail[detail["amount"] > 1.0]
print(len(big))
'''


def scan(name, src):
    result = DebuggerCodeScanner().scan_code(code_str=src)
    graph = result.create_full_lineage_graph(graph_format="json")
    graph = json.loads(graph) if isinstance(graph, str) else graph
    labels = [str(o.get("label", "")) for o in graph.get("objects", [])]
    errs = result.scan_errors
    row = {
        "source": name,
        "objects": len(graph.get("objects", [])),
        "edges": len(graph.get("edges", [])),
        "scan_error_type": errs.get("type") if isinstance(errs, dict) else (type(errs).__name__ if errs else None),
        "scan_errors_empty": not errs,
        "dataframes": len(result.get_dataframes() or []),
        "models": len(result.get_models() or []),
        "agent_states": len(result.get_agent_states() or []),
        "unstructured_states": len(result.get_unstructured_states() or []),
        "objects_mentioning_apis": sum("apis." in l for l in labels),
    }
    return row, graph, errs


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "runs" / "etiq_bridge" / "step1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows, raw = [], {}
    for name, src in [("a_plain", SRC_A), ("b_wrapped", SRC_B), ("c_pandas", SRC_C)]:
        row, graph, errs = scan(name, src)
        rows.append(row)
        raw[name] = {"graph": graph, "scan_errors": repr(errs)}
        print(json.dumps(row))
    out.write_text(json.dumps({"rows": rows, "raw": raw}, indent=1, default=str))


if __name__ == "__main__":
    main()
