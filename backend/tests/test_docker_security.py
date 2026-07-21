import os
import re
from pathlib import Path
import shutil
import subprocess

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _service_block(compose: str, service_name: str) -> str:
    lines = compose.splitlines()
    start = lines.index(f"  {service_name}:")
    block = [lines[start]]
    for line in lines[start + 1 :]:
        if not line.startswith(" ") or (line.startswith("  ") and not line.startswith("    ")):
            break
        block.append(line)
    return "\n".join(block)


def test_compose_mounts_api_token_file_without_embedding_direct_token() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "LIGHTHOUSE_API_TOKEN_FILE: /run/secrets/lighthouse_api_token" in compose
    assert "- lighthouse_api_token" in compose
    assert "file: ${LIGHTHOUSE_API_TOKEN_FILE:?" in compose
    assert re.search(r"^\s+LIGHTHOUSE_API_TOKEN:\s*", compose, flags=re.MULTILINE) is None


def test_compose_mounts_postgres_password_without_embedding_it() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert compose.count("POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password") == 2
    assert compose.count("- postgres_password") == 2
    assert "file: ${POSTGRES_PASSWORD_FILE:?" in compose
    assert "postgresql+psycopg://postgres@postgres:5432/lighthouse" in compose
    assert re.search(r"^\s+POSTGRES_PASSWORD:\s*", compose, flags=re.MULTILINE) is None
    assert "postgres:postgres" not in compose


def test_compose_uses_only_explicit_nonsecret_configuration_file() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    example = (REPOSITORY_ROOT / "backend" / "docker.env.example").read_text(
        encoding="utf-8"
    )

    assert "env_file:" not in compose
    assert "LIGHTHOUSE_CONFIG_FILE: /config/backend.env" in compose
    assert "${LIGHTHOUSE_CONFIG_DIR:?" in compose
    assert ":/config\"" in compose
    assert "TOKEN=" not in example
    assert "PASSWORD=" not in example


def test_jira_compose_override_uses_a_mounted_token_file() -> None:
    override = (REPOSITORY_ROOT / "docker-compose.jira.yml").read_text(encoding="utf-8")

    assert "JIRA_API_TOKEN_FILE: /run/secrets/jira_api_token" in override
    assert "file: ${JIRA_API_TOKEN_FILE:?" in override
    assert re.search(r"^\s+JIRA_API_TOKEN:\s*", override, flags=re.MULTILINE) is None


def test_local_secret_directory_is_ignored_and_documented() -> None:
    gitignore = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")

    assert ".secrets/" in gitignore.splitlines()
    assert ".config/" in gitignore.splitlines()
    assert "LIGHTHOUSE_API_TOKEN_FILE=./.secrets/lighthouse_api_token" in readme
    assert "/run/secrets/lighthouse_api_token" in readme


def test_base_compose_publishes_only_the_backend_on_host_loopback() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    backend = _service_block(compose, "backend")
    postgres = _service_block(compose, "postgres")

    assert '"127.0.0.1:${LIGHTHOUSE_BACKEND_PORT:-8000}:8000"' in backend
    assert "0.0.0.0:${LIGHTHOUSE_BACKEND_PORT" not in backend
    assert "[::]:${LIGHTHOUSE_BACKEND_PORT" not in backend
    assert "ports:" not in postgres
    assert 'expose:\n      - "5432"' in postgres


def test_compose_services_use_project_scoped_network_without_fixed_container_names() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    backend = _service_block(compose, "backend")
    postgres = _service_block(compose, "postgres")

    assert "container_name:" not in compose
    assert "networks:\n      - lighthousepm" in backend
    assert "networks:\n      - lighthousepm" in postgres
    assert "\nnetworks:\n  lighthousepm:\n    driver: bridge" in compose
    assert "external: true" not in compose


def test_docker_cors_default_contains_only_exact_local_origins() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert (
        'CORS_ORIGINS: "${LIGHTHOUSE_CORS_ORIGINS:-'
        'http://127.0.0.1:5173,http://localhost:5173}"'
    ) in compose
    assert "CORS_ORIGINS: \"*\"" not in compose


def test_optional_postgres_override_is_loopback_only() -> None:
    override = (REPOSITORY_ROOT / "docker-compose.postgres-local.yml").read_text(
        encoding="utf-8"
    )

    assert '"127.0.0.1:${LIGHTHOUSE_POSTGRES_PORT:-5432}:5432"' in override
    assert "0.0.0.0:" not in override
    assert "[::]:" not in override


def test_compose_configuration_renders_with_isolated_synthetic_secrets(
    tmp_path: Path,
) -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.fail("Docker CLI with Compose is required for configuration acceptance")

    config_directory = tmp_path / "config"
    secrets_directory = tmp_path / "secrets"
    config_directory.mkdir()
    secrets_directory.mkdir()
    (config_directory / "backend.env").write_text(
        "JIRA_SYNC_ENABLED=false\n",
        encoding="utf-8",
    )
    api_secret = "synthetic-compose-api-secret"
    postgres_secret = "synthetic-compose-postgres-secret"
    jira_secret = "synthetic-compose-jira-secret"
    api_secret_file = secrets_directory / "api-token"
    postgres_secret_file = secrets_directory / "postgres-password"
    jira_secret_file = secrets_directory / "jira-token"
    api_secret_file.write_text(api_secret, encoding="utf-8")
    postgres_secret_file.write_text(postgres_secret, encoding="utf-8")
    jira_secret_file.write_text(jira_secret, encoding="utf-8")

    environment = {
        **os.environ,
        "LIGHTHOUSE_CONFIG_DIR": str(config_directory),
        "LIGHTHOUSE_API_TOKEN_FILE": str(api_secret_file),
        "POSTGRES_PASSWORD_FILE": str(postgres_secret_file),
        "JIRA_API_TOKEN_FILE": str(jira_secret_file),
    }
    commands = (
        [docker, "compose", "-p", "lighthousepm_config_base", "config", "--quiet"],
        [
            docker,
            "compose",
            "-p",
            "lighthousepm_config_all_overrides",
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.jira.yml",
            "-f",
            "docker-compose.postgres-local.yml",
            "config",
            "--quiet",
        ],
    )

    for command in commands:
        result = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = f"{result.stdout}\n{result.stderr}"
        assert result.returncode == 0, output
        assert api_secret not in output
        assert postgres_secret not in output
        assert jira_secret not in output
