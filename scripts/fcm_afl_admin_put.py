#!/usr/bin/env python3
"""Admin PUT helper for FCM live smoke on AFL (Application For Leave)."""
import json
import subprocess
import sys

API = "/home/frappe/.cursor/skills/api/scripts/api.py"
AFL = "Артём Цыганков - 2026-06-10 - 2026-06-12"
ROW1 = "vra8ulghqq"
ROW2 = "vratd50k5g"

ROW1_BASE = {
    "name": ROW1,
    "project": "S-RP-OPRA",
    "doctype": "User Projects",
}

ROW2_BASE = {
    "name": ROW2,
    "project": "TEST-15-106-00",
    "doctype": "User Projects",
}


def put(body):
    proc = subprocess.run(
        [
            sys.executable,
            API,
            "dev",
            f"/api/resource/Application For Leave/{AFL}",
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
                "status": data.get("status"),
                "alreasons": data.get("alreasons"),
                "user_projects": [
                    (r.get("name"), r.get("project")) for r in (data.get("user_projects") or [])
                ],
            },
            ensure_ascii=False,
        )
    )
    return data


def baseline():
    put(
        {
            "status": "Редактирование",
            "alreasons": "FCM AFL baseline",
            "user_projects": [
                dict(ROW1_BASE),
                dict(ROW2_BASE),
            ],
        }
    )


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    if cmd == "baseline":
        baseline()
    elif cmd == "reasons_server":
        put({"alreasons": "SERVER reasons wins"})
    elif cmd == "status_server":
        put({"status": "На согласовании"})
    elif cmd == "row1_project_change":
        put({"user_projects": [{**ROW1_BASE, "project": "S-RP-OPRA"}, dict(ROW2_BASE)]})
    elif cmd == "row1_project_server":
        put({"user_projects": [{**ROW1_BASE, "project": "TEST-15-106-00"}, dict(ROW2_BASE)]})
    elif cmd == "remove_row2":
        put({"user_projects": [dict(ROW1_BASE)]})
    elif cmd == "add_row3":
        put(
            {
                "user_projects": [
                    dict(ROW1_BASE),
                    dict(ROW2_BASE),
                    {"project": "S-RP-OPRA", "doctype": "User Projects"},
                ]
            }
        )
    else:
        raise SystemExit(f"unknown cmd: {cmd}")
