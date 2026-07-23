from pathlib import Path
import subprocess

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
