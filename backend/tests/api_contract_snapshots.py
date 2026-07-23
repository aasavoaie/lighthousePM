from __future__ import annotations

from dataclasses import dataclass
from difflib import unified_diff
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any


API_CONTRACT_ROOT = Path(__file__).resolve().parent / "contracts" / "api"
API_CONTRACT_UPDATE_ENV = "LIGHTHOUSE_UPDATE_API_CONTRACT_SNAPSHOTS"
MANIFEST_FILENAME = "manifest.json"
_CONTRACT_KEYS = {"id", "method", "path", "status_code", "snapshot"}
_SENSITIVE_KEYS = {
    "api_token",
    "authorization",
    "database_url",
    "jira_api_token",
    "password",
    "postgres_password",
}
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"\bbearer\s+\S+", re.IGNORECASE),
    re.compile(r"\bpostgres(?:ql)?(?:\+\w+)?://", re.IGNORECASE),
    re.compile(r"\bsqlite(?:\+\w+)?:///(?:[/\\]|[A-Za-z]:)", re.IGNORECASE),
    re.compile(r"(?:[A-Za-z]:\\|/(?:home|Users|mnt|tmp|var)/)"),
)


class ApiContractSnapshotError(ValueError):
    """Raised when the committed API contract snapshot set is invalid."""


@dataclass(frozen=True)
class ApiContract:
    contract_id: str
    method: str
    path: str
    status_code: int
    snapshot: str


def render_json(payload: object) -> str:
    """Render a payload in the only accepted snapshot representation."""
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiContractSnapshotError(
            f"Could not read JSON contract file {path}: {exc}"
        ) from exc


def _validate_snapshot_path(value: object) -> str:
    if not isinstance(value, str) or not value.endswith(".json"):
        raise ApiContractSnapshotError(
            "Contract snapshot must be a relative .json path."
        )
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value == MANIFEST_FILENAME:
        raise ApiContractSnapshotError(f"Unsafe contract snapshot path: {value!r}")
    return value


