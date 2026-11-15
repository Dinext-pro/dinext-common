"""Run Workflow acceptance on a fresh bench with pinned public dependencies."""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from xml.etree import ElementTree

SITE = "ci.test"
BASE_URL = "http://localhost:8000"
DEPENDENCIES = {
    "frappe": "743721925cc2a4479f68a8315f0bdbaec7dc9870",
    "erpnext": "548e80297397ba5d3ca4fb111a923fe784a37f4e",
    "hrms": "b8cdb4431d6322477c4ed7c04d164fe00972298a",
    "doctype_permission": "43a18b9611d9a1fdf69a3c8d25bf953f468a146a",
    "frappe_comment_xt": "9b2e6b44a291f1cbdcf0808ffa34f250dbd0dfc6",
    "dinext_projects": "1e2edd35b1173c101c74d15a61f2f952354fb43d",
    "dinext_projects_pl": "d3a6e0c6edad7267fe41dc6dbe7f923acd001df5",
    "dinext_timesheets": "dc9033f61be3a2bd294ca521ccfef362d8e56389",
    "project_workload_assignment": "e0689b7f8d0def8b1f6cf5bd7f766b0f604c1d06",
    "dinext_project_tasks_gantt": "d5080b2d3d5bb9e492ced30eb0ded0767e030043",
}
SPECS = {
    "dinext_common": (
        "approval_deadline_chart.js",
        "workflow_scenarios.js",
        "workflow_scenario_timesheets.js",
        "workflow_progress_unlock.js",
        "workflow_request_receipts.js",
    ),
    "dinext_projects": ("workflow_comment_banner.js",),
    "dinext_timesheets": ("timesheet_team_lead.js", "worker_calendar_deadlines.js"),
}
SERVER_TESTS = {
    "dinext_common": {
        "test_workflow_request_receipt": (),
        "test_workflow_approval_api": (),
        "test_workflow_approval_integration": (),
        "test_workflow_approval_concurrency": (),
        "test_workflow_list_actions": (),
        "test_workflow_scenario_api": (),
        "test_workflow_scenario_bulk": (),
        "test_workflow_scenario_compat": (),
        "test_workflow_scenario_lifecycle": (),
        "test_workflow_scenario_reselection_integration": (),
        "test_workflow_scenario_timesheet_integration": (),
        "test_workflow_scenario_timesheets": (),
        "test_workflow_deadline_integration": ("test_signed_comment_uses_live_rule_and_invalid_input_keeps_retry",),
    },
    "dinext_projects": {
        "test_application_for_leave": (),
        "test_workflow_deadlines": (),
    },
    "dinext_timesheets": {
        "test_deadline_integration": (),
        "test_deadlines": (),
        "test_timesheet_settings_refinements": (),
        "test_timesheet_team_lead_access": (),
    },
}


def configure_runner(support, config, common_sha):
    catalog_file = support / "public-apps.json"
    catalog = json.loads(catalog_file.read_text())
    for app, revision in (DEPENDENCIES | {"dinext_common": common_sha}).items():
        if len(revision) != 40 or any(digit not in "0123456789abcdef" for digit in revision):
            raise ValueError(f"Invalid acceptance commit for {app}")
        catalog[app]["ci_sha"] = revision

    # Install the dependencies needed by Workflow integration tests before the owning app.
    common = catalog["dinext_common"]
    common["test_dependencies"] = ["hrms", "doctype_permission", "frappe_comment_xt"]
    order = config.get("post_install", [])
    if "dinext_project_tasks_gantt" not in order:
        raise ValueError("Workflow acceptance requires the Worker utilization table and linked Issue field")
    catalog_file.write_text(json.dumps(catalog))

    # Extend the isolated site settings before imports and integration tests run.
    runner = support / "bench_tests.py"
    code = runner.read_text()
    anchor = "common.write_text(json.dumps(settings))"
    tests_anchor = "\n    report = Path(os.environ['RUNNER_TEMP']) / (app + '-unit.xml')"
    if code.count(anchor) != 1 or code.count(tests_anchor) != 1:
        raise RuntimeError("Shared bench runner does not match its pinned setup contract")
    settings = {
        "developer_mode": 1,
        "enable_parallel_workflow_approval": 1,
        "workflow_email_test_site": 1,
        "workflow_scenarios_test_site": 1,
        "host_name": BASE_URL,
    }
    code = code.split(tests_anchor, 1)[0]
    runner.write_text(code.replace(anchor, f"settings.update({settings!r})\n{anchor}") + "\n")
    return runner


