import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

from dotenv import dotenv_values
import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REQUIRE_DOCKER_ENV = "LIGHTHOUSE_REQUIRE_DOCKER_SECURITY"


def _docker_available(docker: str) -> tuple[bool, str]:
    result = subprocess.run(
        [docker, "info", "--format", "{{.ServerVersion}}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode == 0, f"{result.stdout}\n{result.stderr}".strip()


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _request(
    url: str,
    *,
    api_token: str | None = None,
    method: str = "GET",
    payload: dict[str, object] | None = None,
) -> tuple[int, dict[str, str], str]:
    headers = {}
    if api_token is not None:
        headers["Authorization"] = f"Bearer {api_token}"
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            headers = {key.casefold(): value for key, value in response.headers.items()}
            return response.status, headers, response.read().decode("utf-8")
    except HTTPError as exc:
        headers = {key.casefold(): value for key, value in exc.headers.items()}
        return exc.code, headers, exc.read().decode("utf-8")


def _wait_for_health(
    url: str,
    *,
    compose: list[str],
    environment: dict[str, str],
    timeout_seconds: float = 120.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            status, _, body = _request(url)
            if status == 200 and json.loads(body).get("status") == "ok":
                return
        except (OSError, URLError, json.JSONDecodeError):
            pass

        exited_backend = subprocess.run(
            [*compose, "ps", "--status", "exited", "--quiet", "backend"],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if exited_backend.returncode == 0 and exited_backend.stdout.strip():
            raise RuntimeError("Docker backend exited before becoming healthy")
        time.sleep(0.5)
    raise TimeoutError("Docker backend did not become healthy before the acceptance deadline")


def _redact_output(output: str, secret_values: tuple[str, ...]) -> str:
    redacted = output
    for secret_value in secret_values:
        redacted = redacted.replace(secret_value, "[REDACTED]")
    return redacted[-12000:]


@pytest.mark.docker
def test_isolated_docker_authentication_and_configuration_security(tmp_path: Path) -> None:
    required = os.environ.get(REQUIRE_DOCKER_ENV) == "1"
    docker = shutil.which("docker")
    if docker is None:
        message = "Docker CLI is unavailable"
        if required:
            pytest.fail(message)
        pytest.skip(message)

    available, availability_detail = _docker_available(docker)
    if not available:
        message = f"Docker daemon is unavailable: {availability_detail}"
        if required:
            pytest.fail(message)
        pytest.skip(message)

    config_directory = tmp_path / "config"
    secrets_directory = tmp_path / "secrets"
    config_directory.mkdir()
    secrets_directory.mkdir()
    config_file = config_directory / "backend.env"
    config_file.write_text("JIRA_SYNC_ENABLED=false\n", encoding="utf-8")
    api_token = "synthetic-runtime-api-token"
    postgres_password = "synthetic-runtime-postgres-password"
    rejected_jira_token = "synthetic-runtime-rejected-jira-token"
    api_token_file = secrets_directory / "api-token"
    postgres_password_file = secrets_directory / "postgres-password"
    api_token_file.write_text(api_token, encoding="utf-8")
    postgres_password_file.write_text(postgres_password, encoding="utf-8")

    backend_port = _free_loopback_port()
    project_name = f"lighthousepm_security_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    environment = {
        **os.environ,
        "LIGHTHOUSE_CONFIG_DIR": str(config_directory),
        "LIGHTHOUSE_API_TOKEN_FILE": str(api_token_file),
        "POSTGRES_PASSWORD_FILE": str(postgres_password_file),
        "LIGHTHOUSE_BACKEND_PORT": str(backend_port),
    }
    compose = [docker, "compose", "-p", project_name]
    secret_values = (api_token, postgres_password, rejected_jira_token)

    try:
        startup = subprocess.run(
            [*compose, "up", "-d", "--build"],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=300,
        )
        startup_output = f"{startup.stdout}\n{startup.stderr}"
        assert startup.returncode == 0, _redact_output(startup_output, secret_values)

        base_url = f"http://127.0.0.1:{backend_port}"
        _wait_for_health(
            f"{base_url}/health",
            compose=compose,
            environment=environment,
        )

        health_status, _, health_body = _request(f"{base_url}/health")
        anonymous_status, anonymous_headers, anonymous_body = _request(
            f"{base_url}/config/jira"
        )
        authorized_status, _, authorized_body = _request(
            f"{base_url}/config/jira",
            api_token=api_token,
        )
        rejected_status, rejected_headers, rejected_body = _request(
            f"{base_url}/config/jira",
            api_token=api_token,
            method="PUT",
            payload={"jira_api_token": rejected_jira_token},
        )
        nonsecret_status, nonsecret_headers, nonsecret_body = _request(
            f"{base_url}/config/jira",
            api_token=api_token,
            method="PUT",
            payload={"jira_project_key": "DOCKER-SMOKE"},
        )

        assert health_status == 200
        assert set(json.loads(health_body)) == {"status", "service", "environment"}
        assert anonymous_status == 401
        assert json.loads(anonymous_body) == {"detail": "API authentication failed."}
        assert anonymous_headers["cache-control"] == "no-store"
        assert authorized_status == 200
        assert json.loads(authorized_body)["jira_api_token_configured"] is False
        assert rejected_status == 400
        assert rejected_headers["cache-control"] == "no-store"
        assert "JIRA_API_TOKEN or JIRA_API_TOKEN_FILE" in json.loads(rejected_body)["detail"]
        assert rejected_jira_token not in rejected_body
        assert nonsecret_status == 200
        assert nonsecret_headers["cache-control"] == "no-store"
        assert json.loads(nonsecret_body)["jira_project_key"] == "DOCKER-SMOKE"
        persisted_config = dotenv_values(config_file)
        assert persisted_config["JIRA_PROJECT_KEY"] == "DOCKER-SMOKE"

        combined_responses = (
            health_body
            + anonymous_body
            + authorized_body
            + rejected_body
            + nonsecret_body
        )
        for secret_value in secret_values:
            assert secret_value not in combined_responses
        assert "LIGHTHOUSE_API_TOKEN" not in persisted_config
        assert "JIRA_API_TOKEN" not in persisted_config
        assert "POSTGRES_PASSWORD" not in persisted_config
    except Exception as exc:
        logs = subprocess.run(
            [*compose, "logs", "--no-color"],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        detail = _redact_output(f"{logs.stdout}\n{logs.stderr}", secret_values)
        raise AssertionError(f"{exc}\nDocker logs:\n{detail}") from exc
    finally:
        subprocess.run(
            [*compose, "down", "--volumes", "--remove-orphans", "--rmi", "local"],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
        )
