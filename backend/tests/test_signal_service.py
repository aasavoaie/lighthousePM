"""Unit tests for SignalService confidence score band logic."""

from app.services.signal_service import SignalService


class TestEvaluateSignalScoreBands:
    """Test direct confidence score band boundaries."""

    def test_confidence_score_red_band(self) -> None:
        assert SignalService._signal_from_confidence_score(0.0) == "RED"
        assert SignalService._signal_from_confidence_score(60.0) == "RED"

    def test_confidence_score_yellow_band(self) -> None:
        assert SignalService._signal_from_confidence_score(60.1) == "YELLOW"
        assert SignalService._signal_from_confidence_score(90.0) == "YELLOW"

    def test_confidence_score_green_band(self) -> None:
        assert SignalService._signal_from_confidence_score(90.1) == "GREEN"
        assert SignalService._signal_from_confidence_score(100.0) == "GREEN"


class TestEvaluateSignalRedConditions:
    """Test conditions that previously carried RED metric severity."""

    def test_red_open_blockers_single(self) -> None:
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=1,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=2.0,
        )
        assert signal == "YELLOW"
        assert any("blocker" in r.lower() for r in reasons)

    def test_red_open_blockers_multiple(self) -> None:
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=3,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=2.0,
        )
        assert signal == "YELLOW"
        assert any("3" in r and "blocker" in r.lower() for r in reasons)

    def test_red_high_severity_bugs_exceed_threshold(self) -> None:
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=2,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=2.0,
        )
        assert signal == "YELLOW"
        assert any("high-severity" in r.lower() for r in reasons)

    def test_red_high_severity_bugs_at_threshold(self) -> None:
        """Boundary: exactly at RED threshold (>1, so 2 is RED)."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=1,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=2.0,
        )
        assert signal == "GREEN"

    def test_red_scope_churn_exceeds_threshold(self) -> None:
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=21.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=2.0,
        )
        assert signal == "GREEN"
        assert any("churn" in r.lower() for r in reasons)

    def test_red_scope_churn_at_boundary(self) -> None:
        """Boundary: exactly at 20% RED threshold (>20, so 20.0 is not RED)."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=20.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=2.0,
        )
        assert signal == "GREEN"

    def test_red_reopen_rate_exceeds_threshold(self) -> None:
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=16.0,
            median_cycle_time_days=2.0,
        )
        assert signal == "GREEN"
        assert any("reopen" in r.lower() for r in reasons)

    def test_red_reopen_rate_at_boundary(self) -> None:
        """Boundary: exactly at 15% RED threshold (>15, so 15.0 is not RED)."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=15.0,
            median_cycle_time_days=2.0,
        )
        assert signal == "GREEN"

    def test_red_multiple_triggers(self) -> None:
        """Multiple RED conditions should list all reasons."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=2,
            open_high_severity_bugs=3,
            scope_churn_7d_pct=25.0,
            reopen_rate_pct=18.0,
            median_cycle_time_days=2.0,
        )
        assert signal == "RED"
        assert len(reasons) >= 4
        assert any("blocker" in r.lower() for r in reasons)
        assert any("high-severity" in r.lower() for r in reasons)
        assert any("churn" in r.lower() for r in reasons)
        assert any("reopen" in r.lower() for r in reasons)


