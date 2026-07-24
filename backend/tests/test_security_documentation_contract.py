import ast
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _acceptance_matrix() -> tuple[tuple[object, ...], ...]:
    source_path = Path(__file__).with_name("test_deployment_acceptance_matrix.py")
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    for statement in module.body:
        if isinstance(statement, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "ACCEPTANCE_MATRIX" for target in statement.targets):
                value = ast.literal_eval(statement.value)
                assert isinstance(value, tuple)
                return value
    raise AssertionError("ACCEPTANCE_MATRIX must remain explicit and literal")


def test_documented_deployment_matrix_matches_the_executable_scenarios() -> None:
    matrix = _acceptance_matrix()
    assert matrix == (
        ("desktop-prod", "desktop", "prod", "127.0.0.1", True, "direct"),
        ("local-dev-anonymous", "local-browser", "dev", "127.0.0.1", False, "none"),
        ("local-test-anonymous", "local-browser", "test", "localhost", False, "none"),
        ("local-dev-token", "local-browser", "dev", "127.0.0.1", True, "direct"),
        ("local-test-token", "local-browser", "test", "localhost", True, "direct"),
        ("local-prod", "local-browser", "prod", "127.0.0.1", True, "direct"),
        ("local-non-loopback", "local-browser", "dev", "192.0.2.10", True, "direct"),
        ("docker-prod", "docker", "prod", "0.0.0.0", True, "file"),
    )

    rules = (REPOSITORY_ROOT / "PRODUCT_RULES.md").read_text(encoding="utf-8")
    phase_section = rules.split(
        "## Deployment-Mode Authentication and Configuration-Write Tests",
        maxsplit=1,
    )[1].split("## Change Control", maxsplit=1)[0]
    expected_rows = (
        "| Desktop | Production, loopback | Token always required except `/health` |",
        "| Local browser | `dev` or `test`, loopback, no configured token | Anonymous access allowed |",
        "| Local browser | `dev` or `test`, loopback, configured token | Token required |",
        "| Local browser | Production, loopback | Token required |",
        "| Local browser | Any non-loopback binding | Token required |",
        "| Docker | Every supported configuration | Token required |",
    )
    for expected_row in expected_rows:
        assert expected_row in phase_section


def test_security_verification_command_is_documented_and_release_required() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    package = json.loads((REPOSITORY_ROOT / "desktop" / "package.json").read_text(encoding="utf-8"))

    assert "npm run verify:security" in readme
    assert "LIGHTHOUSE_REQUIRE_DOCKER_SECURITY=1" in readme
    assert package["scripts"]["release:windows"].startswith("npm run verify:security &&")