def _iter_payload_items(value: object, path: str = "$"):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield key, child, child_path
            yield from _iter_payload_items(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            yield None, child, child_path
            yield from _iter_payload_items(child, child_path)


def validate_snapshot_payload(payload: object) -> None:
    """Reject secret-bearing fields and machine-local paths from snapshots."""
    for key, value, path in _iter_payload_items(payload):
        if isinstance(key, str) and key.casefold() in _SENSITIVE_KEYS:
            raise ApiContractSnapshotError(f"Sensitive field is not allowed at {path}.")
        if not isinstance(value, str):
            continue
        for pattern in _SENSITIVE_VALUE_PATTERNS:
            if pattern.search(value):
                raise ApiContractSnapshotError(
                    f"Sensitive or local value is not allowed at {path}."
                )


def _parse_contract(entry: object, index: int) -> ApiContract:
    if not isinstance(entry, dict) or set(entry) != _CONTRACT_KEYS:
        raise ApiContractSnapshotError(
            f"Manifest contract {index} must contain exactly {sorted(_CONTRACT_KEYS)}."
        )
    contract_id = entry["id"]
    method = entry["method"]
    path = entry["path"]
    status_code = entry["status_code"]
    if not isinstance(contract_id, str) or not contract_id.strip():
        raise ApiContractSnapshotError(f"Manifest contract {index} has an invalid id.")
    if not isinstance(method, str) or method != method.upper() or not method.isalpha():
        raise ApiContractSnapshotError(
            f"Manifest contract {contract_id!r} has an invalid method."
        )
    if not isinstance(path, str) or not path.startswith("/") or "?" in path:
        raise ApiContractSnapshotError(
            f"Manifest contract {contract_id!r} has an invalid path."
        )
    if isinstance(status_code, bool) or not isinstance(status_code, int):
        raise ApiContractSnapshotError(
            f"Manifest contract {contract_id!r} has an invalid status code."
        )
    return ApiContract(
        contract_id=contract_id,
        method=method,
        path=path,
        status_code=status_code,
        snapshot=_validate_snapshot_path(entry["snapshot"]),
    )


def load_api_contract_manifest(
    root: Path = API_CONTRACT_ROOT,
) -> tuple[ApiContract, ...]:
    """Load and fully validate the committed contract inventory."""
    manifest_path = root / MANIFEST_FILENAME
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, dict) or set(manifest) != {"version", "contracts"}:
        raise ApiContractSnapshotError(
            "API contract manifest must contain exactly 'version' and 'contracts'."
        )
    if manifest["version"] != 1 or not isinstance(manifest["contracts"], list):
        raise ApiContractSnapshotError(
            "API contract manifest version or contracts list is invalid."
        )

    contracts = tuple(
        _parse_contract(entry, index)
        for index, entry in enumerate(manifest["contracts"])
    )
    contract_ids = [contract.contract_id for contract in contracts]
    snapshot_paths = [contract.snapshot for contract in contracts]
    if len(contract_ids) != len(set(contract_ids)):
        raise ApiContractSnapshotError(
            "API contract manifest contains duplicate contract ids."
        )
    if len(snapshot_paths) != len(set(snapshot_paths)):
        raise ApiContractSnapshotError(
            "API contract manifest contains duplicate snapshot files."
        )

    expected_files = set(snapshot_paths)
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*.json")
        if path.name != MANIFEST_FILENAME
    }
    missing_files = sorted(expected_files - actual_files)
    orphaned_files = sorted(actual_files - expected_files)
    if missing_files:
        raise ApiContractSnapshotError(
            f"API contract manifest references missing snapshots: {missing_files}"
        )
    if orphaned_files:
        raise ApiContractSnapshotError(
            f"API contract directory contains orphaned snapshots: {orphaned_files}"
        )

    for contract in contracts:
        snapshot_path = root / contract.snapshot
        payload = _load_json(snapshot_path)
        validate_snapshot_payload(payload)
        if snapshot_path.read_text(encoding="utf-8") != render_json(payload):
            raise ApiContractSnapshotError(
                f"API contract snapshot is not canonically formatted: {contract.snapshot}"
            )
    return contracts


def assert_api_contract_snapshot(
    contract_id: str,
    *,
    status_code: int,
    payload: object,
    root: Path = API_CONTRACT_ROOT,
) -> None:
    """Compare a complete serialized response payload with its committed contract."""
    contracts = load_api_contract_manifest(root)
    contract = next(
        (candidate for candidate in contracts if candidate.contract_id == contract_id),
        None,
    )
    if contract is None:
        raise AssertionError(f"API contract {contract_id!r} is not registered.")
    if status_code != contract.status_code:
        raise AssertionError(
            f"API contract {contract_id!r} expected status {contract.status_code}, "
            f"received {status_code}."
        )

    validate_snapshot_payload(payload)
    expected = (root / contract.snapshot).read_text(encoding="utf-8")
    actual = render_json(payload)
    if (
        os.environ.get(API_CONTRACT_UPDATE_ENV) == "1"
        and root.resolve() == API_CONTRACT_ROOT.resolve()
    ):
        _replace_snapshot_atomically(root / contract.snapshot, actual)
        return
    if actual != expected:
        difference = "".join(
            unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile=contract.snapshot,
                tofile=f"{contract_id}:actual",
            )
        )
        raise AssertionError(f"API contract {contract_id!r} changed:\n{difference}")


def _replace_snapshot_atomically(snapshot_path: Path, contents: str) -> None:
    temporary_path = snapshot_path.with_name(f".{snapshot_path.name}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as file:
            file.write(contents)
            file.flush()
            os.fsync(file.fileno())
        temporary_path.replace(snapshot_path)
    finally:
        temporary_path.unlink(missing_ok=True)
