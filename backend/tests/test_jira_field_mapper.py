import pytest

from app.config import Settings
from app.services.jira_field_mapper import JiraFieldMapper


def _custom_mapper() -> JiraFieldMapper:
    settings = Settings(
        _env_file=None,
        jira_done_statuses="Released",
        jira_in_progress_statuses="Building,Reviewing",
        jira_high_severity_values="Sev-1",
        jira_bug_issue_types="Defect",
        jira_blocker_issue_types="Impediment",
        jira_blocker_severity_values="Stop-ship",
        jira_blocked_statuses="Waiting",
    )
    settings.validate_classification_settings()
    return JiraFieldMapper(settings)


def test_mapper_uses_configured_classification_values() -> None:
    mapper = _custom_mapper()

    assert mapper.is_done_status(" RELEASED ") is True
    assert mapper.is_done_status("Done") is False
    assert mapper.is_in_progress_status("reviewing") is True
    assert mapper.is_high_severity("SEV-1") is True
    assert mapper.is_bug("defect") is True
    assert mapper.is_bug("Bug") is False


def test_explicit_blocker_value_takes_precedence_over_fallbacks() -> None:
    mapper = _custom_mapper()

    assert mapper.classify_blocker("Impediment", "Stop-ship", "Waiting", blocker_flag=False) is False
    assert mapper.classify_blocker("Story", "Low", "Building", blocker_flag=True) is True
    assert mapper.classify_blocker("Story", "Low", "Released", blocker_flag=True) is False


def test_blocker_fallback_categories_are_configurable() -> None:
    mapper = _custom_mapper()

    assert mapper.classify_blocker("Impediment", "Low", "Building", blocker_flag=None) is True
    assert mapper.classify_blocker("Story", "Stop-ship", "Building", blocker_flag=None) is True
    assert mapper.classify_blocker("Story", "Low", "Waiting", blocker_flag=None) is True
    assert mapper.classify_blocker("Blocker", "Critical", "Blocked", blocker_flag=None) is False


def test_missing_jira_classification_fields_remain_null() -> None:
    mapper = _custom_mapper()
    raw_issue = {"key": "LHPM-1", "fields": {"summary": "Missing classifications"}}

    summary = mapper.normalize_issue_summary(raw_issue, updated=None, created=None)
    detail = mapper.normalize_issue_detail(raw_issue, updated=None, created=None)

    assert summary.status is None
    assert summary.issue_type is None
    assert detail.status is None
    assert detail.issue_type is None
    assert mapper.classify_blocker(None, None, None, blocker_flag=None) is False


@pytest.mark.parametrize(
    ("assignee", "expected_identifier"),
    [
        (
            {
                "displayName": "Ava",
                "accountId": " account-1 ",
                "key": "legacy-key",
                "name": "legacy-name",
            },
            "account-1",
        ),
        ({"displayName": "Ava", "key": " legacy-key ", "name": "legacy-name"}, "legacy-key"),
        ({"displayName": "Ava", "name": " legacy-name "}, "legacy-name"),
        ({"displayName": "Ava"}, None),
        (None, None),
    ],
)
def test_mapper_uses_stable_assignee_identifier_precedence(
    assignee: dict[str, str] | None,
    expected_identifier: str | None,
) -> None:
    mapper = _custom_mapper()
    raw_issue = {
        "key": "LHPM-1",
        "fields": {"summary": "Assignee identity", "assignee": assignee},
    }

    summary = mapper.normalize_issue_summary(raw_issue, updated=None, created=None)
    detail = mapper.normalize_issue_detail(raw_issue, updated=None, created=None)

    assert summary.assignee_id == expected_identifier
    assert detail.assignee_id == expected_identifier
