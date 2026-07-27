import json
import re
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.metric_catalog import metrics_for_scope


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
README_PATH = REPOSITORY_ROOT / "README.md"
DESKTOP_README_PATH = REPOSITORY_ROOT / "desktop" / "README.md"
ABOUT_PATH = REPOSITORY_ROOT / "ABOUT.md"
HELPER_PATH = REPOSITORY_ROOT / "HELPER.md"
UNIT_TEST_DOCS_PATH = REPOSITORY_ROOT / "UNIT_TEST_DOCS.md"
AGENTS_PATH = REPOSITORY_ROOT / "AGENTS.md"
ABOUT_PANEL_PATH = (
    REPOSITORY_ROOT / "frontend" / "src" / "pages" / "AboutKnowledgePanel.tsx"
)
MAINTAINED_PUBLIC_DOCUMENTS = (README_PATH, ABOUT_PATH, DESKTOP_README_PATH)
MAINTAINED_TECHNICAL_DOCUMENTS = (
    README_PATH,
    HELPER_PATH,
    UNIT_TEST_DOCS_PATH,
    ABOUT_PATH,
    AGENTS_PATH,
    DESKTOP_README_PATH,
)
COMMAND_DOCUMENTS = (README_PATH, UNIT_TEST_DOCS_PATH, DESKTOP_README_PATH)
RETIRED_PRODUCT_LABEL_PATTERN = re.compile(
    r"\b(?:Release Prediction|Predicted outcome|Likely outcome)\b",
    re.IGNORECASE,
)
ABOUT_METRIC_HEADING_PATTERN = re.compile(
    r"^#### Metric: (?P<label>.+)$",
    re.MULTILINE,
)
ABOUT_PANEL_METRIC_PATTERN = re.compile(
    r'metric: \{ scope: "(?P<scope>release|sprint)", '
    r'apiField: "(?P<api_field>[a-z][a-z0-9_]*)" \}'
)
METRIC_KEY_PATTERN = re.compile(
    r"\b(?:release|sprint)\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*\b"
)
PYTEST_TARGET_PATTERN = re.compile(
    r"(?<![\w/])(?P<path>(?:backend/)?tests/test_[A-Za-z0-9_*.-]+\.py)"
)
NPM_SCRIPT_PATTERN = re.compile(
    r"\bnpm\s+(?:run\s+(?P<run>[a-z][a-z0-9:-]*)|(?P<direct>test))\b"
)
REPOSITORY_SCRIPT_PATTERN = re.compile(
    r"\b(?P<path>(?:backend|desktop)/scripts/[A-Za-z0-9_.-]+)\b"
)
ALEMBIC_UPGRADE_PATTERN = re.compile(
    r"\balembic\s+upgrade\s+(?P<target>[^\s`\\]+)"
)


