"""Desktop entry point for the packaged LighthousePM backend."""

import argparse
import os
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the LighthousePM desktop backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--database-path", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--app-env", choices=("dev", "test", "prod"), default="prod")
    parser.add_argument("--log-level", default="info")
    return parser.parse_args()


def _load_optional_env_file(env_file: Path | None) -> None:
    if env_file is None or not env_file.is_file():
        return

    from dotenv import load_dotenv

    load_dotenv(env_file, override=False)


def _sqlite_url(database_path: Path) -> str:
    resolved_path = database_path.expanduser().resolve()
    return f"sqlite+pysqlite:///{resolved_path.as_posix()}"


def main() -> None:
    args = _parse_args()
    _load_optional_env_file(args.env_file)

    args.database_path.parent.mkdir(parents=True, exist_ok=True)
    if args.env_file is not None:
        os.environ["LIGHTHOUSE_CONFIG_FILE"] = str(args.env_file.expanduser().resolve())
    os.environ["APP_ENV"] = args.app_env
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


if __name__ == "__main__":
    main()
