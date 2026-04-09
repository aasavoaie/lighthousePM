# Deterministic signal threshold placeholders for later implementation.
OPEN_BLOCKERS_RED_THRESHOLD = 0
HIGH_SEVERITY_BUGS_RED_THRESHOLD = 1
SCOPE_CHURN_RED_THRESHOLD = 0.20
SCOPE_CHURN_YELLOW_THRESHOLD = 0.10
REOPEN_RATE_RED_THRESHOLD = 0.15

# Signal-layer thresholds (MVP assumptions)
# Percent-based metrics are stored as 0-100 in metric_snapshots and converted to
# normalized ratios (0-1) before comparing to ratio thresholds above.
HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD = 0
REOPEN_RATE_YELLOW_THRESHOLD = 0.10
CYCLE_TIME_YELLOW_THRESHOLD_DAYS = 7.0

# ---------------------------------------------------------------------------
# Jira field value mappings
# All status/priority comparisons are case-insensitive (use .casefold()).
# Projects with custom Jira configurations may need to extend these sets.
# ---------------------------------------------------------------------------

# Statuses that count as "done" for scope completion, cycle time, and reopen rate.
# Assumption: "resolved" is treated as done; projects that use different terminal
# status names must add them here.
DONE_STATUSES: frozenset[str] = frozenset({"done", "closed", "resolved"})

# Statuses that mark the start of active work for cycle time calculation.
# Assumption: cycle time starts at the first transition INTO one of these states.
# Issues that were never moved to an in-progress status are excluded from the median.
IN_PROGRESS_STATUSES: frozenset[str] = frozenset(
    {"in progress", "in development", "in review", "in testing"}
)

# Priorities that qualify as "high severity" for the open-high-severity-bugs metric.
# Assumption: only issues with issue_type == "bug" (case-insensitive) are counted.
HIGH_SEVERITY_PRIORITIES: frozenset[str] = frozenset({"high", "highest", "critical"})
