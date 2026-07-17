import re
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.routing import APIRoute

from app.main import app


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
README_PATH = REPOSITORY_ROOT / "README.md"
DESKTOP_README_PATH = REPOSITORY_ROOT / "desktop" / "README.md"
ABOUT_PATH = REPOSITORY_ROOT / "ABOUT.md"
MAINTAINED_PUBLIC_DOCUMENTS = (README_PATH, ABOUT_PATH, DESKTOP_README_PATH)
DOCUMENTED_ENDPOINT_PATTERN = re.compile(
    r"^- `(?P<method>GET|POST|PUT|PATCH|DELETE) (?P<path>/[^`]+)`$",
    re.MULTILINE,
)
RETIRED_PRODUCT_LABEL_PATTERN = re.compile(
    r"\b(?:Release Prediction|Predicted outcome|Likely outcome)\b",
    re.IGNORECASE,
)


def _read_document(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _readme_rest_api_section() -> str:
    readme = _read_document(README_PATH)
    section_start = readme.index("## REST API")
    section_end = readme.find("\n## ", section_start + 1)
    return readme[section_start:] if section_end == -1 else readme[section_start:section_end]


def test_readme_endpoint_inventory_matches_fastapi_routes() -> None:
    documented_endpoints = {
        (match.group("method"), match.group("path"))
        for match in DOCUMENTED_ENDPOINT_PATTERN.finditer(_readme_rest_api_section())
    }
    application_endpoints = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }

    missing_from_readme = sorted(application_endpoints - documented_endpoints)
    stale_in_readme = sorted(documented_endpoints - application_endpoints)

    assert not missing_from_readme and not stale_in_readme, (
        "README REST API inventory differs from registered FastAPI routes. "
        f"Missing from README: {missing_from_readme}; stale in README: {stale_in_readme}"
    )


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


def test_public_documents_do_not_restore_retired_product_labels() -> None:
    violations = [
        f"{path.relative_to(REPOSITORY_ROOT)}: {match.group(0)!r}"
        for path in MAINTAINED_PUBLIC_DOCUMENTS
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
