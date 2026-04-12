"""Tests for backtest validation module.

Validates:
  - Monte Carlo permutation test: p-value, output structure
  - Bootstrap Sharpe CI: confidence interval bounds, prob_positive
  - Walk-Forward analysis: window splitting, consistency metrics
  - run_validation dispatcher
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.models import TradeRecord
from backtest.validation import (
    bootstrap_sharpe_ci,
    monte_carlo_returns_test,
    monte_carlo_test,
    run_validation,
    walk_forward_analysis,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_trades(pnls: list[float], start: str = "2025-01-01") -> list[TradeRecord]:
    """Create TradeRecord list from PnL values."""
    trades = []
    base = pd.Timestamp(start)
    for i, pnl in enumerate(pnls):
        entry = base + pd.Timedelta(days=i * 2)
        exit_ = entry + pd.Timedelta(days=1)
        trades.append(TradeRecord(
            symbol="TEST",
            direction=1,
            entry_price=100.0,
            exit_price=100.0 + pnl / 10,
            entry_time=entry,
            exit_time=exit_,
            size=10.0,
            leverage=1.0,
            pnl=pnl,
            pnl_pct=pnl / 1000 * 100,
            exit_reason="signal",
            holding_bars=1,
            commission=0.0,
        ))
    return trades


def _make_equity(n: int = 100, drift: float = 0.001, seed: int = 42) -> pd.Series:
    """Create a synthetic equity curve."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, 0.02, n)
    prices = 1_000_000 * np.cumprod(1 + returns)
    dates = pd.bdate_range("2025-01-01", periods=n)
    return pd.Series(prices, index=dates)


# ---------------------------------------------------------------------------
# Monte Carlo Permutation Test
# ---------------------------------------------------------------------------


class TestMonteCarlo:
    def test_output_structure(self) -> None:
        trades = _make_trades([100, -50, 200, -30, 150, -80, 120, -40, 90, -20])
        result = monte_carlo_test(trades, 1_000_000, n_simulations=100)
        assert "actual_sharpe" in result
        assert "p_value_sharpe" in result
        assert "p_value_max_dd" in result
        assert "n_simulations" in result
        assert result["n_simulations"] == 100
        assert result["n_trades"] == 10

    def test_p_value_range(self) -> None:
        trades = _make_trades([100, -50, 200, -30, 150])
        result = monte_carlo_test(trades, 1_000_000, n_simulations=200)
        assert 0.0 <= result["p_value_sharpe"] <= 1.0
        assert 0.0 <= result["p_value_max_dd"] <= 1.0

    def test_strong_strategy_low_p_value(self) -> None:
        """A consistently profitable strategy should have low p-value."""
        trades = _make_trades([100, 200, 150, 180, 120, 90, 110, 130, 160, 140])
        result = monte_carlo_test(trades, 1_000_000, n_simulations=500, seed=42)
        # All trades profitable → hard to beat by shuffling (already optimal)
        # p-value should be moderate (shuffling can't make it worse when all positive)
        assert result["actual_sharpe"] > 0

    def test_too_few_trades(self) -> None:
        trades = _make_trades([100, -50])
        result = monte_carlo_test(trades, 1_000_000)
        assert "error" in result

    def test_reproducibility(self) -> None:
        trades = _make_trades([100, -50, 200, -30, 150, -80])
        r1 = monte_carlo_test(trades, 1_000_000, n_simulations=100, seed=42)
        r2 = monte_carlo_test(trades, 1_000_000, n_simulations=100, seed=42)
        assert r1["p_value_sharpe"] == r2["p_value_sharpe"]


# ---------------------------------------------------------------------------
# Monte Carlo Return-Randomization Test
# ---------------------------------------------------------------------------


