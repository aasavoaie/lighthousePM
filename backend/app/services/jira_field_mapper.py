from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.services.jira_types import JiraIssueDetail, JiraIssueSummary
from app.utils.constants import DONE_STATUSES, HIGH_SEVERITY_PRIORITIES, IN_PROGRESS_STATUSES


def _display_name(field: dict[str, Any] | None) -> str | None:
    if field is None:
        return None
    return field.get("displayName") or field.get("name")


def _stringify_field_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _display_name(value) or value.get("value")
    return None


@dataclass(frozen=True)
class JiraFieldMapping:
    story_points_field: str
    severity_field: str
    release_field: str
    blocker_field: str
    blocker_true_values: frozenset[str]
    changelog_fix_version_fields: frozenset[str]


class JiraFieldMapper:
    """Centralizes Jira field keys and value classification assumptions."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.mapping = JiraFieldMapping(
            story_points_field=settings.jira_field_story_points.strip(),
            severity_field=settings.jira_field_severity.strip() or "priority",
            release_field=settings.jira_field_release.strip() or "fixVersions",
            blocker_field=settings.jira_field_blocker.strip(),
            blocker_true_values=settings.blocker_true_values,
            changelog_fix_version_fields=settings.changelog_fix_version_fields,
        )

    def search_issue_fields(self) -> list[str]:
        fields = [
            "summary",
            "status",
            "issuetype",
            "assignee",
            "updated",
            self.mapping.release_field,
            self.mapping.severity_field,
        ]
        return _dedupe(fields)

    def detail_issue_fields(self) -> list[str]:
        fields = [
            "summary",
            "status",
            "issuetype",
            "assignee",
            "updated",
            self.mapping.release_field,
            self.mapping.severity_field,
            "description",
            "labels",
            "components",
            "reporter",
        ]
        if self.mapping.story_points_field:
            fields.append(self.mapping.story_points_field)
        if self.mapping.blocker_field:
            fields.append(self.mapping.blocker_field)
        return _dedupe(fields)

    def normalize_issue_summary(self, raw: dict[str, Any], updated: Any) -> JiraIssueSummary:
        fields: dict[str, Any] = raw.get("fields", {})
        fix_versions = self.extract_fix_versions(fields)
        return JiraIssueSummary(
            key=raw["key"],
            summary=fields.get("summary", ""),
            status=_display_name(fields.get("status")) or "",
            issue_type=_display_name(fields.get("issuetype")) or "",
            priority=self.extract_severity(fields),
            assignee=_display_name(fields.get("assignee")),
            updated=updated,
            fix_versions=fix_versions,
        )

    def normalize_issue_detail(
        self,
        raw: dict[str, Any],
        updated: Any,
    ) -> JiraIssueDetail:
        fields: dict[str, Any] = raw.get("fields", {})
        labels: list[str] = fields.get("labels") or []
        components: list[str] = [c.get("name", "") for c in (fields.get("components") or [])]
        fix_versions = self.extract_fix_versions(fields)
        description_raw = fields.get("description")
        if isinstance(description_raw, dict):
            description = "[ADF content]"
        else:
            description = description_raw

        return JiraIssueDetail(
            key=raw["key"],
            summary=fields.get("summary", ""),
            status=_display_name(fields.get("status")) or "",
            issue_type=_display_name(fields.get("issuetype")) or "",
            priority=self.extract_severity(fields),
            assignee=_display_name(fields.get("assignee")),
            updated=updated,
            description=description,
            labels=labels,
            components=components,
            fix_versions=fix_versions,
            reporter=_display_name(fields.get("reporter")),
            story_points=self.extract_story_points(fields),
            blocker_flag=self.extract_blocker_flag(fields),
        )

    def extract_fix_versions(self, fields: dict[str, Any]) -> list[str]:
        values = fields.get(self.mapping.release_field) or []
        if not isinstance(values, list):
            return []
        names: list[str] = []
        for version in values:
            if isinstance(version, dict):
                name = version.get("name", "")
            else:
                name = str(version)
            if name:
                names.append(name)
        return names

    def extract_severity(self, fields: dict[str, Any]) -> str | None:
        raw = fields.get(self.mapping.severity_field)
        return _stringify_field_value(raw)

    def extract_story_points(self, fields: dict[str, Any]) -> float | None:
        if not self.mapping.story_points_field:
            return None
        raw = fields.get(self.mapping.story_points_field)
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def extract_blocker_flag(self, fields: dict[str, Any]) -> bool | None:
        if not self.mapping.blocker_field:
            return None
        raw = fields.get(self.mapping.blocker_field)
        raw_text = (_stringify_field_value(raw) or "").strip().casefold()
        if not raw_text:
            return None
        return raw_text in self.mapping.blocker_true_values

    def is_fix_version_field(self, field_name: str) -> bool:
        return field_name.strip().casefold() in self.mapping.changelog_fix_version_fields

    def is_relevant_history_field(self, field_name: str) -> bool:
        normalized = field_name.strip().casefold()
        return normalized in {"status", "assignee", "priority"} or self.is_fix_version_field(normalized)

    def is_done_status(self, status: str | None) -> bool:
        return (status or "").casefold() in DONE_STATUSES

    def is_in_progress_status(self, status: str | None) -> bool:
        return (status or "").casefold() in IN_PROGRESS_STATUSES

    def is_high_severity(self, severity: str | None) -> bool:
        return (severity or "").casefold() in HIGH_SEVERITY_PRIORITIES

    def classify_blocker(
        self,
        issue_type: str,
        severity: str | None,
        status: str,
        blocker_flag: bool | None,
    ) -> bool:
        if blocker_flag is not None:
            return blocker_flag and not self.is_done_status(status)
        issue_type_value = issue_type.casefold()
        severity_value = (severity or "").casefold()
        return (
            issue_type_value in {"blocker", "incident"}
            or severity_value in {"blocker", "highest", "critical"}
        ) and not self.is_done_status(status)

    @property
    def done_statuses(self) -> frozenset[str]:
        return DONE_STATUSES

    @property
    def in_progress_statuses(self) -> frozenset[str]:
        return IN_PROGRESS_STATUSES

    @property
    def high_severity_values(self) -> frozenset[str]:
        return HIGH_SEVERITY_PRIORITIES

    @property
    def fix_version_changelog_fields(self) -> frozenset[str]:
        return self.mapping.changelog_fix_version_fields


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result