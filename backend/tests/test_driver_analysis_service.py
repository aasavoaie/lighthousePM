from types import SimpleNamespace

from app.services.driver_analysis_service import DriverAnalysisService


def test_release_driver_identifies_single_dominant_driver() -> None:
    snapshot = SimpleNamespace(
        open_blockers=1,
        open_high_severity_bugs=0,
        scope_churn_7d_pct=0.0,
        reopen_rate_pct=0.0,
        median_cycle_time_days=None,
    )

    driver = DriverAnalysisService.build_release_driver(snapshot)

    assert driver.title == "Open Blockers"
    assert driver.category == "Risk"
    assert driver.impact == -28.0
    assert driver.contributionPercent == 100.0


def test_release_driver_uses_deterministic_tie_break_for_competing_drivers() -> None:
    snapshot = SimpleNamespace(
        open_blockers=0,
        open_high_severity_bugs=0,
        scope_churn_7d_pct=25.0,
        reopen_rate_pct=16.0,
        median_cycle_time_days=10.0,
    )

    driver = DriverAnalysisService.build_release_driver(snapshot)

    assert driver.title == "Scope Churn"
    assert driver.impact == -8.0
    assert driver.contributionPercent == 44.4


def test_release_driver_returns_zero_risk_result() -> None:
    snapshot = SimpleNamespace(
        open_blockers=0,
        open_high_severity_bugs=0,
        scope_churn_7d_pct=0.0,
        reopen_rate_pct=0.0,
        median_cycle_time_days=None,
    )

    driver = DriverAnalysisService.build_release_driver(snapshot)

    assert driver.title == "No Confidence Drag"
    assert driver.impact == 0.0
    assert driver.contributionPercent == 0.0


def test_sprint_driver_identifies_single_dominant_driver() -> None:
    driver = DriverAnalysisService.build_sprint_driver(
        score=79.0,
        components={
            "progress_alignment": 100.0,
            "velocity_fit": 100.0,
            "blocker_penalty": 100.0,
            "scope_stability": 0.0,
        },
    )

    assert driver.title == "Scope Stability"
    assert driver.category == "Delivery"
    assert driver.impact == -10.0
    assert driver.contributionPercent == 100.0


def test_sprint_driver_uses_weighted_impact_for_competing_drivers() -> None:
    driver = DriverAnalysisService.build_sprint_driver(
        score=74.0,
        components={
            "progress_alignment": 60.0,
            "velocity_fit": 80.0,
            "blocker_penalty": 50.0,
            "scope_stability": 40.0,
        },
    )

    assert driver.title == "Progress Alignment"
    assert driver.impact == -16.0
    assert driver.contributionPercent == 42.1


def test_sprint_driver_returns_zero_risk_result() -> None:
    driver = DriverAnalysisService.build_sprint_driver(
        score=100.0,
        components={
            "progress_alignment": 100.0,
            "velocity_fit": 100.0,
            "blocker_penalty": 100.0,
            "scope_stability": 100.0,
        },
    )

    assert driver.title == "No Delivery Drag"
    assert driver.impact == 0.0
    assert driver.contributionPercent == 0.0
