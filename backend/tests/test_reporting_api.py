from collections.abc import Generator
from datetime import UTC, datetime, timedelta
import re

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models import Issue, IssueSprint, MetricSnapshot, Release, ReleaseSignal, Sprint, SprintMetricSnapshot
from app.repositories.release_repository import ReleaseRepository
from app.services.reporting_service import ChartExportService, ChartSpec, PDFThemeProvider, ReportTemplateEngine, ReportingService


def _pdf_text(pdf: bytes) -> str:
    return pdf.decode("latin-1", errors="ignore")


def _assert_pdf(pdf: bytes) -> None:
    assert pdf.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf
    assert len(pdf) > 1000


def _page_count(pdf: bytes) -> int:
    return pdf.count(b"/Type /Page /Parent")


def client_fixture() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    app.state.testing_session_local = TestingSessionLocal

    def override_get_db_session() -> Generator[Session, None, None]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session

    original_init_db = main_module.init_db
    main_module.init_db = lambda: None
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        del app.state.testing_session_local
        main_module.init_db = original_init_db
        app.dependency_overrides.clear()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    yield from client_fixture()


def _seed_release(session: Session, release_id: str = "REL-1", project_key: str = "LHPM") -> None:
    now = datetime.now(UTC)
    session.add(
        Release(
            release_id=release_id,
            name="Release 1",
            project_key=project_key,
            description="Seed release",
            status="active",
            start_date=now - timedelta(days=10),
            release_date=now + timedelta(days=5),
            created_at=now,
            updated_at=now,
        )
    )
    session.add(ReleaseSignal(release_id=release_id, signal="YELLOW", reasons=["1 open blocker"]))
    session.commit()


def _seed_release_snapshot(
    session: Session,
    release_id: str,
    snapshot_at: datetime,
    open_blockers: int,
    scope_completed_pct: float,
    seed_issue: bool = True,
    story_points: float | None = 3.0,
) -> None:
    issue_key = f"{release_id}-ISSUE"
    if seed_issue and session.query(Issue).filter(Issue.issue_key == issue_key).first() is None:
        session.add(
            Issue(
                issue_key=issue_key,
                summary="Release issue",
                issue_type="Story",
                status="Done",
                priority="Medium",
                assignee="alex",
                story_points=story_points,
                release_id=release_id,
                is_blocker=False,
                created_at=datetime.now(UTC),
            )
        )
    session.add(
        MetricSnapshot(
            release_id=release_id,
            snapshot_at=snapshot_at,
            open_blockers=open_blockers,
            open_high_severity_bugs=0,
            open_blocker_issue_keys=[],
            open_high_severity_bug_issue_keys=[],
            scope_completed_pct=scope_completed_pct,
            completed_tickets=5,
            scope_churn_7d_pct=5.0,
            scope_added_7d_count=1,
            scope_removed_7d_count=0,
            median_cycle_time_days=2.0,
            reopen_rate_pct=0.0,
        )
    )
    session.commit()


def _seed_sprint(
    session: Session,
    sprint_id: str = "12",
    project_key: str = "LHPM",
    seed_story_points: bool = True,
) -> None:
    now = datetime.now(UTC)
    session.add(
        Sprint(
            sprint_id=sprint_id,
            name=f"Sprint {sprint_id}",
            state="active",
            project_key=project_key,
            board_id="1",
            start_date=now - timedelta(days=2),
            end_date=now + timedelta(days=8),
            complete_date=None,
            goal="Ship safely",
        )
    )
    if seed_story_points:
        _seed_sprint_issue(session, sprint_id=sprint_id, issue_key=f"{project_key}-{sprint_id}-1", story_points=3.0)
    session.commit()


