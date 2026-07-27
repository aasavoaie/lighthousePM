import ast
import inspect
from pathlib import Path

import pytest

from app.repositories.release_repository import ReleaseRepository
from app.repositories.sprint_repository import SprintRepository
from app.services.application_errors import ApplicationNotFoundError
from app.services.release_metrics_response_service import ReleaseMetricsResponseService
from app.services.release_signal_response_service import ReleaseSignalResponseService
from app.services.sprint_response_service import SprintResponseService


API_DIRECTORY = Path(__file__).resolve().parents[1] / "app" / "api"
ROUTE_SERVICE_NAMES = {
    "metrics.py": "ReleaseMetricsResponseService",
    "signals.py": "ReleaseSignalResponseService",
    "sprints.py": "SprintResponseService",
}


@pytest.mark.parametrize(("filename", "service_name"), ROUTE_SERVICE_NAMES.items())
def test_response_routes_depend_only_on_their_application_service(
    filename: str,
    service_name: str,
) -> None:
    source = (API_DIRECTORY / filename).read_text(encoding="utf-8")
    module = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert not any(module_name.startswith("app.repositories") for module_name in imported_modules)
    assert "app.services.analytics_service" not in imported_modules
    assert "app.services.metric_availability_service" not in imported_modules
    assert "app.services.snapshot_comparison_service" not in imported_modules
    assert "app.services.recommendation_engine" not in imported_modules

    route_functions = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id == "router"
            for decorator in node.decorator_list
        )
    ]
    assert route_functions
    for route_function in route_functions:
        expected_service_name = (
            "MetricRecomputeService"
            if route_function.name.startswith("recompute_")
            else service_name
        )
        assert any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == expected_service_name
            for node in ast.walk(route_function)
        ), f"{filename}:{route_function.name} must delegate to {expected_service_name}"


def test_response_services_require_explicit_time_for_time_dependent_assembly() -> None:
    release_parameters = inspect.signature(
        ReleaseMetricsResponseService.get_metrics
    ).parameters
    sprint_metric_parameters = inspect.signature(
        SprintResponseService.get_sprint_metrics
    ).parameters
    sprint_issue_parameters = inspect.signature(
        SprintResponseService.get_sprint_issues
    ).parameters

    assert release_parameters["current_time"].default is inspect.Parameter.empty
    assert sprint_metric_parameters["current_time"].default is inspect.Parameter.empty
    assert sprint_issue_parameters["current_time"].default is inspect.Parameter.empty

    for service_type in (ReleaseMetricsResponseService, SprintResponseService):
        assert "datetime.now(" not in inspect.getsource(service_type)


def test_release_service_reports_missing_release_without_http_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ReleaseRepository,
        "get_release_by_id",
        lambda **_kwargs: None,
    )

    with pytest.raises(ApplicationNotFoundError, match="Release 'MISSING' not found"):
        ReleaseMetricsResponseService().get_snapshot_change_history(
            session=object(),
            release_id="MISSING",
            limit=10,
        )


def test_release_signal_service_reports_missing_release_without_http_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ReleaseRepository,
        "get_release_by_id",
        lambda **_kwargs: None,
    )

    with pytest.raises(ApplicationNotFoundError, match="Release 'MISSING' not found"):
        ReleaseSignalResponseService().get_signal(
            session=object(),
            release_id="MISSING",
        )


def test_sprint_service_reports_missing_sprint_without_http_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        SprintRepository,
        "get_sprint_by_id",
        lambda **_kwargs: None,
    )

    with pytest.raises(ApplicationNotFoundError, match="Sprint 'MISSING' not found"):
        SprintResponseService().get_sprint(
            session=object(),
            sprint_id="MISSING",
        )


def test_sprint_service_assembles_empty_current_sprint_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        SprintRepository,
        "get_current_sprint",
        lambda **_kwargs: None,
    )

    response = SprintResponseService().get_current_sprint(
        session=object(),
        project_key="LHPM",
    )

    assert response.item is None
