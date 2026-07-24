"""Desktop entry point for the packaged LighthousePM backend."""

import argparse
import json
import os
from pathlib import Path
from typing import Sequence


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the LighthousePM desktop backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    parser.add_argument("--database-path", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--app-env", choices=("dev", "test", "prod"), default="prod")
    parser.add_argument("--log-level", default="info")
    utilities = parser.add_mutually_exclusive_group()
    utilities.add_argument("--validate-sqlite-backup", type=Path)
    utilities.add_argument("--create-sqlite-backup", type=Path, metavar="SOURCE")
    utilities.add_argument("--validate-env-file", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--migration-backup", action="store_true")
    return parser.parse_args(argv)


def _load_optional_env_file(env_file: Path | None) -> None:
    if env_file is None or not env_file.is_file():
        return

    from dotenv import load_dotenv

    load_dotenv(env_file, override=False)


def _sqlite_url(database_path: Path) -> str:
    resolved_path = database_path.expanduser().resolve()
    return f"sqlite+pysqlite:///{resolved_path.as_posix()}"


def _validate_configuration_file(env_file: Path) -> dict[str, object]:
    path = env_file.expanduser().resolve()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Configuration must be a regular file: {path}")

    path.read_text(encoding="utf-8")
    from dotenv import dotenv_values

    from app.config import Settings

    parsed = dotenv_values(path, encoding="utf-8")
    values = {str(key).casefold(): value for key, value in parsed.items() if key is not None}
    settings = Settings(_env_file=None, **values)
    settings.validate_classification_settings()
    if settings.jira_base_url and not settings.jira_base_url.startswith(("http://", "https://")):
        raise ValueError("JIRA_BASE_URL must start with http:// or https://")
    return {
        "valid": True,
        "status": "VALID",
        "path": str(path),
        "kind": "backend_env",
    }


def _run_utility(args: argparse.Namespace) -> int | None:
    if not any(
        (
            args.validate_sqlite_backup,
            args.create_sqlite_backup,
            args.validate_env_file,
        )
    ):
        return None

    try:
        if args.validate_sqlite_backup is not None:
            from app.db.backup_validation import (
                migration_target_from_filename,
                validate_sqlite_backup,
            )
            from app.db.migration_graph import installed_revision_chain

            target_revision = None
            if args.migration_backup:
                target_revision = migration_target_from_filename(args.validate_sqlite_backup)
            result = validate_sqlite_backup(
                args.validate_sqlite_backup,
                installed_revision_chain(),
                target_revision=target_revision,
                require_target_in_filename=args.migration_backup,
            ).as_dict()
        elif args.create_sqlite_backup is not None:
            if args.output_path is None:
                raise ValueError("--output-path is required with --create-sqlite-backup")
            from app.db.backup_validation import create_standalone_sqlite_backup
            from app.db.migration_graph import installed_revision_chain

            result = create_standalone_sqlite_backup(
                args.create_sqlite_backup,
                args.output_path,
                installed_revision_chain(),
            ).as_dict()
        else:
            result = _validate_configuration_file(args.validate_env_file)
    except Exception as exc:
        from app.db.backup_validation import BackupValidationError

        if isinstance(exc, BackupValidationError):
            result = exc.as_dict()
        else:
            result = {
                "valid": False,
                "status": "INVALID",
                "path": str(
                    args.validate_sqlite_backup
                    or args.create_sqlite_backup
                    or args.validate_env_file
                    or ""
                ),
                "rule": "utility",
                "detail": str(exc),
            }
        print(json.dumps(result, sort_keys=True))
        return 2

    print(json.dumps(result, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    utility_status = _run_utility(args)
    if utility_status is not None:
        return utility_status

    if args.port is None or args.database_path is None:
        raise SystemExit("--port and --database-path are required when starting the backend server")

    _load_optional_env_file(args.env_file)

    args.database_path.parent.mkdir(parents=True, exist_ok=True)
    config_file = args.env_file or args.database_path.with_name("backend.env")
    os.environ["LIGHTHOUSE_CONFIG_FILE"] = str(config_file.expanduser().resolve())
    os.environ["APP_ENV"] = args.app_env
    os.environ["DEPLOYMENT_MODE"] = "desktop"
    os.environ["APP_HOST"] = args.host
    os.environ["APP_PORT"] = str(args.port)
    os.environ["DATABASE_URL"] = _sqlite_url(args.database_path)
    os.environ["CORS_ORIGINS"] = ""
    os.environ["LOG_LEVEL"] = args.log_level.upper()

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level.casefold(),
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