def _seed_sprint_issue(
    session: Session,
    sprint_id: str,
    issue_key: str,
    story_points: float | None,
    status: str = "To Do",
) -> None:
    session.add(
        Issue(
            issue_key=issue_key,
            summary="Sprint issue",
            issue_type="Story",
            status=status,
            priority="Medium",
            assignee=None,
            story_points=story_points,
            release_id=None,
            is_blocker=False,
            created_at=datetime.now(UTC),
        )
    )
    session.add(IssueSprint(issue_key=issue_key, sprint_id=sprint_id))


def _seed_sprint_snapshot(session: Session, sprint_id: str, snapshot_at: datetime, confidence: float) -> None:
    session.add(
        SprintMetricSnapshot(
            sprint_id=sprint_id,
            snapshot_at=snapshot_at,
            committed_scope=10,
            completed_scope_pct=50.0,
            open_blockers=1,
            open_high_severity_bugs=1,
            bugs_created_during_sprint=2,
            open_blocker_issue_keys=["LHPM-1"],
            open_high_severity_bug_issue_keys=["LHPM-2"],
            bugs_created_during_sprint_issue_keys=["LHPM-3", "LHPM-4"],
            in_progress_count=3,
            not_started_count=4,
            rollover_count=1,
            median_cycle_time_days=3.0,
            reopen_rate_pct=10.0,
            delivery_confidence_score=confidence,
            delivery_confidence_components={
                "progress_alignment": 50.0,
                "velocity_fit": 80.0,
                "blocker_penalty": 90.0,
                "scope_stability": 95.0,
            },
            delivery_confidence_inputs={
                "committed_issue_count": 10,
                "initial_commitment_count": 9,
                "committed_effective_points": 10.0,
                "completed_effective_points": 5.0,
                "remaining_effective_points": 5.0,
                "completed_scope_pct": 50.0,
                "time_elapsed_pct": 40.0,
                "historical_velocity": 8.0,
                "baseline_sprint_count": 3,
                "remaining_capacity_points": 4.0,
                "blocked_issue_ratio": 0.1,
                "scope_change_count": 1,
                "scope_added_count": 1,
                "scope_removed_count": 0,
                "scope_stability_index": 0.11,
                "scope_change_issue_keys": ["LHPM-5"],
                "scope_added_issue_keys": ["LHPM-5"],
                "scope_removed_issue_keys": [],
            },
        )
    )
    session.commit()


def test_release_report_generation_includes_sections_footer_and_chart(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session)
        _seed_release_snapshot(session, "REL-1", now - timedelta(hours=2), 2, 45.0)
        _seed_release_snapshot(session, "REL-1", now, 1, 55.0)
        pdf = ReportingService().generate_release_report(session=session, release_id="REL-1", depth="full")

    _assert_pdf(pdf)
    text = _pdf_text(pdf)
    assert "Executive Summary" in text
    assert "Confidence Trend" in text
    assert "Confidence Score" in text
    assert "LighthousePM" in text
    assert "Generated by LighthousePM" in text
    assert "Page 1" in text
    assert "Version 0.1.0" in text
    assert "0.137255 0.454902 0.270588 RG" in text
    assert "BI /W" in text
    assert "/F [/AHx /Fl]" in text
    assert "Scale: 0% / 50% / 100%" in text


def test_chart_export_service_creates_high_resolution_chart_image() -> None:
    theme = PDFThemeProvider().theme()
    chart = ChartSpec(
        title="Confidence",
        kind="line",
        points=[("A", 50.0), ("B", 75.0), ("C", 90.0)],
        color=theme.metric_colors["sprintConfidence"].rgb,
        y_max=100,
    )

    image = ChartExportService(theme=theme, scale=3).export_chart_image(chart, width=500, height=160)

    assert image.width == 1500
    assert image.height == 480
    assert len(image.rgb_data) == image.width * image.height * 3


