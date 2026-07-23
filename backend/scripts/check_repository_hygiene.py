"""Verify repository artifact, ignore, line-ending, and generated-file hygiene."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_IGNORE_RULES = frozenset(
    {
        "*.log",
        "*.tsbuildinfo",
        "frontend/.tmp-tests/",
        "/frontend/vite.config.js",
        "/frontend/vite.config.d.ts",
        "/6.0",
    }
)
REQUIRED_GITATTRIBUTE_RULES = frozenset(
    {
        "* text=auto eol=lf",
        "*.bat text eol=crlf",
        "*.cmd text eol=crlf",
        "*.ps1 text eol=crlf",
        "*.psd1 text eol=crlf",
        "*.psm1 text eol=crlf",
        "*.bmp binary !eol",
        "*.gif binary !eol",
        "*.icns binary !eol",
        "*.ico binary !eol",
        "*.jpeg binary !eol",
        "*.jpg binary !eol",
        "*.png binary !eol",
        "*.webp binary !eol",
        "*.eot binary !eol",
        "*.otf binary !eol",
        "*.ttf binary !eol",
        "*.woff binary !eol",
        "*.woff2 binary !eol",
        "*.7z binary !eol",
        "*.bz2 binary !eol",
        "*.doc binary !eol",
        "*.docx binary !eol",
        "*.gz binary !eol",
        "*.pdf binary !eol",
        "*.ppt binary !eol",
        "*.pptx binary !eol",
        "*.rar binary !eol",
        "*.tar binary !eol",
        "*.tgz binary !eol",
        "*.xz binary !eol",
        "*.xls binary !eol",
        "*.xlsx binary !eol",
        "*.zip binary !eol",
        "*.asar binary !eol",
        "*.dll binary !eol",
        "*.dylib binary !eol",
        "*.exe binary !eol",
        "*.msi binary !eol",
        "*.node binary !eol",
        "*.pyd binary !eol",
        "*.so binary !eol",
        "*.db binary !eol",
        "*.db-shm binary !eol",
        "*.db-wal binary !eol",
        "*.sqlite binary !eol",
        "*.sqlite3 binary !eol",
    }
)
ACCIDENTAL_FILENAME_FRAGMENTS = ("WorkingDirectory", "PassThru")
MALFORMED_FILENAME_SENTINEL = (
    "frontend.err.log' -WorkingDirectory "
    "'C:\\Projects\\lighthousePM\\frontend' -PassThru).Id"
)
GENERATED_CONTENT_PATHS = (
    "backend/tests/contracts/api",
    "frontend/src/generated",
)
GENERATED_VITE_CONFIG_PATHS = frozenset(
    {
        "frontend/vite.config.d.ts",
        "frontend/vite.config.js",
    }
)


class RepositoryHygieneError(RuntimeError):
    """Raised when Git cannot provide the inventory required for a check."""


def _run_git(
    repository_root: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _git_paths(repository_root: Path, *arguments: str) -> list[str]:
    result = _run_git(repository_root, *arguments, "-z")
    if result.returncode:
        message = result.stderr.decode(errors="replace").strip()
        raise RepositoryHygieneError(message or "Git inventory command failed.")
    return [os.fsdecode(value) for value in result.stdout.split(b"\0") if value]


def _active_policy_lines(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def forbidden_tracked_paths(paths: list[str]) -> list[str]:
    return sorted(
        path
        for path in paths
        if path == "6.0"
        or path.endswith((".log", ".tsbuildinfo"))
        or path.startswith("frontend/.tmp-tests/")
        or path in GENERATED_VITE_CONFIG_PATHS
        or any(fragment in path for fragment in ACCIDENTAL_FILENAME_FRAGMENTS)
    )


def accidental_visible_paths(paths: list[str]) -> list[str]:
    return sorted(
        path
        for path in paths
        if any(fragment in path for fragment in ACCIDENTAL_FILENAME_FRAGMENTS)
    )


def missing_policy_rules(path: Path, required_rules: frozenset[str]) -> list[str]:
    return sorted(required_rules - _active_policy_lines(path))


def _malformed_filename_is_ignored(repository_root: Path) -> bool:
    result = _run_git(
        repository_root,
        "check-ignore",
        "--no-index",
        "--quiet",
        "--",
        MALFORMED_FILENAME_SENTINEL,
    )
    if result.returncode not in {0, 1}:
        message = result.stderr.decode(errors="replace").strip()
        raise RepositoryHygieneError(message or "Git ignore check failed.")
    return result.returncode == 0


def _generated_content_is_dirty(repository_root: Path) -> bool:
    result = _run_git(
        repository_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        *GENERATED_CONTENT_PATHS,
    )
    if result.returncode:
        message = result.stderr.decode(errors="replace").strip()
        raise RepositoryHygieneError(message or "Git generated-content check failed.")
    return bool(result.stdout)


def repository_hygiene_errors(
    repository_root: Path = REPOSITORY_ROOT,
    *,
    verify_generated_clean: bool = False,
) -> list[str]:
    root = repository_root.resolve()
    tracked_paths = _git_paths(root, "ls-files")
    visible_paths = _git_paths(
        root,
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
    )
    errors: list[str] = []

    forbidden_paths = forbidden_tracked_paths(tracked_paths)
    if forbidden_paths:
        errors.append(
            "forbidden generated or accidental paths are tracked: "
            + ", ".join(forbidden_paths)
        )

    accidental_paths = accidental_visible_paths(visible_paths)
    if accidental_paths:
        errors.append(
            "accidental command-fragment filenames are present: "
            + ", ".join(accidental_paths)
        )

    missing_ignore_rules = missing_policy_rules(
        root / ".gitignore",
        REQUIRED_IGNORE_RULES,
    )
    if missing_ignore_rules:
        errors.append(
            ".gitignore is missing required rules: " + ", ".join(missing_ignore_rules)
        )

    missing_attribute_rules = missing_policy_rules(
        root / ".gitattributes",
        REQUIRED_GITATTRIBUTE_RULES,
    )
    if missing_attribute_rules:
        errors.append(
            ".gitattributes is missing required rules: "
            + ", ".join(missing_attribute_rules)
        )

    if _malformed_filename_is_ignored(root):
        errors.append(
            "the malformed WorkingDirectory/PassThru filename pattern must remain visible"
        )

    if verify_generated_clean and _generated_content_is_dirty(root):
        errors.append(
            "verification unexpectedly modified tracked generated content under: "
            + ", ".join(GENERATED_CONTENT_PATHS)
        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verification-clean",
        action="store_true",
        help=(
            "also require tracked generated content to be unchanged; "
            "use after verification commands in a clean checkout"
        ),
    )
    args = parser.parse_args()

    try:
        errors = repository_hygiene_errors(
            verify_generated_clean=args.verification_clean,
        )
    except RepositoryHygieneError as exc:
        print(f"Repository hygiene could not be checked: {exc}", file=sys.stderr)
        return 1

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("Repository hygiene passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