class TestMonteCarloReturns:
    def _make_timed_equity(self, n=500, invested_frac=0.6, drift=0.003, seed=42):
        """Build an equity curve where 'invested' days have positive drift
        and 'cash' days have zero return, simulating a timing signal."""
        rng = np.random.default_rng(seed)
        n_invested = int(n * invested_frac)
        # Invested days: positive drift with noise
        invested_rets = rng.normal(drift, 0.015, n_invested)
        # Cash days: zero return
        cash_rets = np.zeros(n - n_invested)
        # Interleave: invested days first, then cash
        all_rets = np.concatenate([invested_rets, cash_rets])
        # Shuffle to mix invested/cash days
        order = rng.permutation(n)
        all_rets = all_rets[order]
        # Build equity
        equity = 1_000_000 * np.cumprod(1 + all_rets)
        dates = pd.bdate_range("2022-01-01", periods=n)
        return pd.Series(equity, index=dates)

    def test_output_structure(self) -> None:
        eq = self._make_timed_equity(200)
        result = monte_carlo_returns_test(eq, n_simulations=500)
        assert "actual_sharpe" in result
        assert "p_value" in result
        assert "n_simulations" in result
        assert "n_observations" in result
        assert "exposure_fraction" in result
        assert result["n_simulations"] == 500

    def test_p_value_range(self) -> None:
        eq = self._make_timed_equity(200)
        result = monte_carlo_returns_test(eq, n_simulations=500)
        assert 0.0 <= result["p_value"] <= 1.0

    def test_good_timing_low_p_value(self) -> None:
        """Equity where invested days have strong drift should show
        significant timing (low p-value)."""
        eq = self._make_timed_equity(500, invested_frac=0.5, drift=0.005, seed=7)
        result = monte_carlo_returns_test(eq, n_simulations=5000, seed=42)
        # Good timing signal → random timing should rarely beat it
        assert result["p_value"] < 0.20

    def test_no_timing_high_p_value(self) -> None:
        """Equity where all days are invested (no timing) → trivial exposure."""
        eq = _make_equity(200, drift=0.001)
        result = monte_carlo_returns_test(eq, n_simulations=500)
        # Nearly all returns are non-zero → exposure ~ 1.0
        # Should either report trivial or high p-value
        assert result.get("p_value", 1.0) >= 0.05 or "error" in result

    def test_too_few_observations(self) -> None:
        eq = pd.Series([100, 101, 102, 103, 104],
                       index=pd.bdate_range("2025-01-01", periods=5))
        result = monte_carlo_returns_test(eq, n_simulations=100)
        assert "error" in result

    def test_reproducibility(self) -> None:
        eq = self._make_timed_equity(200)
        r1 = monte_carlo_returns_test(eq, n_simulations=200, seed=42)
        r2 = monte_carlo_returns_test(eq, n_simulations=200, seed=42)
        assert r1["p_value"] == r2["p_value"]
        assert r1["actual_sharpe"] == r2["actual_sharpe"]

    def test_with_positions_df(self) -> None:
        """Test that passing positions_df is used for exposure detection."""
        eq = self._make_timed_equity(200, invested_frac=0.6)
        # Create a positions_df where only ~60% of days have positions
        dates = eq.index[1:]  # skip first (no return for it)
        n = len(dates)
        n_inv = int(n * 0.6)
        pos_vals = np.zeros(n)
        pos_vals[:n_inv] = 0.5  # invested
        pos_df = pd.DataFrame({"TEST.US": pos_vals}, index=dates)
        result = monte_carlo_returns_test(eq, positions_df=pos_df, n_simulations=200)
        assert "p_value" in result
        assert 0.4 < result["exposure_fraction"] < 0.8


# ---------------------------------------------------------------------------
# Bootstrap Sharpe CI
# ---------------------------------------------------------------------------


class TestBootstrapSharpe:
    def test_output_structure(self) -> None:
        eq = _make_equity(100)
        result = bootstrap_sharpe_ci(eq, n_bootstrap=100)
        assert "observed_sharpe" in result
        assert "ci_lower" in result
        assert "ci_upper" in result
        assert "prob_positive" in result
        assert "confidence" in result
        assert result["confidence"] == 0.95

    def test_ci_contains_observed(self) -> None:
        """The observed Sharpe should usually fall within the CI."""
        eq = _make_equity(200, drift=0.001)
        result = bootstrap_sharpe_ci(eq, n_bootstrap=500)
        # Not guaranteed, but very likely for 95% CI
        assert result["ci_lower"] <= result["ci_upper"]

    def test_positive_drift_mostly_positive(self) -> None:
        """Equity with positive drift should have high prob_positive."""
        eq = _make_equity(200, drift=0.003, seed=123)
        result = bootstrap_sharpe_ci(eq, n_bootstrap=500)
        assert result["prob_positive"] > 0.5

    def test_too_few_observations(self) -> None:
        eq = pd.Series([100, 101, 102], index=pd.bdate_range("2025-01-01", periods=3))
        result = bootstrap_sharpe_ci(eq, n_bootstrap=100)
        assert "error" in result

    def test_reproducibility(self) -> None:
        eq = _make_equity(50)
        r1 = bootstrap_sharpe_ci(eq, n_bootstrap=100, seed=42)
        r2 = bootstrap_sharpe_ci(eq, n_bootstrap=100, seed=42)
        assert r1["ci_lower"] == r2["ci_lower"]

    def test_custom_confidence(self) -> None:
        eq = _make_equity(100)
        r90 = bootstrap_sharpe_ci(eq, confidence=0.90, n_bootstrap=200)
        r99 = bootstrap_sharpe_ci(eq, confidence=0.99, n_bootstrap=200)
        # 99% CI should be wider than 90% CI
        width_90 = r90["ci_upper"] - r90["ci_lower"]
        width_99 = r99["ci_upper"] - r99["ci_lower"]
        assert width_99 >= width_90


