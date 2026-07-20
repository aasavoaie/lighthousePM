from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.services.jira_types import JiraIssueDetail, JiraIssueSummary, JiraSprintRef


def _display_name(field: dict[str, Any] | None) -> str | None:
    if field is None:
        return None
    return field.get("displayName") or field.get("name")


def _assignee_identifier(field: dict[str, Any] | None) -> str | None:
    if not isinstance(field, dict):
        return None
    value = field.get("accountId") or field.get("key") or field.get("name")
    return str(value).strip() if value is not None and str(value).strip() else None


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
    sprint_field: str
    blocker_field: str
    blocker_true_values: frozenset[str]
    changelog_fix_version_fields: frozenset[str]
    changelog_sprint_fields: frozenset[str]
    done_statuses: frozenset[str]
    in_progress_statuses: frozenset[str]
    high_severity_values: frozenset[str]
    bug_issue_types: frozenset[str]
    blocker_issue_types: frozenset[str]
    blocker_severity_values: frozenset[str]
    blocked_statuses: frozenset[str]


class JiraFieldMapper:
    """Centralizes Jira field keys and value classification assumptions."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.mapping = JiraFieldMapping(
            story_points_field=settings.jira_field_story_points.strip(),
            severity_field=settings.jira_field_severity.strip() or "priority",
            release_field=settings.jira_field_release.strip() or "fixVersions",
            sprint_field=settings.jira_field_sprint.strip(),
            blocker_field=settings.jira_field_blocker.strip(),
            blocker_true_values=settings.blocker_true_values,
            changelog_fix_version_fields=settings.changelog_fix_version_fields,
            changelog_sprint_fields=settings.changelog_sprint_fields,
            done_statuses=settings.done_statuses,
            in_progress_statuses=settings.in_progress_statuses,
            high_severity_values=settings.high_severity_values,
            bug_issue_types=settings.bug_issue_types,
            blocker_issue_types=settings.blocker_issue_types,
            blocker_severity_values=settings.blocker_severity_values,
            blocked_statuses=settings.blocked_statuses,
        )

    def search_issue_fields(self) -> list[str]:
        fields = [
            "summary",
            "status",
            "issuetype",
            "assignee",
            "created",
            "updated",
            self.mapping.release_field,
            self.mapping.severity_field,
        ]
        if self.mapping.sprint_field:
            fields.append(self.mapping.sprint_field)
        return _dedupe(fields)

    def detail_issue_fields(self) -> list[str]:
        fields = [
            "summary",
            "status",
            "issuetype",
            "assignee",
            "created",
            "updated",
            self.mapping.release_field,
            self.mapping.severity_field,
        ]
        if self.mapping.sprint_field:
            fields.append(self.mapping.sprint_field)
        if self.mapping.story_points_field:
            fields.append(self.mapping.story_points_field)
        if self.mapping.blocker_field:
            fields.append(self.mapping.blocker_field)
        return _dedupe(fields)

    def normalize_issue_summary(self, raw: dict[str, Any], updated: Any, created: Any) -> JiraIssueSummary:
        fields: dict[str, Any] = raw.get("fields", {})
        fix_versions = self.extract_fix_versions(fields)
        sprints = self.extract_sprints(fields)
        return JiraIssueSummary(
            key=raw["key"],
            summary=fields.get("summary", ""),
            status=_display_name(fields.get("status")),
            issue_type=_display_name(fields.get("issuetype")),
            priority=self.extract_severity(fields),
            assignee=_display_name(fields.get("assignee")),
            updated=updated,
            assignee_id=_assignee_identifier(fields.get("assignee")),
            created=created,
            fix_versions=fix_versions,
            sprints=sprints,
        )

    def normalize_issue_detail(
        self,
        raw: dict[str, Any],
        updated: Any,
        created: Any,
    ) -> JiraIssueDetail:
        fields: dict[str, Any] = raw.get("fields", {})
        fix_versions = self.extract_fix_versions(fields)
        sprints = self.extract_sprints(fields)

        return JiraIssueDetail(
            key=raw["key"],
            summary=fields.get("summary", ""),
            status=_display_name(fields.get("status")),
            issue_type=_display_name(fields.get("issuetype")),
            priority=self.extract_severity(fields),
            assignee=_display_name(fields.get("assignee")),
            updated=updated,
            assignee_id=_assignee_identifier(fields.get("assignee")),
            created=created,
            fix_versions=fix_versions,
            sprints=sprints,
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

    def extract_sprints(self, fields: dict[str, Any]) -> list[JiraSprintRef]:
        if not self.mapping.sprint_field:
            return []
        values = fields.get(self.mapping.sprint_field) or []
        if not isinstance(values, list):
            values = [values]

        sprints: list[JiraSprintRef] = []
        for value in values:
            sprint = self._parse_sprint_value(value)
            if sprint is not None:
                sprints.append(sprint)
        return sprints

    @staticmethod
    def _parse_sprint_value(value: Any) -> JiraSprintRef | None:
        if isinstance(value, dict):
            sprint_id = value.get("id")
            name = value.get("name")
            if sprint_id is None or not name:
                return None
            board_id = value.get("rapidViewId") or value.get("originBoardId") or value.get("boardId")
            return JiraSprintRef(
                id=str(sprint_id),
                name=str(name),
                state=str(value.get("state") or "unknown").casefold(),
                board_id=str(board_id) if board_id is not None else None,
                start_date=value.get("startDate"),
                end_date=value.get("endDate"),
                complete_date=value.get("completeDate"),
                goal=value.get("goal"),
            )
        if isinstance(value, str):
            parsed = _parse_legacy_sprint_string(value)
            if parsed.get("id") and parsed.get("name"):
                return JiraSprintRef(
                    id=parsed["id"],
                    name=parsed["name"],
                    state=parsed.get("state", "unknown").casefold(),
                    board_id=parsed.get("rapidViewId") or parsed.get("originBoardId"),
                    start_date=parsed.get("startDate"),
                    end_date=parsed.get("endDate"),
                    complete_date=parsed.get("completeDate"),
                    goal=parsed.get("goal"),
                )
        return None

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

    def is_sprint_field(self, field_name: str) -> bool:
        return field_name.strip().casefold() in self.mapping.changelog_sprint_fields

    def is_relevant_history_field(self, field_name: str) -> bool:
        normalized = field_name.strip().casefold()
        return (
            normalized
            in {
                "status",
                "assignee",
                "priority",
                "issuetype",
                "issue type",
                self.mapping.severity_field.casefold(),
                self.mapping.blocker_field.casefold(),
            }
            or self.is_fix_version_field(normalized)
            or self.is_sprint_field(normalized)
        )

    def is_done_status(self, status: str | None) -> bool:
        return (status or "").strip().casefold() in self.mapping.done_statuses

    def is_in_progress_status(self, status: str | None) -> bool:
        return (status or "").strip().casefold() in self.mapping.in_progress_statuses

    def is_high_severity(self, severity: str | None) -> bool:
        return (severity or "").strip().casefold() in self.mapping.high_severity_values

    def is_bug(self, issue_type: str | None) -> bool:
        return (issue_type or "").strip().casefold() in self.mapping.bug_issue_types

    def parse_blocker_flag(self, value: str | None) -> bool | None:
        normalized = (value or "").strip().casefold()
        if not normalized:
            return None
        return normalized in self.mapping.blocker_true_values

    def classify_blocker(
        self,
        issue_type: str | None,
        severity: str | None,
        status: str | None,
        blocker_flag: bool | None,
    ) -> bool:
        if blocker_flag is not None:
            return blocker_flag and not self.is_done_status(status)
        issue_type_value = (issue_type or "").strip().casefold()
        severity_value = (severity or "").strip().casefold()
        status_value = (status or "").strip().casefold()
        return (
            issue_type_value in self.mapping.blocker_issue_types
            or severity_value in self.mapping.blocker_severity_values
            or status_value in self.mapping.blocked_statuses
        ) and not self.is_done_status(status)

    @property
    def done_statuses(self) -> frozenset[str]:
        return self.mapping.done_statuses

    @property
    def in_progress_statuses(self) -> frozenset[str]:
        return self.mapping.in_progress_statuses

    @property
    def high_severity_values(self) -> frozenset[str]:
        return self.mapping.high_severity_values

    @property
    def bug_issue_types(self) -> frozenset[str]:
        return self.mapping.bug_issue_types

    @property
    def blocker_issue_types(self) -> frozenset[str]:
        return self.mapping.blocker_issue_types

    @property
    def blocker_severity_values(self) -> frozenset[str]:
        return self.mapping.blocker_severity_values

    @property
    def blocked_statuses(self) -> frozenset[str]:
        return self.mapping.blocked_statuses

    @property
    def fix_version_changelog_fields(self) -> frozenset[str]:
        return self.mapping.changelog_fix_version_fields

    @property
    def sprint_changelog_fields(self) -> frozenset[str]:
        return self.mapping.changelog_sprint_fields


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _parse_legacy_sprint_string(value: str) -> dict[str, str]:
    if "[" not in value or "]" not in value:
        return {}
    content = value[value.find("[") + 1 : value.rfind("]")]
    parsed: dict[str, str] = {}
    for part in content.split(","):
        if "=" not in part:
            continue
        key, raw_value = part.split("=", 1)
        parsed[key.strip()] = raw_value.strip()
    return parsed
