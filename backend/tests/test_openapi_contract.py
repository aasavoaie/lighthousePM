import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from fastapi.routing import APIRoute
from fastapi.security.base import SecurityBase

from app.main import app
from app.security import RouteSecurityClass, route_security_class


APPLICATION_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
BUILT_IN_PATHS = {
    "/docs",
    "/docs/oauth2-redirect",
    "/openapi.json",
    "/redoc",
}
PATH_PARAMETER_PATTERN = re.compile(r"\{(?P<name>[^{}]+)\}")
README_ENDPOINT_PATTERN = re.compile(
    r"^- `(?P<method>GET|POST|PUT|PATCH|DELETE) (?P<path>/[^`\s]+)`$"
)
HELPER_ENDPOINT_PATTERN = re.compile(
    r"^### `(?P<method>GET|POST|PUT|PATCH|DELETE) (?P<path>/[^`\s]+)`$"
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
README_PATH = REPOSITORY_ROOT / "README.md"
HELPER_PATH = REPOSITORY_ROOT / "HELPER.md"
APPLICATION_TAGS = {
    "admin",
    "configuration",
    "health",
    "issues",
    "metadata",
    "metrics",
    "releases",
    "reports",
    "signals",
    "sprints",
    "sync",
}
PDF_OPERATIONS = {
    ("GET", "/reports/documentation.pdf"),
    ("GET", "/releases/{release_id}/reports/overview.pdf"),
    ("GET", "/releases/{release_id}/reports/{depth}.pdf"),
    ("GET", "/sprints/{sprint_id}/reports/{depth}.pdf"),
}
CONTROLLED_ERROR_STATUSES = {
    ("PUT", "/config/jira"): {400},
    ("POST", "/config/jira/test"): {400},
    ("GET", "/issues/{jira_key}"): {404},
    ("GET", "/releases/{release_id}"): {404},
    ("GET", "/releases/{release_id}/issues"): {404},
    ("GET", "/releases/{release_id}/metrics"): {404},
    ("GET", "/releases/{release_id}/charts"): {400, 404},
    ("GET", "/releases/{release_id}/snapshot-comparison"): {404},
    ("GET", "/releases/{release_id}/snapshot-change-history"): {404},
    ("POST", "/releases/{release_id}/recompute"): {404},
    ("GET", "/releases/{release_id}/signal"): {404},
    ("GET", "/reports/documentation.pdf"): {404},
    ("GET", "/releases/{release_id}/reports/overview.pdf"): {404},
    ("GET", "/releases/{release_id}/reports/{depth}.pdf"): {404},
    ("GET", "/sprints/{sprint_id}/reports/{depth}.pdf"): {404},
    ("GET", "/sprints/{sprint_id}"): {404},
    ("GET", "/sprints/{sprint_id}/issues"): {404},
    ("GET", "/sprints/{sprint_id}/metrics"): {404},
    ("GET", "/sprints/{sprint_id}/snapshot-comparison"): {404},
    ("GET", "/sprints/{sprint_id}/snapshot-change-history"): {404},
    ("POST", "/sprints/{sprint_id}/recompute"): {404},
    ("POST", "/sync/jira"): {400, 401, 409},
}


def _application_operations() -> list[tuple[str, APIRoute]]:
    operations: list[tuple[str, APIRoute]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        for method in sorted(route.methods & APPLICATION_METHODS):
            operations.append((method, route))
    return operations


def _runtime_security_dependencies(route: APIRoute) -> list[str]:
    security_dependencies: list[str] = []
    pending = [route.dependant]
    visited: set[int] = set()
    while pending:
        dependant = pending.pop()
        if id(dependant) in visited:
            continue
        visited.add(id(dependant))
        dependency_call = getattr(dependant, "call", None)
        if isinstance(dependency_call, SecurityBase):
            security_dependencies.append(type(dependency_call).__name__)
        pending.extend(getattr(dependant, "dependencies", ()))
    return security_dependencies


def _openapi_operations(openapi: dict[str, Any]) -> list[tuple[str, str]]:
    operations: list[tuple[str, str]] = []
    for path, path_item in openapi["paths"].items():
        for method in path_item:
            normalized_method = method.upper()
            if normalized_method in APPLICATION_METHODS:
                operations.append((normalized_method, path))
    return operations


def _readme_api_section() -> tuple[int, list[str]]:
    lines = README_PATH.read_text(encoding="utf-8").splitlines()
    heading_indexes = [
        index for index, line in enumerate(lines) if line == "## REST API"
    ]
    assert len(heading_indexes) == 1, (
        "README.md must contain exactly one '## REST API' inventory section; "
        f"found {len(heading_indexes)}"
    )
    section_start = heading_indexes[0]
    section_end = next(
        (
            index
            for index in range(section_start + 1, len(lines))
            if lines[index].startswith("## ")
        ),
        len(lines),
    )
    return section_start + 2, lines[section_start + 1 : section_end]


def _documented_endpoint_inventory(
    *,
    document_path: Path,
    lines: list[str],
    first_line_number: int,
    candidate_prefix: str,
    pattern: re.Pattern[str],
) -> tuple[list[tuple[str, str]], list[str]]:
    operations: list[tuple[str, str]] = []
    malformed: list[str] = []
    for offset, line in enumerate(lines):
        if not line.startswith(candidate_prefix):
            continue
        match = pattern.fullmatch(line)
        if match is None:
            malformed.append(
                f"{document_path.name}:{first_line_number + offset}: {line!r}"
            )
            continue
        operations.append((match.group("method"), match.group("path")))
    return operations, malformed


def _path_parameter_mismatches(
    *,
    expected: set[tuple[str, str]],
    documented: set[tuple[str, str]],
) -> list[str]:
    expected_by_shape = {
        (method, PATH_PARAMETER_PATTERN.sub("{}", path)): path
        for method, path in expected
    }
    documented_by_shape = {
        (method, PATH_PARAMETER_PATTERN.sub("{}", path)): path
        for method, path in documented
    }
    mismatches: list[str] = []
    for route_shape in sorted(expected_by_shape.keys() & documented_by_shape.keys()):
        expected_path = expected_by_shape[route_shape]
        documented_path = documented_by_shape[route_shape]
        if expected_path == documented_path:
            continue
        mismatches.append(
            f"expected {expected_path}, found {documented_path}"
        )
    return mismatches


def test_application_operations_have_stable_identity_and_presentation() -> None:
    operations = _application_operations()
    assert operations, "No application operations were registered"

    violations: list[str] = []
    operation_locations: dict[str, list[str]] = defaultdict(list)
    observed_tags: set[str] = set()
    for method, route in operations:
        location = f"{method} {route.path}"
        if route.operation_id != route.endpoint.__name__:
            violations.append(
                f"{location}: operation_id must be explicit and match handler "
                f"{route.endpoint.__name__!r}; found {route.operation_id!r}"
            )
        else:
            operation_locations[route.operation_id].append(location)

        if not isinstance(route.summary, str) or not route.summary.strip():
            violations.append(f"{location}: missing explicit summary")

        if len(route.tags) != 1 or route.tags[0] not in APPLICATION_TAGS:
            violations.append(
                f"{location}: expected one approved tag; found {route.tags!r}"
            )
        else:
            observed_tags.add(route.tags[0])

    duplicate_ids = {
        operation_id: locations
        for operation_id, locations in operation_locations.items()
        if len(locations) > 1
    }
    if duplicate_ids:
        violations.append(f"duplicate operation IDs: {duplicate_ids}")
    if observed_tags != APPLICATION_TAGS:
        violations.append(
            "application tag inventory differs: "
            f"missing={sorted(APPLICATION_TAGS - observed_tags)}, "
            f"unexpected={sorted(observed_tags - APPLICATION_TAGS)}"
        )

    assert not violations, "OpenAPI operation identity drift: " + "; ".join(violations)


def test_openapi_exposes_explicit_operation_identity_and_presentation() -> None:
    openapi = app.openapi()
    violations: list[str] = []
    for method, route in _application_operations():
        location = f"{method} {route.path}"
        operation = openapi["paths"][route.path][method.lower()]
        expected = {
            "operationId": route.operation_id,
            "summary": route.summary,
            "tags": route.tags,
        }
        actual = {key: operation.get(key) for key in expected}
        if actual != expected:
            violations.append(
                f"{location}: expected {expected!r}; found {actual!r}"
            )

    assert not violations, "Generated OpenAPI operation metadata drift: " + "; ".join(
        violations
    )


def test_openapi_success_content_matches_operation_type() -> None:
    openapi = app.openapi()
    violations: list[str] = []
    for method, route in _application_operations():
        route_key = (method, route.path)
        location = f"{method} {route.path}"
        success_response = openapi["paths"][route.path][method.lower()]["responses"][
            "200"
        ]
        success_content = success_response.get("content", {})
        if route_key in PDF_OPERATIONS:
            if route.response_model is not None:
                violations.append(f"{location}: PDF operation has a response model")
            if set(success_content) != {"application/pdf"}:
                violations.append(
                    f"{location}: expected only application/pdf; "
                    f"found {sorted(success_content)}"
                )
        else:
            if route.response_model is None:
                violations.append(f"{location}: JSON operation has no response model")
            if "application/json" not in success_content:
                violations.append(
                    f"{location}: missing application/json success content"
                )
            elif not success_content["application/json"].get("schema"):
                violations.append(f"{location}: missing JSON success schema")

    assert not violations, "OpenAPI success-response drift: " + "; ".join(violations)


def test_controlled_error_response_inventory_matches_routes() -> None:
    openapi = app.openapi()
    violations: list[str] = []
    observed_error_routes: set[tuple[str, str]] = set()
    for method, route in _application_operations():
        route_key = (method, route.path)
        location = f"{method} {route.path}"
        explicit_statuses = {
            int(status_code)
            for status_code in route.responses
            if int(status_code) != 200
        }
        expected_statuses = CONTROLLED_ERROR_STATUSES.get(route_key, set())
        if explicit_statuses != expected_statuses:
            violations.append(
                f"{location}: expected controlled errors "
                f"{sorted(expected_statuses)}; found {sorted(explicit_statuses)}"
            )
        if expected_statuses:
            observed_error_routes.add(route_key)

        openapi_responses = openapi["paths"][route.path][method.lower()]["responses"]
        for status_code in sorted(expected_statuses):
            response = openapi_responses.get(str(status_code), {})
            schema = response.get("content", {}).get("application/json", {}).get(
                "schema", {}
            )
            if schema.get("$ref") != "#/components/schemas/ApiErrorResponse":
                violations.append(
                    f"{location}: {status_code} does not use ApiErrorResponse"
                )
            if not response.get("description", "").strip():
                violations.append(
                    f"{location}: {status_code} has no response description"
                )

    if observed_error_routes != set(CONTROLLED_ERROR_STATUSES):
        violations.append(
            "controlled-error route inventory differs: "
            f"missing={sorted(set(CONTROLLED_ERROR_STATUSES) - observed_error_routes)}, "
            f"unexpected={sorted(observed_error_routes - set(CONTROLLED_ERROR_STATUSES))}"
        )

    assert not violations, "OpenAPI controlled-error drift: " + "; ".join(violations)


def test_validation_capable_operations_document_422() -> None:
    openapi = app.openapi()
    violations: list[str] = []
    for method, route in _application_operations():
        has_request_values = bool(
            route.dependant.path_params
            or route.dependant.query_params
            or route.dependant.body_params
        )
        responses = openapi["paths"][route.path][method.lower()]["responses"]
        has_validation_response = "422" in responses
        if has_validation_response != has_request_values:
            violations.append(
                f"{method} {route.path}: expected 422={has_request_values}; "
                f"found {has_validation_response}"
            )

    assert not violations, "OpenAPI validation-response drift: " + "; ".join(
        violations
    )


def test_openapi_security_matches_central_route_classification() -> None:
    openapi = app.openapi()
    expected_scheme = {
        "type": "http",
        "scheme": "bearer",
        "description": (
            "LighthousePM API token required whenever authentication is enabled "
            "for the active deployment mode."
        ),
    }
    assert openapi["components"]["securitySchemes"] == {
        "BearerAuth": expected_scheme
    }

    violations: list[str] = []
    public_operations: set[tuple[str, str]] = set()
    for method, route in _application_operations():
        route_key = (method, route.path)
        location = f"{method} {route.path}"
        operation = openapi["paths"][route.path][method.lower()]
        security_class = route_security_class(route_key)
        if security_class == RouteSecurityClass.PUBLIC_HEALTH:
            public_operations.add(route_key)
            if operation.get("security"):
                violations.append(f"{location}: public operation declares security")
            if "401" in operation["responses"]:
                violations.append(f"{location}: public operation documents 401")
            continue

        if operation.get("security") != [{"BearerAuth": []}]:
            violations.append(
                f"{location}: expected BearerAuth; found {operation.get('security')!r}"
            )
        authentication_response = operation["responses"].get("401", {})
        authentication_schema = (
            authentication_response.get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        if authentication_schema.get("$ref") != (
            "#/components/schemas/ApiErrorResponse"
        ):
            violations.append(f"{location}: 401 does not use ApiErrorResponse")
        if not authentication_response.get("description", "").strip():
            violations.append(f"{location}: 401 has no response description")

    if public_operations != {("GET", "/health")}:
        violations.append(
            f"public OpenAPI operation inventory differs: {sorted(public_operations)}"
        )

    assert not violations, "OpenAPI route-security drift: " + "; ".join(violations)


def test_openapi_security_does_not_add_runtime_auth_dependencies() -> None:
    violations = []
    for method, route in _application_operations():
        security_dependencies = _runtime_security_dependencies(route)
        if security_dependencies:
            violations.append(
                f"{method} {route.path}: unexpected security dependencies "
                f"{security_dependencies}"
            )

    assert not violations, (
        "Authentication must remain centrally enforced by middleware: "
        + "; ".join(violations)
    )


def test_openapi_operation_inventory_matches_registered_application_routes() -> None:
    openapi = app.openapi()
    registered_operations = [
        (method, route.path) for method, route in _application_operations()
    ]
    documented_operations = _openapi_operations(openapi)
    registered_counts = Counter(registered_operations)
    documented_counts = Counter(documented_operations)

    missing = sorted(registered_counts.keys() - documented_counts.keys())
    stale = sorted(documented_counts.keys() - registered_counts.keys())
    duplicate_registered = sorted(
        operation for operation, count in registered_counts.items() if count > 1
    )
    duplicate_documented = sorted(
        operation for operation, count in documented_counts.items() if count > 1
    )

    assert not any((missing, stale, duplicate_registered, duplicate_documented)), (
        "FastAPI/OpenAPI operation inventory differs: "
        f"missing={missing}; stale={stale}; "
        f"duplicate registered={duplicate_registered}; "
        f"duplicate documented={duplicate_documented}"
    )


def test_openapi_path_parameters_match_route_placeholders() -> None:
    openapi = app.openapi()
    violations: list[str] = []
    for method, route in _application_operations():
        location = f"{method} {route.path}"
        path_item = openapi["paths"][route.path]
        operation = path_item[method.lower()]
        parameters = [
            *path_item.get("parameters", []),
            *operation.get("parameters", []),
        ]
        expected_names = PATH_PARAMETER_PATTERN.findall(route.path)
        documented_path_parameters: list[dict[str, object]] = []
        documented_names: list[str] = []
        for index, parameter in enumerate(parameters):
            if not isinstance(parameter, dict):
                violations.append(
                    f"{location}: parameter {index} is not an object"
                )
                continue
            if parameter.get("in") != "path":
                continue
            documented_path_parameters.append(parameter)
            name = parameter.get("name")
            if not isinstance(name, str) or not name:
                violations.append(
                    f"{location}: path parameter {index} has no valid name"
                )
                continue
            documented_names.append(name)

        if Counter(documented_names) != Counter(expected_names):
            missing = sorted(
                (Counter(expected_names) - Counter(documented_names)).elements()
            )
            unexpected = sorted(
                (Counter(documented_names) - Counter(expected_names)).elements()
            )
            duplicates = sorted(
                name
                for name, count in Counter(documented_names).items()
                if count > 1
            )
            violations.append(
                f"{location}: path parameters differ; missing={missing}, "
                f"unexpected={unexpected}, duplicates={duplicates}"
            )

        not_required = sorted(
            str(parameter.get("name"))
            for parameter in documented_path_parameters
            if parameter.get("required") is not True
        )
        if not_required:
            violations.append(
                f"{location}: path parameters are not required: {not_required}"
            )

    assert not violations, "OpenAPI path-parameter drift: " + "; ".join(violations)


def test_openapi_excludes_builtin_and_implicit_operations() -> None:
    openapi = app.openapi()
    documented_paths = set(openapi["paths"])
    included_builtins = sorted(documented_paths & BUILT_IN_PATHS)
    implicit_operations = sorted(
        (method.upper(), path)
        for path, path_item in openapi["paths"].items()
        for method in path_item
        if method.upper() in {"HEAD", "OPTIONS"}
    )

    assert not included_builtins and not implicit_operations, (
        "OpenAPI includes non-application operations: "
        f"built-ins={included_builtins}; implicit={implicit_operations}"
    )


def test_readme_and_helper_endpoint_inventories_match_openapi() -> None:
    openapi_operations = _openapi_operations(app.openapi())
    expected_counts = Counter(openapi_operations)
    readme_first_line, readme_lines = _readme_api_section()
    helper_lines = HELPER_PATH.read_text(encoding="utf-8").splitlines()
    document_inventories = {
        README_PATH: _documented_endpoint_inventory(
            document_path=README_PATH,
            lines=readme_lines,
            first_line_number=readme_first_line,
            candidate_prefix="- ",
            pattern=README_ENDPOINT_PATTERN,
        ),
        HELPER_PATH: _documented_endpoint_inventory(
            document_path=HELPER_PATH,
            lines=helper_lines,
            first_line_number=1,
            candidate_prefix="### ",
            pattern=HELPER_ENDPOINT_PATTERN,
        ),
    }

    violations: list[str] = []
    for document_path, (operations, malformed) in document_inventories.items():
        documented_counts = Counter(operations)
        missing = sorted(expected_counts.keys() - documented_counts.keys())
        stale = sorted(documented_counts.keys() - expected_counts.keys())
        duplicates = sorted(
            operation
            for operation, count in documented_counts.items()
            if count > 1
        )
        parameter_mismatches = _path_parameter_mismatches(
            expected=set(expected_counts),
            documented=set(documented_counts),
        )
        if any((missing, stale, duplicates, malformed, parameter_mismatches)):
            violations.append(
                f"{document_path.name}: missing={missing}; stale={stale}; "
                f"duplicates={duplicates}; malformed={malformed}; "
                f"path parameter mismatches={parameter_mismatches}"
            )

    assert not violations, "Endpoint documentation drift: " + " | ".join(violations)
