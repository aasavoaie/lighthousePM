from pathlib import Path
import subprocess

import pytest

from scripts import check_repository_hygiene as hygiene


def test_current_repository_satisfies_hygiene_policy() -> None:
    assert hygiene.repository_hygiene_errors() == []


def test_forbidden_tracked_paths_cover_every_approved_artifact_class() -> None:
    paths = [
        "6.0",
        "backend/backend.out.log",
        "frontend/tsconfig.app.tsbuildinfo",
        "frontend/.tmp-tests/api/types.js",
        "frontend/vite.config.d.ts",
        "frontend/vite.config.js",
        "frontend.err.log' -WorkingDirectory 'C:/repo' -PassThru).Id",
        "frontend/src/App.tsx",
    ]

    assert hygiene.forbidden_tracked_paths(paths) == sorted(paths[:-1])


def test_accidental_command_fragments_remain_visible() -> None:
    paths = [
        "frontend.err.log' -WorkingDirectory 'C:/repo' -PassThru).Id",
        "ordinary-file.txt",
    ]

    assert hygiene.accidental_visible_paths(paths) == [paths[0]]


def test_generated_content_status_detects_verification_mutations(
    monkeypatch,
) -> None:
    result = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=b" M frontend/src/generated/metricCatalogFallback.json\n",
        stderr=b"",
    )
    monkeypatch.setattr(hygiene, "_run_git", lambda *_args: result)

    assert hygiene._generated_content_is_dirty(Path(".")) is True


def test_indexed_line_ending_inventory_accepts_normalized_and_non_text_content(
    monkeypatch,
) -> None:
    result = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=(
            b"i/lf    w/crlf  attr/text eol=lf\tREADME.md\0"
            b"i/none  w/none  attr/text eol=lf\tempty-file\0"
            b"i/-text w/-text attr/-text\timage.png\0"
            b"i/lf    w/lf    attr/text eol=lf\tpath-with-\t-tab.txt\0"
        ),
        stderr=b"",
    )
    monkeypatch.setattr(hygiene, "_run_git", lambda *_args: result)

    assert hygiene._indexed_line_ending_violations(Path(".")) == []


def test_indexed_line_ending_inventory_rejects_crlf_and_mixed_content(
    monkeypatch,
) -> None:
    result = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=(
            b"i/crlf w/crlf attr/text eol=lf\twindows.txt\0"
            b"i/mixed w/mixed attr/text eol=lf\tmixed.txt\0"
        ),
        stderr=b"",
    )
    monkeypatch.setattr(hygiene, "_run_git", lambda *_args: result)

    assert hygiene._indexed_line_ending_violations(Path(".")) == [
        "mixed.txt (i/mixed)",
        "windows.txt (i/crlf)",
    ]


@pytest.mark.parametrize(
    "stdout",
    [
        b"",
        b"missing-tab-separator\0",
        b"i/unknown w/lf attr/text eol=lf\tunknown.txt\0",
    ],
)
def test_indexed_line_ending_inventory_fails_closed_on_unusable_output(
    monkeypatch,
    stdout: bytes,
) -> None:
    result = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=stdout,
        stderr=b"",
    )
    monkeypatch.setattr(hygiene, "_run_git", lambda *_args: result)

    with pytest.raises(hygiene.RepositoryHygieneError):
        hygiene._indexed_line_ending_violations(Path("."))


def test_indexed_line_ending_inventory_fails_closed_when_git_fails(
    monkeypatch,
) -> None:
    result = subprocess.CompletedProcess(
        args=[],
        returncode=128,
        stdout=b"",
        stderr=b"inventory unavailable",
    )
    monkeypatch.setattr(hygiene, "_run_git", lambda *_args: result)

    with pytest.raises(
        hygiene.RepositoryHygieneError,
        match="inventory unavailable",
    ):
        hygiene._indexed_line_ending_violations(Path("."))


def test_missing_policy_rules_reports_only_absent_active_rules(
    tmp_path: Path,
) -> None:
    policy_path = tmp_path / ".gitignore"
    policy_path.write_text(
        "# comment\n*.log\n\nfrontend/.tmp-tests/\n",
        encoding="utf-8",
    )

    assert hygiene.missing_policy_rules(
        policy_path,
        frozenset(
            {
                "*.log",
                "*.tsbuildinfo",
                "frontend/.tmp-tests/",
            }
        ),
    ) == ["*.tsbuildinfo"]
