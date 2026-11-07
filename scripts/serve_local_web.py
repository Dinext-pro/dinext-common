"""Run the local web profile with native Python source notifications."""

import os
import sys
from importlib.util import find_spec
from pathlib import Path


def main():
	command = [
		sys.executable,
		"-m",
		"watchdog.watchmedo",
		"auto-restart",
		"--recursive",
		"--patterns=*.py",
		"--ignore-directories",
		"--ignore-patterns=*/test_*.py;*/__pycache__/*;*/node_modules/*",
		"--debounce-interval=0.5",
		"--signal=SIGTERM",
		"--kill-after=30",
	]
	for name in Path("apps.txt").read_text().splitlines():
		name = name.strip()
		if not name.isidentifier():
			continue
		spec = find_spec(name)
		if spec and spec.submodule_search_locations:
			command.extend(f"--directory={path}" for path in spec.submodule_search_locations)
	command.extend(
		[
			"--",
			sys.executable,
			"-m",
			"gunicorn",
			"--workers",
			"8",
			"--worker-class",
			"gevent",
			"--worker-connections",
			"50",
			"--bind",
			"0.0.0.0:8000",
			"--timeout",
			"120",
			"--keep-alive",
			"0",
			"dinext_common.local_web:create_application()",
		]
	)
	os.execv(sys.executable, command)


if __name__ == "__main__":
	main()