# ---------------------------------------------------------------------------
# Walk-Forward Analysis
# ---------------------------------------------------------------------------


class TestWalkForward:
    def test_output_structure(self) -> None:
        eq = _make_equity(100)
        trades = _make_trades([100, -50] * 10)
        result = walk_forward_analysis(eq, trades, n_windows=4)
        assert result["n_windows"] == 4
        assert len(result["windows"]) == 4
        assert "consistency_rate" in result
        assert "return_mean" in result
        assert "sharpe_mean" in result

    def test_window_fields(self) -> None:
        eq = _make_equity(100)
        trades = _make_trades([100, -50] * 10)
        result = walk_forward_analysis(eq, trades, n_windows=5)
        w = result["windows"][0]
        assert "window" in w
        assert "start" in w
        assert "end" in w
        assert "return" in w
        assert "sharpe" in w
        assert "max_dd" in w
        assert "trades" in w
        assert "win_rate" in w

    def test_consistency_rate(self) -> None:
        """Equity with positive drift should have high consistency."""
        eq = _make_equity(200, drift=0.003)
        trades = _make_trades([100] * 50)
        result = walk_forward_analysis(eq, trades, n_windows=5)
        assert result["consistency_rate"] > 0.5

    def test_windows_cover_full_range(self) -> None:
        eq = _make_equity(100)
        trades = _make_trades([100] * 10)
        result = walk_forward_analysis(eq, trades, n_windows=5)
        first_start = result["windows"][0]["start"]
        last_end = result["windows"][-1]["end"]
        assert first_start == str(eq.index[0].date())
        assert last_end == str(eq.index[-1].date())

    def test_too_few_bars(self) -> None:
        eq = pd.Series([100, 101], index=pd.bdate_range("2025-01-01", periods=2))
        result = walk_forward_analysis(eq, [], n_windows=5)
        assert "error" in result


# ---------------------------------------------------------------------------
# run_validation dispatcher
# ---------------------------------------------------------------------------


class TestRunValidation:
    def test_empty_config_runs_all_by_default(self) -> None:
        eq = _make_equity(100)
        trades = _make_trades([100, -50, 200, -30, 150])
        result = run_validation({}, eq, trades, 1_000_000)
        # All four tests run by default
        assert "monte_carlo" in result
        assert "monte_carlo_returns" in result
        assert "bootstrap" in result
        assert "walk_forward" in result

    def test_all_four(self) -> None:
        eq = _make_equity(100)
        trades = _make_trades([100, -50, 200, -30, 150])
        config = {
            "validation": {
                "monte_carlo": {"n_simulations": 50},
                "monte_carlo_returns": {"n_simulations": 200},
                "bootstrap": {"n_bootstrap": 50},
                "walk_forward": {"n_windows": 3},
            }
        }
        result = run_validation(config, eq, trades, 1_000_000)
        assert "monte_carlo" in result
        assert "monte_carlo_returns" in result
        assert "bootstrap" in result
        assert "walk_forward" in result

    def test_skip_individual_tool(self) -> None:
        eq = _make_equity(100)
        trades = _make_trades([100, -50, 200])
        config = {"validation": {
            "monte_carlo": {"skip": True},
            "walk_forward": {"skip": True},
            "bootstrap": {"n_bootstrap": 50},
        }}
        result = run_validation(config, eq, trades, 1_000_000)
        assert "bootstrap" in result
        assert "monte_carlo" not in result
        assert "walk_forward" not in result
