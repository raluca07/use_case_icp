# Run or adapt Attempt 057

## Install

Python 3.12, the Codex CLI, Linux Bubblewrap and Etiq 2.3.0 are required for a
full run.

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev,etiq]'
```

Authenticate the Codex CLI before starting live reviews. A full live run makes
576 logical model calls, so review the model and cost settings first.

Run the self-contained release checks with:

```bash
pytest -q
```

## Build, freeze and verify without model calls

```bash
python -m use_case_icp.n27phf_public build
python -m use_case_icp.n27phf_public freeze
python -m use_case_icp.n27phf_public verify
```

The build creates 64 native captures and 96 reviewer packages under
`outputs/attempt-057-reproduction`. The output is intentionally ignored by
Git because it is large.

## Run the reviews

```bash
python -m use_case_icp.n27phf_public live
```

The lifecycle is resumable: rerun `live` after an interruption. Use `--model`
and `--reasoning-effort` to adapt provider settings. Use `--attempt-root` for a
different output directory.

## Adapt the experiment

Start with `src/use_case_icp/n27phf_experiment.py`. It defines the instances,
six one-site mutations, fixtures, treatment schedule, qualification, analysis
and reports. The public entry point changes only workspace-specific provenance
bindings. Shared capture, graph projection and provider machinery lives in the
other modules under `src/use_case_icp`.

The compact published result is under
`docs/workshops/ICLR/N27PHF-natural-state-multi-hard-fault-experiment`. Raw
captures, requests, provider receipts and duplicated execution workspaces are
not committed.