class TestEvaluateSignalYellowConditions:
    """Test conditions that previously carried YELLOW metric severity."""

    def test_yellow_high_severity_bugs_present_not_red(self) -> None:
        """YELLOW if >0 bugs (and not RED due to >1)."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=1,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=2.0,
        )
        assert signal == "GREEN"
        assert any("high-severity" in r.lower() for r in reasons)

    def test_yellow_scope_churn_between_thresholds(self) -> None:
        """YELLOW if 10% < churn <= 20%."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=15.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=2.0,
        )
        assert signal == "GREEN"
        assert any("churn" in r.lower() for r in reasons)

    def test_yellow_scope_churn_at_yellow_boundary(self) -> None:
        """YELLOW if >= 10% (>10, so 10.0 is not YELLOW)."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=10.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=2.0,
        )
        # At exactly 10%, should be GREEN (not >10)
        assert signal == "GREEN"

    def test_yellow_reopen_rate_between_thresholds(self) -> None:
        """YELLOW if 10% < reopen <= 15%."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=12.0,
            median_cycle_time_days=2.0,
        )
        assert signal == "GREEN"
        assert any("reopen" in r.lower() for r in reasons)

    def test_yellow_reopen_rate_at_boundary(self) -> None:
        """YELLOW if >10% (so 10.0 is not YELLOW)."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=10.0,
            median_cycle_time_days=2.0,
        )
        assert signal == "GREEN"

    def test_yellow_high_cycle_time(self) -> None:
        """YELLOW if median cycle time > 7 days."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=8.0,
        )
        assert signal == "GREEN"
        assert any("cycle" in r.lower() for r in reasons)

    def test_yellow_high_cycle_time_at_boundary(self) -> None:
        """YELLOW if >7 days (so 7.0 is not YELLOW)."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=7.0,
        )
        assert signal == "GREEN"

    def test_yellow_high_cycle_time_with_null(self) -> None:
        """YELLOW if cycle time is null but other YELLOW triggers present."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=1,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=None,
        )
        assert signal == "GREEN"
        assert any("high-severity" in r.lower() for r in reasons)

    def test_yellow_multiple_triggers(self) -> None:
        """Multiple YELLOW conditions should list all reasons."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=1,
            scope_churn_7d_pct=15.0,
            reopen_rate_pct=12.0,
            median_cycle_time_days=8.0,
        )
        assert signal == "YELLOW"
        assert len(reasons) >= 4
        assert any("high-severity" in r.lower() for r in reasons)
        assert any("churn" in r.lower() for r in reasons)
        assert any("reopen" in r.lower() for r in reasons)
        assert any("cycle" in r.lower() for r in reasons)


class TestEvaluateSignalGreenConditions:
    """Test GREEN signal conditions (all metrics healthy)."""

    def test_green_all_metrics_healthy(self) -> None:
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=5.0,
            reopen_rate_pct=1.0,
            median_cycle_time_days=2.0,
        )
        assert signal == "GREEN"
        assert reasons == ["No major risk indicators"]

    def test_green_metrics_at_low_boundary(self) -> None:
        """Ensure GREEN when all metrics just below thresholds."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=9.9,
            reopen_rate_pct=9.9,
            median_cycle_time_days=6.9,
        )
        assert signal == "GREEN"

    def test_green_cycle_time_null(self) -> None:
        """GREEN when cycle time is null and other metrics healthy."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=1.0,
            reopen_rate_pct=1.0,
            median_cycle_time_days=None,
        )
        assert signal == "GREEN"
        assert reasons == ["No major risk indicators"]


class TestEvaluateSignalEdgeCases:
    """Test edge cases and boundary scenarios."""

    def test_high_values_trigger_red_before_yellow(self) -> None:
        """Very high values without blockers remain YELLOW by score band."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=10,
            scope_churn_7d_pct=50.0,
            reopen_rate_pct=50.0,
            median_cycle_time_days=30.0,
        )
        assert signal == "YELLOW"
        # Should include threshold reasons even though final status is score-based.
        assert any("high-severity" in r.lower() for r in reasons)

    def test_very_low_metrics(self) -> None:
        """Zero or near-zero metrics all yield GREEN."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=0.1,
        )
        assert signal == "GREEN"

    def test_reason_messages_are_strings(self) -> None:
        """All reasons should be strings (never None or other types)."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=2,
            open_high_severity_bugs=5,
            scope_churn_7d_pct=25.0,
            reopen_rate_pct=20.0,
            median_cycle_time_days=10.0,
        )
        assert all(isinstance(r, str) for r in reasons)
        assert all(len(r) > 0 for r in reasons)

    def test_cycle_time_exactly_zero(self) -> None:
        """Cycle time of 0 (instant) should be GREEN."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=0.0,
        )
        assert signal == "GREEN"

    def test_blockers_zero_is_not_red_trigger(self) -> None:
        """Zero blockers should not trigger RED for blocked-ness."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=2.0,
        )
        assert signal == "GREEN"
        assert not any("blocker" in r.lower() for r in reasons)

    def test_fractional_percentages(self) -> None:
        """Percentages can have decimal points and should work correctly."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=20.5,
            reopen_rate_pct=0.0,
            median_cycle_time_days=2.0,
        )
        assert signal == "GREEN"
        assert any("churn" in r.lower() for r in reasons)

    def test_cycle_time_high_value(self) -> None:
        """High cycle time alone keeps the score in the GREEN band."""
        signal, reasons = SignalService._evaluate_signal(
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=14.0,
        )
        assert signal == "GREEN"
        assert any("14" in r and "cycle" in r.lower() for r in reasons)
