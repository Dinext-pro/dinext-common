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
    "frappe": "3b73839e0c5080f638d007fe96e2da02225d6674",
    "erpnext": "548e80297397ba5d3ca4fb111a923fe784a37f4e",
    "hrms": "b8cdb4431d6322477c4ed7c04d164fe00972298a",
    "doctype_permission": "81c9c824d5cdf274c6350a1ee073c4359d4616e7",
    "frappe_comment_xt": "9b2e6b44a291f1cbdcf0808ffa34f250dbd0dfc6",
    "dinext_projects": "534345d00bb10489c74f64048bfb74bba6593c60",
    "dinext_projects_pl": "6b6852fd63bb863344b5183216f5ce0521e66338",
    "dinext_timesheets": "c2a98bf6372201aafd72169a38210fce5ffeb934",
    "dinext_deputies": "ed5798add9aaa5c80f51f634316adb8a191d5126",
    "project_workload_assignment": "18a0845b25f3759a607760ca5aa6316e68f0f006",
    "dinext_project_tasks_gantt": "c9650bf6986c8e276c1899139b2e90d1253bfc45",
}
SPECS = {
    "dinext_common": (
        "approval_deadline_chart.js",
        "workflow_scenarios.js",
        "workflow_round_errors.js",
        "workflow_delegation_audit.js",
        "workflow_progress_unlock.js",
        "workflow_request_receipts.js",
    ),
    "dinext_timesheets": (
        "timesheet_team_lead.js", "worker_calendar_deadlines.js", "ut_form_workflow_position_failures.js",
        "ut_empty_approval.js", "workflow_scenario_timesheets.js",
        "application_for_leave.js", "afl_workflow_comment_banner.js", "workflow_transition_style.js",
    ),
    "project_workload_assignment": ("workload_absence_navigation.js",),
}
SERVER_TESTS = {
    "dinext_common": {
        "test_workflow_request_receipt": (),
        "test_workflow_approval_api": (),
        "test_workflow_approval_engine": (),
        "test_workflow_approval_integration": (),
        "test_workflow_approval_permissions": (),
        "test_workflow_approval_source_batches": (),
        "test_workflow_approval_desk": (),
        "test_workflow_native_access": (),
        "test_my_approvals_audit": (),
        "test_workflow_scenario_records": (),
        "test_my_approvals_permissions_integration": (),
        "test_workflow_approval_migration": (),
        "test_workflow_legacy_api_retirement": (),
        "test_workflow_queued_round_failure": (),
        "test_workflow_approval_concurrency": (),
        "test_workflow_approval_signed_links": (),
        "test_rebuild_round_conflict": (),
        "test_workflow_standards": (),
        "test_workflow_list_actions": (),
        "test_workflow_form_references": (),
        "test_workflow_localization": (),
        "test_workflow_scenario_api": (),
        "test_workflow_scenario_bulk": (),
        "test_workflow_scenario_compat": (),
        "test_workflow_scenario_lifecycle": (),
        "test_workflow_scenario_reselection_integration": (),
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
        "test_empty_timesheet_approval": (),
        "test_workflow_scenario_timesheet_integration": (),
        "test_workflow_scenario_timesheets": (),
        "dinext_timesheets.dinext_timesheets.doctype.application_for_leave.test_application_for_leave": (),
        "test_approval_fingerprint_integration": (),
        "test_utp_status_migration": (),
        "test_workflow_email_ownership": (),
        "test_workflow_limit_notifications": (),
        "test_workflow_position_batch_failures": (),
        "test_workflow_localization": (),
        "dinext_timesheets.dinext_timesheets.user_timesheet.test_status_rollup": (),
        "dinext_timesheets.dinext_timesheets.user_timesheet.test_workflow_tasks_bridge": (),
    },
    "project_workload_assignment": {
        "project_workload_assignment.project_workload_assignment.tests.test_approval_compatibility": (),
        "project_workload_assignment.project_workload_assignment.tests.test_plan_fact_adapter": (),
    },
    "dinext_project_tasks_gantt": {"test_timesheet_status_compatibility": ()},
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
        "workflow_style_test_site": 1,
        "host_name": BASE_URL,
    }
    code = code.split(tests_anchor, 1)[0]
    runner.write_text(code.replace(anchor, f"settings.update({settings!r})\n{anchor}") + "\n")
    return runner


def run_server(bench, app, artifacts):
    failures = []
    for module, tests in SERVER_TESTS[app].items():
        report = artifacts / f"server-{module}.xml"
        qualified = module if module.startswith(f"{app}.") else f"{app}.tests.{module}"
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

    config_args = (
        ["--config-file", "cypress.bench.config.js"] if app == "project_workload_assignment" else []
    )
    report_prefix = f"browser-{app}-"
    with (artifacts / f"{app}-web.log").open("w") as output:
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
                    "electron", *config_args, "--spec", ",".join(spec_paths), "--reporter", "junit",
                    "--reporter-options", f"mochaFile={artifacts / (report_prefix + '[hash].xml')}", "--config",
                    f"screenshotsFolder={artifacts / 'screenshots'}"],
                cwd=bench, env=env, check=True, timeout=1500,
            )
        finally:
            if server.poll() is None:
                os.killpg(server.pid, signal.SIGTERM)
                server.wait(timeout=30)
    report_paths = list(artifacts.glob(report_prefix + "*.xml"))
    if len(report_paths) < len(spec_paths):
        raise RuntimeError("Cypress did not report every selected spec")
    for path in report_paths:
        check_report(path, reject_skipped=True)


def check_report(path, *, reject_skipped=False):
    report = ElementTree.parse(path)
    suites = list(report.iter("testsuite"))
    total = sum(int(suite.get("tests", 0)) for suite in suites)
    unexpected = ("failures", "errors", "skipped") if reject_skipped else ("failures", "errors")
    incomplete = reject_skipped and (len(report.findall(".//testcase")) != total or report.find(".//skipped") is not None)
    if not total or incomplete or any(int(suite.get(key, 0)) for suite in suites for key in unexpected):
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
    subprocess.run([
        str(bench / "env/bin/python"), "-c",
        "from frappe.model.db_query import DatabaseQuery; "
        "assert not hasattr(DatabaseQuery, 'final_permission_query_conditions_version')",
    ], cwd=bench, check=True)
    failures = run_server(bench, app, artifacts)
    if app == "dinext_common":
        for consumer in ("project_workload_assignment", "dinext_project_tasks_gantt"):
            failures.extend(run_server(bench, consumer, artifacts))
    if failures:
        print("Failing Workflow server suites: " + ", ".join(failures), flush=True)
    if SPECS.get(app):
        run_browser(bench, app, artifacts)
    if app == "dinext_common":
        run_browser(bench, "project_workload_assignment", artifacts)
    if failures:
        raise RuntimeError("One or more Workflow server suites failed")


if __name__ == "__main__":
    main()
