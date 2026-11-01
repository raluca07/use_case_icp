"""Stand-in for `claude -p` in tests.

FAKE_MODE: result | structured | fenced | fail | fail_stdout | error_envelope | malformed | garbage | sleep.
FAKE_SERVED overrides the served model; FAKE_SERVED_EXTRA adds a second served model.
FAKE_ERR sets the failure text. FAKE_COUNT_FILE gets one line appended per invocation.
The envelope's usage reports the stdin it actually read: input_chars and input_sha256.
"""
import hashlib
import json
import os
import sys
import time

args = sys.argv[1:]
prompt = sys.stdin.read()
assert "-p" in args
assert args[args.index("--tools") + 1] == ""
assert args[args.index("--setting-sources") + 1] == ""
assert "--strict-mcp-config" in args and "--no-session-persistence" in args
model = args[args.index("--model") + 1]
mode = os.environ.get("FAKE_MODE", "result")
if os.environ.get("FAKE_COUNT_FILE"):
    with open(os.environ["FAKE_COUNT_FILE"], "a") as handle:
        handle.write("call\n")
failure = os.environ.get("FAKE_ERR", "Claude usage limit reached")
if mode == "fail":
    print(failure, file=sys.stderr)
    sys.exit(1)
if mode == "fail_stdout":
    print(failure)
    sys.exit(1)
if mode == "sleep":
    time.sleep(30)
if mode == "garbage":
    print("this is not json")
    sys.exit(0)
answer = {"anything_wrong": True, "origin_call": 1, "still_wrong_records": ["splitwise.expenses#77"]}
if mode == "malformed":
    answer = {"anything_wrong": "yes", "origin_call": 1}
served = {os.environ.get("FAKE_SERVED", model): {}}
if os.environ.get("FAKE_SERVED_EXTRA"):
    served[os.environ["FAKE_SERVED_EXTRA"]] = {}
envelope = {"usage": {"input_chars": len(prompt), "input_sha256": hashlib.sha256(prompt.encode()).hexdigest()},
            "modelUsage": served, "is_error": mode == "error_envelope"}
if mode == "structured":
    envelope.update(structured_output=answer, result="")
elif mode == "fenced":
    envelope["result"] = "```json\n" + json.dumps(answer) + "\n```"
else:
    envelope["result"] = json.dumps(answer)
print("[claude-code:unrecognized_model] {}")
print(json.dumps(envelope))
