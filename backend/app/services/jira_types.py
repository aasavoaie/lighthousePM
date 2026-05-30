"""Normalized internal types for Jira API responses.

These dataclasses represent the subset of Jira data used by this service.
Raw Jira JSON is mapped into these structures in jira_service.py so the rest
of the codebase is insulated from Jira's field naming conventions.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class JiraSprintRef:
    """A Jira sprint value extracted from an issue sprint field."""

    id: str
    name: str
    state: str
    board_id: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    complete_date: str | None = None
    goal: str | None = None


@dataclass
class JiraIssueSummary:
    """Lightweight view of a Jira issue returned from JQL search results."""

    key: str
    summary: str
    status: str
    issue_type: str
    priority: str | None
    assignee: str | None
    updated: datetime | None
    fix_versions: list[str] = field(default_factory=list)
    sprints: list[JiraSprintRef] = field(default_factory=list)


@dataclass
class JiraIssueDetail:
    """Full issue detail including description, labels, and components."""

    key: str
    summary: str
    status: str
    issue_type: str
    priority: str | None
    assignee: str | None
    updated: datetime | None
    description: str | None
    labels: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    fix_versions: list[str] = field(default_factory=list)
    sprints: list[JiraSprintRef] = field(default_factory=list)
    reporter: str | None = None
    story_points: float | None = None
    blocker_flag: bool | None = None


@dataclass
class JiraChangelogEntry:
    """A single field-change record from a Jira issue's changelog."""

    issue_key: str
    field_name: str
    from_value: str | None
    to_value: str | None
    changed_at: datetime
    author: str | None


@dataclass
class JiraVersion:
    """A Jira project version (fix version / release)."""

    id: str
    name: str
    project_key: str
    released: bool
    release_date: str | None  # ISO date string, e.g. "2026-06-30"
    start_date: str | None
    description: str | None
