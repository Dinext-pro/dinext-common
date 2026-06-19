#!/usr/bin/env python3
"""Admin PUT helper for FCM workflow resync smoke on Task."""
import json
import subprocess
import sys

API = "/home/frappe/.cursor/skills/api/scripts/api.py"
TASK = "TASK-2026-00129"


def put(body):
    proc = subprocess.run(
        [
            sys.executable,
            API,
            "dev",
            f"/api/resource/Task/{TASK}",
            "--method",
            "PUT",
            "--as-admin",
            "--body",
            json.dumps(body, ensure_ascii=False),
        ],
        capture_output=True,
        text=True,
    )
    text = proc.stdout or proc.stderr
    idx = text.find("{")
    if idx < 0:
        raise RuntimeError(text)
    data = json.loads(text[idx:])["data"]
    print(
        json.dumps(
            {
                "modified": data.get("modified"),
                "workflow_state": data.get("workflow_state"),
                "status": data.get("status"),
                "subject": data.get("subject"),
            },
            ensure_ascii=False,
        )
    )
    return data


def baseline():
    put({"workflow_state": "_______", "status": "Open", "subject": "FCM workflow resync test"})


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    if cmd == "baseline":
        baseline()
    elif cmd == "otlozheno":
        put({"workflow_state": "Отложено"})
    elif cmd == "v_rabote":
        put({"workflow_state": "В работе"})
    elif cmd == "ochered":
        put({"workflow_state": "В очереди на консультацию"})
    elif cmd == "subject_server":
        put({"subject": "SERVER subject after resync"})
    else:
        raise SystemExit(f"unknown cmd: {cmd}")
