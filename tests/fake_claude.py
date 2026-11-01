"""Stand-in for `claude -p` in tests. FAKE_MODE: result | structured | fenced | fail. FAKE_SERVED overrides the served model."""
import json
import os
import sys

args = sys.argv[1:]
prompt = sys.stdin.read()
assert "-p" in args
assert args[args.index("--tools") + 1] == ""
assert args[args.index("--setting-sources") + 1] == ""
assert "--strict-mcp-config" in args and "--no-session-persistence" in args
model = args[args.index("--model") + 1]
mode = os.environ.get("FAKE_MODE", "result")
if mode == "fail":
    print("Claude usage limit reached", file=sys.stderr)
    sys.exit(1)
answer = {"anything_wrong": True, "origin_call": 1, "still_wrong_records": ["splitwise.expenses#77"]}
envelope = {"usage": {"input_tokens": len(prompt)}, "modelUsage": {os.environ.get("FAKE_SERVED", model): {}},
            "is_error": False}
if mode == "structured":
    envelope.update(structured_output=answer, result="")
elif mode == "fenced":
    envelope["result"] = "```json\n" + json.dumps(answer) + "\n```"
else:
    envelope["result"] = json.dumps(answer)
print("[claude-code:unrecognized_model] {}")
print(json.dumps(envelope))