def test_pdf_renderer_aligns_header_and_separates_sections(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session)
        _seed_release_snapshot(session, "REL-1", now, 1, 55.0)
        pdf = ReportingService().generate_release_report(session=session, release_id="REL-1", depth="summary")

    text = _pdf_text(pdf)
    assert "48.00 723.00 22.00 22.00 re B" in text
    assert "BT /F2 12 Tf 82.00 730.00 Td (LighthousePM) Tj ET" in text
    assert "BT /F2 20 Tf 48.00 692.00 Td (Release Summary Report: Release 1) Tj ET" in text

    section_dividers = re.findall(
        r"0\.839216 0\.878431 0\.917647 RG 1 w 48\.00 [0-9.]+ m 564\.00 [0-9.]+ l S",
        text,
    )
    assert len(section_dividers) >= 4


def test_pdf_theme_provider_uses_lighthousepm_app_colors() -> None:
    theme_provider = PDFThemeProvider()
    theme = theme_provider.theme()

    assert theme.metric_colors["sprintConfidence"].hex == "#237445"
    assert theme.metric_colors["confidenceWatch"].hex == "#e48f00"
    assert theme.metric_colors["confidenceCritical"].hex == "#c43c2d"
    assert theme_provider.confidence_color(95).hex == "#237445"
    assert theme_provider.confidence_color(72).hex == "#e48f00"
    assert theme_provider.confidence_color(40).hex == "#c43c2d"
    assert theme.typography.heading_font == "F2"
    assert theme.spacing.page_margin == 48
    assert theme.table.background.hex == "#f6f9fc"


def test_report_template_engine_assigns_lighthousepm_chart_colors(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session)
        _seed_release_snapshot(session, "REL-1", now, 1, 55.0)
        release = ReleaseRepository.get_release_by_id(session=session, release_id="REL-1")
        assert release is not None

        theme = PDFThemeProvider().theme()
        document = ReportTemplateEngine(theme=theme).build_release_document(
            session=session,
            release=release,
            depth="full",
            generated_at=now,
        )

    confidence_trend = next(section for section in document.sections if section.title == "Confidence Trend")
    assert confidence_trend.charts[0].color == theme.metric_colors["sprintConfidence"].rgb
    assert confidence_trend.charts[1].color == theme.metric_colors["readiness"].rgb
    assert confidence_trend.charts[0].value_suffix == "%"
    assert confidence_trend.charts[1].value_suffix == "%"


def test_full_release_template_includes_historical_trend_charts(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session)
        _seed_release_snapshot(session, "REL-1", now - timedelta(hours=2), 2, 45.0)
        _seed_release_snapshot(session, "REL-1", now, 1, 55.0)
        release = ReleaseRepository.get_release_by_id(session=session, release_id="REL-1")
        assert release is not None

        document = ReportTemplateEngine().build_release_document(
            session=session,
            release=release,
            depth="full",
            generated_at=now,
        )

    historical = next(section for section in document.sections if section.title == "Historical Trends")
    assert len(historical.charts) >= 8
    assert {chart.title for chart in historical.charts}.issuperset(
        {
            "Historical Confidence",
            "Historical Release Gates Passed",
            "Historical Open Blockers",
            "Historical Scope Completed",
            "Historical Reopen Rate",
        }
    )


