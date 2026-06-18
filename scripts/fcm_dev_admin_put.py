#!/usr/bin/env python3
"""Admin PUT helper for FCM live smoke on dev."""
import json
import subprocess
import sys

API = "/home/frappe/.cursor/skills/api/scripts/api.py"
ISSUE = "ISS-2026-00915"
ROW1 = "atuj9u090i"
ROW2 = "v1g8i274po"

ROW1_BASE = {
    "name": ROW1,
    "category1": "Трудоемкость, ч/ч",
    "category": "Трудоемкость, ч/ч (по умолчанию)",
    "project_role": "Консультант",
    "task": "TASK-2026-00117",
    "type": "User",
    "executor": "administrator@dinext.invalid",
    "status": "В оценке / на доработке",
    "doctype": "Issue Estimations",
}

ROW2_BASE = {
    "name": ROW2,
    "category1": "Сроки, раб. дни",
    "category": "Сроки, раб. дни",
    "project_role": "Разработчик FI",
    "task": "TASK-2026-00117",
    "grade": 4,
    "type": "User",
    "executor": "administrator@dinext.invalid",
    "status": "На согласовании",
    "doctype": "Issue Estimations",
}


def put(body):
    proc = subprocess.run(
        [sys.executable, API, "dev", f"/api/resource/Issue/{ISSUE}", "--method", "PUT", "--as-admin", "--body", json.dumps(body, ensure_ascii=False)],
        capture_output=True,
        text=True,
    )
    text = proc.stdout or proc.stderr
    idx = text.find("{")
    if idx < 0:
        raise RuntimeError(text)
    data = json.loads(text[idx:])["data"]
    print(json.dumps({"modified": data.get("modified"), "subject": data.get("subject"), "priority": data.get("priority"), "estimations": [(r.get("name"), r.get("grade"), r.get("status")) for r in (data.get("estimations") or [])]}, ensure_ascii=False))
    return data


def baseline():
    put({
        "subject": "FCM FULL TEST baseline",
        "priority": "Low",
        "estimations": [
            {**ROW1_BASE, "grade": 10},
            dict(ROW2_BASE),
        ],
    })


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    if cmd == "baseline":
        baseline()
    elif cmd == "priority_medium":
        put({"priority": "Medium"})
    elif cmd == "subject_server":
        put({"subject": "SERVER subject wins"})
    elif cmd == "grade12":
        put({"estimations": [{**ROW1_BASE, "grade": 12}, dict(ROW2_BASE)]})
    elif cmd == "row2_status_closed":
        put({"estimations": [{**ROW1_BASE, "grade": 10}, {**ROW2_BASE, "status": "Согласовано"}]})
    elif cmd == "row1_grade99":
        put({"estimations": [{**ROW1_BASE, "grade": 99}, dict(ROW2_BASE)]})
    elif cmd == "remove_row2":
        put({"estimations": [{**ROW1_BASE, "grade": 10}]})
    elif cmd == "add_row3":
        put({"estimations": [{**ROW1_BASE, "grade": 10}, dict(ROW2_BASE), {"category1": "Сроки, раб. дни", "category": "Сроки, раб. дни", "project_role": "Разработчик FI", "task": "TASK-2026-00117", "grade": 7, "type": "User", "executor": "administrator@dinext.invalid", "status": "На согласовании", "doctype": "Issue Estimations"}]})
    else:
        raise SystemExit(f"unknown cmd: {cmd}")