def _read_document(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_operational_documents_state_current_alembic_head() -> None:
    config = Config()
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "backend" / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1, f"Expected one Alembic head, found {list(heads)}"

    expected_revision = f"`{heads[0]}`"
    documents_missing_head = [
        str(path.relative_to(REPOSITORY_ROOT))
        for path in (README_PATH, DESKTOP_README_PATH)
        if expected_revision not in _read_document(path)
    ]

    assert not documents_missing_head, (
        f"Current Alembic head {expected_revision} is missing from: {documents_missing_head}"
    )


def test_maintained_documents_do_not_restore_retired_product_labels() -> None:
    violations = [
        f"{path.relative_to(REPOSITORY_ROOT)}: {match.group(0)!r}"
        for path in MAINTAINED_TECHNICAL_DOCUMENTS
        for match in RETIRED_PRODUCT_LABEL_PATTERN.finditer(_read_document(path))
    ]

    assert not violations, f"Retired product labels found: {violations}"


def test_public_documents_use_release_outlook_term() -> None:
    documents_missing_term = [
        str(path.relative_to(REPOSITORY_ROOT))
        for path in MAINTAINED_PUBLIC_DOCUMENTS
        if "Release Outlook" not in _read_document(path)
    ]

    assert not documents_missing_term, (
        f"Canonical 'Release Outlook' term is missing from: {documents_missing_term}"
    )


def test_about_metric_headings_use_current_catalog_labels() -> None:
    about = _read_document(ABOUT_PATH)
    release_section, sprint_section = about.split("\n## Sprints", maxsplit=1)
    headings_by_scope = {
        "release": ABOUT_METRIC_HEADING_PATTERN.findall(release_section),
        "sprint": ABOUT_METRIC_HEADING_PATTERN.findall(sprint_section),
    }

    violations: list[str] = []
    for scope, headings in headings_by_scope.items():
        catalog_labels = {metric.label for metric in metrics_for_scope(scope)}
        unknown_labels = sorted(set(headings) - catalog_labels)
        duplicate_labels = sorted(
            label for label in set(headings) if headings.count(label) > 1
        )
        if unknown_labels:
            violations.append(f"{scope} headings absent from catalog: {unknown_labels}")
        if duplicate_labels:
            violations.append(f"duplicate {scope} headings: {duplicate_labels}")

    assert not violations, "ABOUT metric-label drift: " + "; ".join(violations)


def test_in_app_about_metric_titles_are_catalog_backed() -> None:
    source = _read_document(ABOUT_PANEL_PATH)
    references = ABOUT_PANEL_METRIC_PATTERN.findall(source)
    assert references, "In-app About does not reference catalog-backed metrics"

    catalog_fields = {
        scope: {metric.api_field for metric in metrics_for_scope(scope)}
        for scope in ("release", "sprint")
    }
    unknown = [
        f"{scope}.{api_field}"
        for scope, api_field in references
        if api_field not in catalog_fields[scope]
    ]

    assert not unknown, f"In-app About references unknown catalog metrics: {unknown}"
    assert 'title: "Metric:' not in source


def test_documented_metric_keys_exist_in_current_catalog() -> None:
    catalog_keys = {
        metric.key
        for scope in ("release", "sprint")
        for metric in metrics_for_scope(scope)
    }
    violations = [
        f"{path.relative_to(REPOSITORY_ROOT)}: {metric_key}"
        for path in MAINTAINED_TECHNICAL_DOCUMENTS
        for metric_key in METRIC_KEY_PATTERN.findall(_read_document(path))
        if metric_key not in catalog_keys
    ]

    assert not violations, f"Documented metric keys absent from catalog: {violations}"


def test_documents_keep_metric_threshold_authority_catalog_backed() -> None:
    required_statements = {
        README_PATH: (
            "PRODUCT_RULES.md`](PRODUCT_RULES.md) is the source of truth for formulas,",
            "backend/app/metric_catalog.py`](backend/app/metric_catalog.py) is the",
        ),
        ABOUT_PATH: (
            "thresholds, and availability boundaries shown by the application "
            "come from the versioned metric catalog",
            "`PRODUCT_RULES.md` remains the detailed product authority",
        ),
        HELPER_PATH: (
            "Clients should consume this endpoint instead of maintaining competing",
            "metric labels or thresholds",
        ),
        AGENTS_PATH: (
            "`PRODUCT_RULES.md` is the normative authority for product behavior, "
            "metric formulas, thresholds",
            "`backend/app/metric_catalog.py` is the machine-readable "
            "implementation authority",
        ),
    }
    violations = [
        f"{path.relative_to(REPOSITORY_ROOT)}: missing {statement!r}"
        for path, statements in required_statements.items()
        for statement in statements
        if statement not in _read_document(path)
    ]

    assert not violations, "Metric-threshold authority drift: " + "; ".join(violations)


def test_documented_pytest_targets_exist() -> None:
    violations: list[str] = []
    for document_path in COMMAND_DOCUMENTS:
        for match in PYTEST_TARGET_PATTERN.finditer(_read_document(document_path)):
            documented_path = match.group("path")
            repository_pattern = (
                documented_path
                if documented_path.startswith("backend/")
                else f"backend/{documented_path}"
            )
            if not list(REPOSITORY_ROOT.glob(repository_pattern)):
                violations.append(
                    f"{document_path.relative_to(REPOSITORY_ROOT)}: {documented_path}"
                )

    assert not violations, f"Documented pytest targets do not exist: {violations}"


def test_documented_npm_scripts_exist() -> None:
    package_scripts = {
        "frontend": set(
            json.loads(
                (REPOSITORY_ROOT / "frontend" / "package.json").read_text(
                    encoding="utf-8"
                )
            )["scripts"]
        ),
        "desktop": set(
            json.loads(
                (REPOSITORY_ROOT / "desktop" / "package.json").read_text(
                    encoding="utf-8"
                )
            )["scripts"]
        ),
    }
    violations: list[str] = []
    for document_path in COMMAND_DOCUMENTS:
        allowed_scripts = (
            package_scripts["desktop"]
            if document_path == DESKTOP_README_PATH
            else package_scripts["frontend"] | package_scripts["desktop"]
        )
        for match in NPM_SCRIPT_PATTERN.finditer(_read_document(document_path)):
            script_name = match.group("run") or match.group("direct")
            if script_name not in allowed_scripts:
                violations.append(
                    f"{document_path.relative_to(REPOSITORY_ROOT)}: npm run {script_name}"
                )

    assert not violations, f"Documented npm scripts do not exist: {violations}"


def test_documented_repository_scripts_exist() -> None:
    violations = [
        f"{document_path.relative_to(REPOSITORY_ROOT)}: {script_path}"
        for document_path in MAINTAINED_TECHNICAL_DOCUMENTS
        for script_path in REPOSITORY_SCRIPT_PATTERN.findall(
            _read_document(document_path)
        )
        if not (REPOSITORY_ROOT / script_path).is_file()
    ]

    assert not violations, f"Documented repository scripts do not exist: {violations}"


def test_documented_manual_migrations_target_current_head() -> None:
    documented_targets = [
        (document_path.relative_to(REPOSITORY_ROOT), match.group("target"))
        for document_path in COMMAND_DOCUMENTS
        for match in ALEMBIC_UPGRADE_PATTERN.finditer(_read_document(document_path))
    ]
    assert documented_targets, "No manual Alembic upgrade command is documented"

    stale_targets = [
        f"{document_path}: alembic upgrade {target}"
        for document_path, target in documented_targets
        if target != "head"
    ]
    assert not stale_targets, (
        "Documented Alembic upgrades must target the current head: "
        f"{stale_targets}"
    )
