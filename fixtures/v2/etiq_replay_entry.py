"""Build deterministic replay globals for scanning an exact frozen workflow."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import ModuleType


def canonical_hash(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


class ReplayApiCollection:
    """Stateful API collection used as ETIQ's single custom capture target."""

    def __init__(self, bundle: dict, transcript: list[dict]):
        self._bundle = bundle
        self._transcript = transcript
        self._position = 0
        apps = {}
        for call in bundle["calls"]:
            app = call["app"]
            method = call["method"]
            methods = apps.setdefault(app, {})
            if method not in methods:
                methods[method] = (
                    lambda app_name, method_name: (
                        lambda **kwargs: self._replay_call(app_name, method_name, kwargs)
                    )
                )(app, method)
        for app, methods in apps.items():
            namespace = ModuleType(f"replay_api.{app}")
            for method, function in methods.items():
                setattr(namespace, method, function)
            setattr(self, app, namespace)

    def _replay_call(self, app: str, method: str, kwargs: dict):
        index = self._position
        calls = self._bundle["calls"]
        if index < len(calls) and calls[index].get("injected_hook"):
            while index < len(calls) and calls[index].get("injected_hook"):
                hook = calls[index]
                actual_hash = canonical_hash(hook["hook_args"])
                if hook["args_sha256"] != actual_hash:
                    raise RuntimeError(f"replay hook {index} argument hash differs")
                self._transcript.append({
                    "index": index, "app": hook["app"], "method": hook["method"],
                    "args_sha256": actual_hash,
                })
                self._position += 1
                index = self._position
            index = self._position
        if index >= len(calls):
            raise RuntimeError(f"unexpected replay call {app}.{method} after transcript end")
        expected = calls[index]
        kwargs = copy.deepcopy(kwargs)
        intervention = self._bundle.get("argument_interventions", {}).get(str(index))
        if intervention and intervention["operation"] == "set_arg":
            kwargs[intervention["arg"]] = copy.deepcopy(intervention["value"])
        elif intervention and intervention["operation"] == "partial_file":
            content = kwargs.get(intervention["arg"], "")
            kwargs[intervention["arg"]] = content[:max(1, len(content) // 2)]
        actual_hash = canonical_hash(kwargs)
        if (expected["app"], expected["method"]) != (app, method):
            raise RuntimeError(
                f"replay call {index} expected {expected['app']}.{expected['method']}, "
                f"received {app}.{method}"
            )
        if expected["args_sha256"] != actual_hash:
            raise RuntimeError(f"replay call {index} argument hash differs")
        item = {"index": index, "app": app, "method": method, "args_sha256": actual_hash}
        self._transcript.append(item)
        self._position += 1
        return copy.deepcopy(expected["response"])

    def assert_complete(self) -> None:
        if self._position != len(self._bundle["calls"]):
            raise RuntimeError(
                f"replay ended after {self._position} of {len(self._bundle['calls'])} calls"
            )


def write_replay_result(path: Path, bundle: dict, transcript: list[dict], final_output) -> None:
    result = {
        "transcript": transcript,
        "transcript_sha256": canonical_hash(transcript),
        "final_output": final_output,
        "final_output_sha256": canonical_hash(final_output),
        "workflow_sha256": bundle["workflow_sha256"],
    }
    path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