def test_full_sprint_template_includes_historical_trend_charts(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_sprint(session)
        _seed_sprint_snapshot(session, "12", now - timedelta(hours=2), 62.0)
        _seed_sprint_snapshot(session, "12", now, 72.0)
        sprint = session.query(Sprint).filter(Sprint.sprint_id == "12").one()

        document = ReportTemplateEngine().build_sprint_document(
            session=session,
            sprint=sprint,
            depth="full",
            generated_at=now,
        )

    historical = next(section for section in document.sections if section.title == "Historical Trends")
    assert len(historical.charts) >= 10
    assert {chart.title for chart in historical.charts}.issuperset(
        {
            "Historical Delivery Confidence",
            "Historical Progress Alignment",
            "Historical Scope Changes",
            "Historical High-Severity Bugs",
            "Historical Reopen Rate",
        }
    )


def test_release_summary_template_uses_leadership_sections(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session)
        _seed_release_snapshot(session, "REL-1", now, 1, 55.0)
        release = ReleaseRepository.get_release_by_id(session=session, release_id="REL-1")
        assert release is not None

        document = ReportTemplateEngine().build_release_document(
            session=session,
            release=release,
            depth="summary",
            generated_at=now,
        )

    assert [section.title for section in document.sections] == [
        "Executive Summary",
        "Confidence Score",
        "Confidence Breakdown",
        "Biggest Driver",
        "Top Risks",
        "Top Recommendations",
        "Decision Recommendation",
    ]
    assert document.title == "Release Summary Report: Release 1"
    assert "Release Gates" not in [section.title for section in document.sections]
    decision = next(section for section in document.sections if section.title == "Decision Recommendation")
    assert "Proceed only" in decision.lines[0]


def test_sprint_summary_template_uses_leadership_sections(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_sprint(session)
        _seed_sprint_snapshot(session, "12", now, 72.0)
        sprint = session.query(Sprint).filter(Sprint.sprint_id == "12").one()

        document = ReportTemplateEngine().build_sprint_document(
            session=session,
            sprint=sprint,
            depth="summary",
            generated_at=now,
        )

    assert [section.title for section in document.sections] == [
        "Executive Summary",
        "Delivery Confidence",
        "Confidence Breakdown",
        "Biggest Driver",
        "Top Risks",
        "Top Recommendations",
    ]
    assert document.title == "Sprint Summary Report: Sprint 12"


def test_release_report_handles_empty_dataset(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-empty")
        pdf = ReportingService().generate_release_report(session=session, release_id="REL-empty", depth="full")

    _assert_pdf(pdf)
    text = _pdf_text(pdf)
    assert "Metrics have not been computed yet" in text
    assert "No release metrics have been computed yet" in text
    assert "No chart data available" in text


def test_release_report_suppresses_confidence_for_zero_ticket_release(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-empty-snapshot")
        _seed_release_snapshot(
            session,
            "REL-empty-snapshot",
            now,
            open_blockers=0,
            scope_completed_pct=100.0,
            seed_issue=False,
        )
        release = ReleaseRepository.get_release_by_id(session=session, release_id="REL-empty-snapshot")
        assert release is not None

        document = ReportTemplateEngine().build_release_document(
            session=session,
            release=release,
            depth="full",
            generated_at=now,
        )

    summary = next(section for section in document.sections if section.title == "Executive Summary")
    assert ("Signal", "NOT COMPUTED") in summary.rows
    assert ("Confidence", "N/A") in summary.rows
    assert summary.lines == ["Release signal is not computed because no tickets are available for this scope."]

    confidence_breakdown = next(section for section in document.sections if section.title == "Confidence Breakdown")
    assert confidence_breakdown.rows == [("Status", "No confidence breakdown available.")]

    evidence = next(section for section in document.sections if section.title == "Evidence Metrics")
    assert ("Status", "No tickets are available for this scope.") in evidence.rows
    assert ("Scope completed", "N/A | No tickets are available for this scope.") in evidence.rows

    confidence_trend = next(section for section in document.sections if section.title == "Confidence Trend")
    assert [value for _, value in confidence_trend.charts[0].points] == [None]
    assert [value for _, value in confidence_trend.charts[1].points] == [None]


def test_release_report_marks_story_point_metrics_unavailable(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-no-points")
        _seed_release_snapshot(
            session,
            "REL-no-points",
            now,
            open_blockers=0,
            scope_completed_pct=75.0,
            story_points=None,
        )
        release = ReleaseRepository.get_release_by_id(session=session, release_id="REL-no-points")
        assert release is not None

        document = ReportTemplateEngine().build_release_document(
            session=session,
            release=release,
            depth="full",
            generated_at=now,
        )

    evidence = next(section for section in document.sections if section.title == "Evidence Metrics")
    assert ("Story-point metrics", "N/A | No tickets in this scope have story points.") in evidence.rows
    assert ("Scope completed", "75.0%") in evidence.rows


def test_release_report_export_endpoint_returns_pdf(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session)

    response = client.get("/releases/REL-1/reports/summary.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "lighthousepm-release-REL-1-summary.pdf" in response.headers["content-disposition"]
    _assert_pdf(response.content)
    text = _pdf_text(response.content)
    assert "Release Summary Report" in text
    assert "LighthousePM" in text
    assert "Generated by LighthousePM" in text
    assert "Page 1" in text
    assert _page_count(response.content) <= 3


def test_release_full_report_export_endpoint_embeds_chart_images(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session)
        _seed_release_snapshot(session, "REL-1", now - timedelta(hours=2), 2, 45.0)
        _seed_release_snapshot(session, "REL-1", now, 1, 55.0)

    response = client.get("/releases/REL-1/reports/full.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "lighthousepm-release-REL-1-full.pdf" in response.headers["content-disposition"]
    _assert_pdf(response.content)
    text = _pdf_text(response.content)
    assert "Release Report" in text
    assert "Historical Trends" in text
    assert "BI /W" in text
    assert "/F [/AHx /Fl]" in text
    assert "Scale: 0% / 50% / 100%" in text


def test_sprint_report_generation_and_export_workflow(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_sprint(session)
        _seed_sprint_snapshot(session, "12", now - timedelta(hours=4), 62.0)
        _seed_sprint_snapshot(session, "12", now, 72.0)

    response = client.get("/sprints/12/reports/full.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "lighthousepm-sprint-12-full.pdf" in response.headers["content-disposition"]
    _assert_pdf(response.content)
    text = _pdf_text(response.content)
    assert "Sprint Report" in text
    assert "Delivery Confidence Trend" in text
    assert "Quality Signals" in text
    assert "Recommended Actions" in text
    assert "Historical Trends" in text
    assert "BI /W" in text
    assert "Scale: 0% / 50% / 100%" in text


def test_sprint_report_suppresses_story_point_sections_without_story_points(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_sprint(session, seed_story_points=False)
        _seed_sprint_issue(session, sprint_id="12", issue_key="LHPM-0", story_points=None)
        _seed_sprint_snapshot(session, "12", now - timedelta(hours=4), 62.0)
        _seed_sprint_snapshot(session, "12", now, 72.0)
        session.commit()
        sprint = session.query(Sprint).filter(Sprint.sprint_id == "12").one()

        document = ReportTemplateEngine().build_sprint_document(
            session=session,
            sprint=sprint,
            depth="full",
            generated_at=now,
        )

    delivery = next(section for section in document.sections if section.title == "Delivery Confidence")
    assert ("Status", "Story-point metrics are unavailable because no tickets in this sprint have story points.") in delivery.rows
    assert ("Score", "N/A") in delivery.rows
    assert ("Committed scope", "10") in delivery.rows
    assert delivery.charts == []

    velocity = next(section for section in document.sections if section.title == "Velocity Health")
    assert velocity.rows == [
        ("Status", "Story-point metrics are unavailable because no tickets in this sprint have story points.")
    ]

    snapshot_changes = next(section for section in document.sections if section.title == "Snapshot Changes")
    assert snapshot_changes.lines == [
        "Story-point metrics are unavailable because no tickets in this sprint have story points."
    ]

    historical = next(section for section in document.sections if section.title == "Historical Trends")
    chart_titles = {chart.title for chart in historical.charts}
    assert "Historical Delivery Confidence" not in chart_titles
    assert "Historical Velocity Fit" not in chart_titles
    assert "Historical Scope Completion" in chart_titles
    assert "Historical High-Severity Bugs" in chart_titles


def test_sprint_summary_report_export_endpoint_returns_leadership_pdf(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_sprint(session)
        _seed_sprint_snapshot(session, "12", now, 72.0)

    response = client.get("/sprints/12/reports/summary.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "lighthousepm-sprint-12-summary.pdf" in response.headers["content-disposition"]
    _assert_pdf(response.content)
    text = _pdf_text(response.content)
    assert "Sprint Summary Report" in text
    assert "Delivery Confidence" in text
    assert "Top Risks" in text
    assert "Top Recommendations" in text
    assert "Generated by LighthousePM" in text
    assert "Page 1" in text
    assert _page_count(response.content) <= 3


def test_overview_template_matches_dashboard_sections_and_charts(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session)
        _seed_release_snapshot(session, "REL-1", now - timedelta(hours=2), 2, 45.0)
        _seed_release_snapshot(session, "REL-1", now, 1, 55.0)
        _seed_sprint(session)
        _seed_sprint_snapshot(session, "12", now - timedelta(hours=2), 62.0)
        _seed_sprint_snapshot(session, "12", now, 72.0)
        release = ReleaseRepository.get_release_by_id(session=session, release_id="REL-1")
        assert release is not None

        document = ReportTemplateEngine().build_overview_document(
            session=session,
            release=release,
            generated_at=now,
        )

    assert document.title == "Overview Dashboard Report: Release 1"
    assert [section.title for section in document.sections] == [
        "Executive Summary",
        "Project Portfolio Metrics",
        "Release Metrics",
        "Sprint Metrics",
        "Confidence Metrics",
        "Risk Indicators",
        "Signals",
        "Trends",
        "Health Indicators",
        "Recommendations",
    ]
    trends = next(section for section in document.sections if section.title == "Trends")
    assert {chart.title for chart in trends.charts}.issuperset(
        {
            "Overview Confidence Trend",
            "Overview Readiness Trend",
            "Overview Sprint Delivery Trend",
        }
    )
    assert trends.charts[0].y_max == 100
    assert trends.charts[0].value_suffix == "%"
    portfolio = next(section for section in document.sections if section.title == "Project Portfolio Metrics")
    assert ("Project", "LHPM") in portfolio.rows


def test_overview_report_export_endpoint_embeds_dashboard_chart_images(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session)
        _seed_release_snapshot(session, "REL-1", now - timedelta(hours=2), 2, 45.0)
        _seed_release_snapshot(session, "REL-1", now, 1, 55.0)
        _seed_sprint(session)
        _seed_sprint_snapshot(session, "12", now, 72.0)

    response = client.get("/releases/REL-1/reports/overview.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "lighthousepm-overview-REL-1.pdf" in response.headers["content-disposition"]
    _assert_pdf(response.content)
    text = _pdf_text(response.content)
    assert "Overview Dashboard Report" in text
    assert "Project Portfolio Metrics" in text
    assert "Release Metrics" in text
    assert "Sprint Metrics" in text
    assert "Confidence Metrics" in text
    assert "Risk Indicators" in text
    assert "Signals" in text
    assert "Trends" in text
    assert "Health Indicators" in text
    assert "Recommendations" in text
    assert "Overview Confidence Trend" in text
    assert "BI /W" in text
    assert "/F [/AHx /Fl]" in text
    assert "Scale: 0% / 50% / 100%" in text
    assert "Generated by LighthousePM" in text


def test_overview_report_handles_empty_dashboard_dataset(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-empty")
        pdf = ReportingService().generate_overview_report(session=session, release_id="REL-empty")

    _assert_pdf(pdf)
    text = _pdf_text(pdf)
    assert "Overview Dashboard Report" in text
    assert "Metrics have not been computed yet" in text
    assert "No snapshot available yet" in text
    assert "No release metrics have been computed yet" in text
    assert "No active sprint is available" in text
    assert "No chart data available" in text


def test_overview_template_uses_active_sprint_from_release_project_only(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-LHPM", project_key="LHPM")
        _seed_release(session, release_id="REL-OTHER", project_key="OTHER")
        _seed_sprint(session, sprint_id="99", project_key="OTHER")
        _seed_sprint_snapshot(session, "99", now, 72.0)
        release = ReleaseRepository.get_release_by_id(session=session, release_id="REL-LHPM")
        assert release is not None

        document = ReportTemplateEngine().build_overview_document(
            session=session,
            release=release,
            generated_at=now,
        )

    executive = next(section for section in document.sections if section.title == "Executive Summary")
    assert ("Current sprint", "No active sprint") in executive.rows
    assert ("Latest sprint snapshot", "No sprint snapshot available yet.") in executive.rows
    portfolio = next(section for section in document.sections if section.title == "Project Portfolio Metrics")
    assert ("Project", "LHPM") in portfolio.rows
    assert ("Total releases", "1") in portfolio.rows
    assert ("Total sprints", "0") in portfolio.rows


def test_overview_report_for_project_a_does_not_pull_project_b_active_sprint(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-A", project_key="PROJECTA")
        _seed_release(session, release_id="REL-B", project_key="PROJECTB")
        _seed_sprint(session, sprint_id="B-99", project_key="PROJECTB")
        _seed_sprint_snapshot(session, "B-99", now, 72.0)

        pdf = ReportingService().generate_overview_report(session=session, release_id="REL-A")

    _assert_pdf(pdf)
    text = _pdf_text(pdf)
    assert "Overview Dashboard Report" in text
    assert "PROJECTA" in text
    assert "No active sprint" in text
    assert "Sprint B-99" not in text
    assert "72.0%" not in text


def test_overview_template_portfolio_rows_are_scoped_for_same_release_names(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="LHPM-REL-1", project_key="LHPM")
        _seed_release(session, release_id="OTHER-REL-1", project_key="OTHER")
        _seed_sprint(session, sprint_id="12", project_key="LHPM")
        _seed_sprint(session, sprint_id="99", project_key="OTHER")
        _seed_sprint_snapshot(session, "12", now, 81.0)
        _seed_sprint_snapshot(session, "99", now, 42.0)
        release = ReleaseRepository.get_release_by_id(session=session, release_id="LHPM-REL-1")
        assert release is not None

        document = ReportTemplateEngine().build_overview_document(
            session=session,
            release=release,
            generated_at=now,
        )

    executive = next(section for section in document.sections if section.title == "Executive Summary")
    assert ("Release", "Release 1") in executive.rows
    assert ("Project", "LHPM") in executive.rows
    assert ("Current sprint", "Sprint 12") in executive.rows
    assert ("Latest sprint snapshot", f"{now.strftime('%Y-%m-%d %H:%M')} UTC") in executive.rows

    portfolio = next(section for section in document.sections if section.title == "Project Portfolio Metrics")
    assert ("Project", "LHPM") in portfolio.rows
    assert ("Total releases", "1") in portfolio.rows
    assert ("Active releases", "1") in portfolio.rows
    assert ("Total sprints", "1") in portfolio.rows
    assert ("Active sprints", "1") in portfolio.rows

    sprint_metrics = next(section for section in document.sections if section.title == "Sprint Metrics")
    assert ("Sprint", "Sprint 12") in sprint_metrics.rows
    assert ("Delivery confidence", "81.0%") in sprint_metrics.rows


def test_overview_template_reports_missing_active_sprint_snapshot(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session)
        _seed_sprint(session, sprint_id="12", project_key="LHPM")
        release = ReleaseRepository.get_release_by_id(session=session, release_id="REL-1")
        assert release is not None

        document = ReportTemplateEngine().build_overview_document(
            session=session,
            release=release,
            generated_at=now,
        )

    executive = next(section for section in document.sections if section.title == "Executive Summary")
    assert ("Latest release snapshot", "No snapshot available yet.") in executive.rows
    assert ("Latest sprint snapshot", "No sprint snapshot available yet.") in executive.rows
    sprint_metrics = next(section for section in document.sections if section.title == "Sprint Metrics")
    assert ("Status", "No sprint snapshot available yet.") in sprint_metrics.rows