def run_server(bench, app, artifacts):
    failures = []
    for module, tests in SERVER_TESTS[app].items():
        report = artifacts / f"server-{module}.xml"
        qualified = f"{app}.tests.{module}"
        result = subprocess.run([
            "bench", "--site", SITE, "run-tests", "--app", app, "--module", qualified,
            "--skip-test-records", f"--junit-xml-output={report}",
            *(argument for name in tests for argument in ("--test", name)),
        ], cwd=bench, check=False, timeout=1200)
        try:
            check_report(report, reject_skipped=True)
        except (OSError, ElementTree.ParseError, RuntimeError):
            failures.append(qualified)
        else:
            if result.returncode:
                failures.append(qualified)
    return failures


def run_browser(bench, app, artifacts):
    env = os.environ | {
        "DEV_SERVER": "1",
        "FRAPPE_SITE": SITE,
        "CYPRESS_adminPassword": "ci-admin",
    }
    env.pop("CYPRESS_RECORD_KEY", None)
    # Clear old screenshots from the test checkout and preserve this run's evidence.
    spec_paths = [f"cypress/integration/{spec}" for spec in SPECS[app]]
    app_root = bench / "apps" / app
    for spec in spec_paths:
        if not (app_root / spec).is_file():
            raise RuntimeError(f"Missing acceptance scenario {spec}")

    with (artifacts / "web.log").open("w") as output:
        server = subprocess.Popen(
            ["bench", "--site", SITE, "serve", "--port", "8000", "--noreload"],
            cwd=bench, env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True,
        )
        try:
            for _ in range(60):
                if server.poll() is not None:
                    raise RuntimeError("Disposable Desk server exited")
                try:
                    with urlopen(f"{BASE_URL}/api/method/ping", timeout=2) as response:
                        if response.status == 200:
                            break
                except (URLError, TimeoutError):
                    time.sleep(1)
            else:
                raise RuntimeError("Disposable Desk server did not start")
            subprocess.run(
                ["bench", "--site", SITE, "run-ui-tests", app, "--headless", "--browser",
                    "electron", "--spec", ",".join(spec_paths), "--reporter", "junit",
                    "--reporter-options", f"mochaFile={artifacts / 'browser-[hash].xml'}", "--config",
                    f"screenshotsFolder={artifacts / 'screenshots'}"],
                cwd=bench, env=env, check=True, timeout=1500,
            )
        finally:
            if server.poll() is None:
                os.killpg(server.pid, signal.SIGTERM)
                server.wait(timeout=30)
    report_paths = list(artifacts.glob("browser-*.xml"))
    if len(report_paths) < len(spec_paths):
        raise RuntimeError("Cypress did not report every selected spec")
    for path in report_paths:
        check_report(path, reject_skipped=True)


def check_report(path, *, reject_skipped=False):
    suites = list(ElementTree.parse(path).iter("testsuite"))
    total = sum(int(suite.get("tests", 0)) for suite in suites)
    unexpected = ("failures", "errors", "skipped") if reject_skipped else ("failures", "errors")
    if not total or any(int(suite.get(key, 0)) for suite in suites for key in unexpected):
        raise RuntimeError(f"Acceptance test report is incomplete or failing: {path.name}")


def main():
    source = Path(sys.argv[1]).resolve()
    pinned_support = Path(sys.argv[2]).resolve()
    runner_temp = Path(os.environ["RUNNER_TEMP"])
    config = json.loads((source / ".github/dinext-ci.json").read_text())
    app = config["app"]
    source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    common_sha = source_sha if app == "dinext_common" else os.environ["WORKFLOW_COMMON_SHA"]
    artifacts = runner_temp / "workflow-acceptance"
    artifacts.mkdir()
    (artifacts / "revisions.json").write_text(
        json.dumps(DEPENDENCIES | {"dinext_common": common_sha, app: source_sha}, indent=2) + "\n"
    )
    with tempfile.TemporaryDirectory(dir=runner_temp) as directory:
        support = Path(directory) / "ci"
        shutil.copytree(pinned_support, support)
        runner = configure_runner(support, config, common_sha)
        subprocess.run([sys.executable, runner, source], check=True)
    bench = runner_temp / "dinext-test-bench"
    failures = run_server(bench, app, artifacts)
    if failures:
        print("Failing Workflow server suites: " + ", ".join(failures), flush=True)
    run_browser(bench, app, artifacts)
    if failures:
        raise RuntimeError("One or more Workflow server suites failed")


if __name__ == "__main__":
    main()
