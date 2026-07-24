"""Generate platform-correct Python 3.11 lock files from pyproject.toml."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
REQUIREMENTS_DIR = BACKEND_DIR / "requirements"


def _compile(output_name: str, *, include_dev: bool, upgrade: bool) -> None:
    command = [
        sys.executable,
        "-m",
        "piptools",
        "compile",
        "pyproject.toml",
        "--no-config",
        "--quiet",
        "--resolver=backtracking",
        "--generate-hashes",
        "--reuse-hashes",
        "--strip-extras",
        "--allow-unsafe",
        "--all-build-deps",
        "--annotation-style=line",
        "--newline=lf",
        "--no-emit-index-url",
        "--no-emit-trusted-host",
        "--output-file",
        f"requirements/{output_name}",
    ]
    if include_dev:
        command.extend(("--extra", "dev"))
    if upgrade:
        command.append("--upgrade")
    subprocess.run(command, cwd=BACKEND_DIR, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="resolve the newest compatible versions instead of preserving existing pins",
    )
    args = parser.parse_args()

    if sys.version_info[:2] != (3, 11):
        raise SystemExit(
            "Python locks must be generated with Python 3.11, the supported "
            f"minimum version; received {sys.version.split()[0]}."
        )

    REQUIREMENTS_DIR.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        _compile("linux-runtime.lock", include_dev=False, upgrade=args.upgrade)
        _compile("linux-dev.lock", include_dev=True, upgrade=args.upgrade)
        return
    if sys.platform == "win32":
        _compile("windows-dev.lock", include_dev=True, upgrade=args.upgrade)
        return
    raise SystemExit(f"Unsupported lock-generation platform: {sys.platform}")


if __name__ == "__main__":
    main()
