"""Statistical validation for backtest results.

Four independent tools:
  - Monte Carlo permutation test (trade-level): is the trade ordering significant?
  - Monte Carlo return-randomization test: is the strategy Sharpe significantly
    better than what random daily returns would produce?
  - Bootstrap Sharpe CI: how stable is the risk-adjusted return?
  - Walk-Forward analysis: is performance consistent across time windows?

Usage: called automatically by BaseEngine.run_backtest when config["validation"]
is present, or invoked directly on backtest outputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from backtest.models import TradeRecord


# ─── Quality Gate Acceptance Criteria ───

# Tier 1: Minimum bar (required for all strategies)
TIER_1 = {
    "wf_consistency_min": 0.60,   # ≥60% of windows profitable
    "bs_prob_positive_min": 0.90, # ≥90% bootstrap probability of positive Sharpe
    "trade_count_min": 30,         # minimum trades for CLT
    "max_drawdown_max": -0.50,    # absolute circuit breaker
}

# Tier 2: Statistical significance (required for deployment)
TIER_2 = {
    "mc_p_value_max": 0.10,       # marginal significance that order matters
    "bs_ci_lower_min": 0.0,       # bootstrap CI must not include zero
    "wf_sharpe_std_max": 1.0,     # performance shouldn't vary wildly
    "wf_consistency_min": 0.80,   # ≥80% windows profitable
}

# Tier 3: High conviction (aspirational)
TIER_3 = {
    "mc_p_value_max": 0.05,       # conventional statistical significance
    "bs_ci_lower_min": 0.3,       # confidently above trivial Sharpe
    "wf_consistency_min": 1.0,    # profitable in every window
}


def evaluate_quality_gate(validation: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate validation results against Tier 1/2/3 acceptance criteria.

    Args:
        validation: Results from run_validation().
        metrics: Backtest metrics dict.

    Returns:
        Dict with quality_tier (0=untested, 1/2/3=tier achieved),
        tier_results (per-tier pass/fail details), and summary.
    """
    tier_results = {}
    achieved_tier = 0

    # ── Tier 1 checks ──
    t1 = TIER_1.copy()
    t1_pass = True
    t1_details = {}

    wf = validation.get("walk_forward", {})
    t1_details["wf_consistency"] = wf.get("consistency_rate", 0.0)
    if t1_details["wf_consistency"] < t1["wf_consistency_min"]:
        t1_pass = False

    bs = validation.get("bootstrap", {})
    t1_details["bs_prob_positive"] = bs.get("prob_positive", 0.0)
    if t1_details["bs_prob_positive"] < t1["bs_prob_positive_min"]:
        t1_pass = False

    t1_details["trade_count"] = metrics.get("trade_count", 0)
    if t1_details["trade_count"] < t1["trade_count_min"]:
        t1_pass = False

    t1_details["max_drawdown"] = metrics.get("max_drawdown", 0.0)
    if t1_details["max_drawdown"] < t1["max_drawdown_max"]:
        t1_pass = False

    tier_results["tier_1"] = {"passed": t1_pass, "details": t1_details}
    if t1_pass:
        achieved_tier = 1

    # ── Tier 2 checks (only if Tier 1 passed) ──
    if t1_pass:
        t2 = TIER_2.copy()
        t2_pass = True
        t2_details = {}

        mcr = validation.get("monte_carlo_returns", {})
        t2_details["mc_p_value"] = mcr.get("p_value", 1.0)
        if t2_details["mc_p_value"] > t2["mc_p_value_max"]:
            t2_pass = False

        t2_details["bs_ci_lower"] = bs.get("ci_lower", -1.0)
        if t2_details["bs_ci_lower"] <= t2["bs_ci_lower_min"]:
            t2_pass = False

        t2_details["wf_sharpe_std"] = wf.get("sharpe_std", 999.0)
        if t2_details["wf_sharpe_std"] > t2["wf_sharpe_std_max"]:
            t2_pass = False

        t2_details["wf_consistency"] = wf.get("consistency_rate", 0.0)
        if t2_details["wf_consistency"] < t2["wf_consistency_min"]:
            t2_pass = False

        tier_results["tier_2"] = {"passed": t2_pass, "details": t2_details}
        if t2_pass:
            achieved_tier = 2

    # ── Tier 3 checks (only if Tier 2 passed) ──
    if achieved_tier == 2:
        t3 = TIER_3.copy()
        t3_pass = True
        t3_details = {}

        t3_details["mc_p_value"] = mcr.get("p_value", 1.0)
        if t3_details["mc_p_value"] > t3["mc_p_value_max"]:
            t3_pass = False

        t3_details["bs_ci_lower"] = bs.get("ci_lower", -1.0)
        if t3_details["bs_ci_lower"] <= t3["bs_ci_lower_min"]:
            t3_pass = False

        t3_details["wf_consistency"] = wf.get("consistency_rate", 0.0)
        if t3_details["wf_consistency"] < t3["wf_consistency_min"]:
            t3_pass = False

        tier_results["tier_3"] = {"passed": t3_pass, "details": t3_details}
        if t3_pass:
            achieved_tier = 3

    return {
        "quality_tier": achieved_tier,
        "tier_results": tier_results,
    }


# ─── Monte Carlo Permutation Test ───


def monte_carlo_test(
    trades: List[TradeRecord],
    initial_capital: float,
    n_simulations: int = 1000,
    seed: int = 42,
) -> Dict[str, Any]:
    """Shuffle trade PnL order to test path significance.

    Null hypothesis: the observed Sharpe / max-drawdown is no better than
    a random ordering of the same trades.

    Args:
        trades: Completed round-trip trades from backtest.
        initial_capital: Starting capital.
        n_simulations: Number of random permutations.
        seed: Random seed for reproducibility.

    Returns:
        Dict with actual_sharpe, p_value_sharpe, actual_max_dd,
        p_value_max_dd, simulated_sharpes (percentiles).
    """
    if len(trades) < 3:
        return {"error": "need at least 3 trades", "p_value_sharpe": 1.0}

    pnls = np.array([t.pnl for t in trades])
    actual = _path_metrics(pnls, initial_capital)

    rng = np.random.default_rng(seed)
    sharpe_count = 0
    dd_count = 0
    sim_sharpes = []

    for _ in range(n_simulations):
        shuffled = rng.permutation(pnls)
        sim = _path_metrics(shuffled, initial_capital)
        sim_sharpes.append(sim["sharpe"])
        if sim["sharpe"] >= actual["sharpe"]:
            sharpe_count += 1
        if sim["max_dd"] >= actual["max_dd"]:  # less negative = "better"
            dd_count += 1

    sim_arr = np.array(sim_sharpes)
    return {
        "actual_sharpe": round(actual["sharpe"], 4),
        "actual_max_dd": round(actual["max_dd"], 4),
        "p_value_sharpe": round(sharpe_count / n_simulations, 4),
        "p_value_max_dd": round(dd_count / n_simulations, 4),
        "simulated_sharpe_mean": round(float(sim_arr.mean()), 4),
        "simulated_sharpe_std": round(float(sim_arr.std()), 4),
        "simulated_sharpe_p5": round(float(np.percentile(sim_arr, 5)), 4),
        "simulated_sharpe_p95": round(float(np.percentile(sim_arr, 95)), 4),
        "n_simulations": n_simulations,
        "n_trades": len(trades),
    }


def _path_metrics(pnls: np.ndarray, initial_capital: float) -> Dict[str, float]:
    """Compute Sharpe and max drawdown from a PnL sequence."""
    equity = initial_capital + np.cumsum(pnls)
    returns = np.diff(equity) / equity[:-1] if len(equity) > 1 else np.array([0.0])
    std = returns.std()
    sharpe = float(returns.mean() / (std + 1e-10) * np.sqrt(252))
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / np.where(peak > 0, peak, 1.0)
    max_dd = float(dd.min())
    return {"sharpe": sharpe, "max_dd": max_dd}


# ─── Monte Carlo Return-Randomization Test ───


def monte_carlo_returns_test(
    equity_curve: pd.Series,
    positions_df: pd.DataFrame | None = None,
    returns_df: pd.DataFrame | None = None,
    benchmark_returns: pd.Series | None = None,
    n_simulations: int = 10000,
    bars_per_year: int = 252,
    seed: int = 42,
) -> Dict[str, Any]:
    """Stock-selection randomization test: does the strategy select
    the RIGHT stocks at the RIGHT time?

    When ``returns_df`` (per-stock daily returns) and ``positions_df``
    (per-stock daily weights) are provided, this test randomizes WHICH
    stocks receive weight on each day while preserving:
      - The same number of active positions per day
      - The same total exposure per day
      - The same per-stock weight distribution

    This is far more powerful than simple timing randomization because
    it directly tests whether the signal engine's stock picks add alpha
    over random selection from the same universe.

    Fallback (no returns_df): shuffles exposure-weight timing as before.

    Args:
        equity_curve: Portfolio equity time series.
        positions_df: DataFrame of daily position weights (columns = codes).
        returns_df: DataFrame of daily per-stock returns (columns = codes).
            When provided, enables stock-selection randomization.
        benchmark_returns: Unused (kept for API compat).
        n_simulations: Number of random draws (default 10 000).
        bars_per_year: Annualisation factor.
        seed: Random seed for reproducibility.

    Returns:
        Dict with actual_sharpe, p_value, simulated stats.
    """
    port_returns = equity_curve.pct_change().dropna()
    all_returns = port_returns.values
    n = len(all_returns)

    if n < 20:
        return {"error": "need at least 20 daily return observations", "p_value": 1.0}

    actual_sharpe = _sharpe(all_returns, bars_per_year)

    # ── Stock-selection randomization (preferred when we have per-stock data) ──
    if positions_df is not None and returns_df is not None:
        # Align positions and returns to equity curve index
        aligned_pos = positions_df.reindex(port_returns.index).fillna(0.0)
        aligned_ret = returns_df.reindex(port_returns.index).fillna(0.0)

        # Ensure same columns
        common_cols = sorted(set(aligned_pos.columns) & set(aligned_ret.columns))
        if len(common_cols) < 2:
            # Fall through to timing-based test
            pass
        else:
            pos_mat = aligned_pos[common_cols].values  # (n_days, n_stocks)
            ret_mat = aligned_ret[common_cols].values   # (n_days, n_stocks)
            n_stocks = len(common_cols)

            # Compute actual portfolio return: sum(weight_i * return_i) per day
            actual_port_ret = (pos_mat * ret_mat).sum(axis=1)
            actual_sharpe_sel = _sharpe(actual_port_ret, bars_per_year)

            # Per-day: number of active positions and total weight
            active_per_day = (np.abs(pos_mat) > 1e-8).sum(axis=1)  # (n_days,)
            total_weight_per_day = np.abs(pos_mat).sum(axis=1)     # (n_days,)

            # Exposure stats
            invested_mask = total_weight_per_day > 1e-8
            n_invested = int(invested_mask.sum())
            mean_exposure = float(total_weight_per_day.mean())
            exposure_frac = n_invested / n if n > 0 else 0.0

            rng = np.random.default_rng(seed)
            count_ge = 0
            sim_sharpes = np.empty(n_simulations)

            for i in range(n_simulations):
                sim_ret = np.zeros(n)
                for d in range(n):
                    k = active_per_day[d]
                    if k == 0 or k >= n_stocks:
                        # No positions or all positions — same as actual
                        sim_ret[d] = actual_port_ret[d]
                        continue
                    # Randomly select k stocks from the universe
                    chosen = rng.choice(n_stocks, size=k, replace=False)
                    # Equal weight among chosen, scaled to same total weight
                    w = total_weight_per_day[d] / k
                    sim_ret[d] = (ret_mat[d, chosen] * w).sum()

                s = _sharpe(sim_ret, bars_per_year)
                sim_sharpes[i] = s
                if s >= actual_sharpe_sel:
                    count_ge += 1

            p_value = count_ge / n_simulations

            return {
                "actual_sharpe": round(actual_sharpe_sel, 4),
                "p_value": round(p_value, 4),
                "simulated_sharpe_mean": round(float(sim_sharpes.mean()), 4),
                "simulated_sharpe_std": round(float(sim_sharpes.std()), 4),
                "simulated_sharpe_p5": round(float(np.percentile(sim_sharpes, 5)), 4),
                "simulated_sharpe_p95": round(float(np.percentile(sim_sharpes, 95)), 4),
                "n_simulations": n_simulations,
                "n_observations": n,
                "n_invested_days": n_invested,
                "exposure_fraction": round(exposure_frac, 4),
                "mean_exposure_weight": round(mean_exposure, 4),
                "test_type": "stock_selection",
            }

    # ── Fallback: exposure-weight timing shuffle ──
    if positions_df is not None:
        aligned_pos = positions_df.reindex(port_returns.index).fillna(0.0)
        exposure_weights = aligned_pos.abs().sum(axis=1).values
    else:
        exposure_weights = (np.abs(all_returns) > 1e-12).astype(float)

    invested_mask = exposure_weights > 1e-8
    n_invested = int(invested_mask.sum())
    mean_exposure = float(exposure_weights.mean())
    exposure_frac = n_invested / n if n > 0 else 0.0

    if n_invested < 5 or n_invested >= n:
        return {
            "actual_sharpe": round(actual_sharpe, 4),
            "p_value": 1.0,
            "error": f"trivial exposure ({n_invested}/{n} days invested)",
            "exposure_fraction": round(exposure_frac, 4),
            "mean_exposure_weight": round(mean_exposure, 4),
            "n_observations": n,
        }

    rng = np.random.default_rng(seed)
    count_ge = 0
    sim_sharpes = np.empty(n_simulations)

    for i in range(n_simulations):
        shuffled_weights = rng.permutation(exposure_weights)
        sim_returns = np.where(
            exposure_weights > 1e-8,
            all_returns * (shuffled_weights / (exposure_weights + 1e-10)),
            all_returns * shuffled_weights,
        )
        s = _sharpe(sim_returns, bars_per_year)
        sim_sharpes[i] = s
        if s >= actual_sharpe:
            count_ge += 1

    p_value = count_ge / n_simulations

    return {
        "actual_sharpe": round(actual_sharpe, 4),
        "p_value": round(p_value, 4),
        "simulated_sharpe_mean": round(float(sim_sharpes.mean()), 4),
        "simulated_sharpe_std": round(float(sim_sharpes.std()), 4),
        "simulated_sharpe_p5": round(float(np.percentile(sim_sharpes, 5)), 4),
        "simulated_sharpe_p95": round(float(np.percentile(sim_sharpes, 95)), 4),
        "n_simulations": n_simulations,
        "n_observations": n,
        "n_invested_days": n_invested,
        "exposure_fraction": round(exposure_frac, 4),
        "mean_exposure_weight": round(mean_exposure, 4),
        "test_type": "timing_shuffle",
    }


# ─── Bootstrap Sharpe CI ───


def bootstrap_sharpe_ci(
    equity_curve: pd.Series,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    bars_per_year: int = 252,
    seed: int = 42,
) -> Dict[str, Any]:
    """Resample daily returns to estimate Sharpe confidence interval.

    Args:
        equity_curve: Equity time series.
        n_bootstrap: Number of bootstrap samples.
        confidence: Confidence level (e.g. 0.95 for 95% CI).
        bars_per_year: Annualisation factor.
        seed: Random seed.

    Returns:
        Dict with observed_sharpe, ci_lower, ci_upper, median_sharpe,
        prob_positive (fraction of samples with Sharpe > 0).
    """
    returns = equity_curve.pct_change().dropna().values
    if len(returns) < 5:
        return {"error": "need at least 5 return observations"}

    observed = _sharpe(returns, bars_per_year)

    rng = np.random.default_rng(seed)
    boot_sharpes = []
    for _ in range(n_bootstrap):
        sample = rng.choice(returns, size=len(returns), replace=True)
        boot_sharpes.append(_sharpe(sample, bars_per_year))

    arr = np.array(boot_sharpes)
    alpha = (1 - confidence) / 2
    lower = float(np.percentile(arr, alpha * 100))
    upper = float(np.percentile(arr, (1 - alpha) * 100))
    prob_pos = float(np.mean(arr > 0))

    return {
        "observed_sharpe": round(observed, 4),
        "ci_lower": round(lower, 4),
        "ci_upper": round(upper, 4),
        "median_sharpe": round(float(np.median(arr)), 4),
        "prob_positive": round(prob_pos, 4),
        "confidence": confidence,
        "n_bootstrap": n_bootstrap,
    }


def _sharpe(returns: np.ndarray, bars_per_year: int = 252) -> float:
    std = returns.std()
    return float(returns.mean() / (std + 1e-10) * np.sqrt(bars_per_year))


# ─── Walk-Forward Analysis ───


def walk_forward_analysis(
    equity_curve: pd.Series,
    trades: List[TradeRecord],
    n_windows: int = 5,
    bars_per_year: int = 252,
) -> Dict[str, Any]:
    """Split backtest into sequential windows, check consistency.

    Each window is evaluated independently (returns normalised to window start).

    Args:
        equity_curve: Equity time series.
        trades: Completed trades.
        n_windows: Number of non-overlapping windows.
        bars_per_year: Annualisation factor.

    Returns:
        Dict with per_window stats, consistency metrics.
    """
    if len(equity_curve) < n_windows * 2:
        return {"error": f"need at least {n_windows * 2} bars for {n_windows} windows"}

    indices = equity_curve.index
    window_size = len(indices) // n_windows
    windows = []

    for i in range(n_windows):
        start_idx = i * window_size
        end_idx = (i + 1) * window_size if i < n_windows - 1 else len(indices)
        win_eq = equity_curve.iloc[start_idx:end_idx]
        win_start = indices[start_idx]
        win_end = indices[end_idx - 1]

        # Per-window trades
        win_trades = [
            t for t in trades
            if win_start <= t.entry_time <= win_end
        ]

        # Per-window metrics
        ret = float(win_eq.iloc[-1] / win_eq.iloc[0] - 1) if win_eq.iloc[0] > 0 else 0.0
        win_returns = win_eq.pct_change().dropna().values
        sharpe = _sharpe(win_returns, bars_per_year) if len(win_returns) > 1 else 0.0

        peak = win_eq.cummax()
        dd = (win_eq - peak) / peak.replace(0, 1)
        max_dd = float(dd.min())

        win_pnls = [t.pnl for t in win_trades]
        win_rate = (
            len([p for p in win_pnls if p > 0]) / len(win_pnls)
            if win_pnls else 0.0
        )

        windows.append({
            "window": i + 1,
            "start": str(win_start.date()) if hasattr(win_start, "date") else str(win_start),
            "end": str(win_end.date()) if hasattr(win_end, "date") else str(win_end),
            "return": round(ret, 6),
            "sharpe": round(sharpe, 4),
            "max_dd": round(max_dd, 6),
            "trades": len(win_trades),
            "win_rate": round(win_rate, 4),
        })

    # Consistency metrics
    returns_list = [w["return"] for w in windows]
    sharpes_list = [w["sharpe"] for w in windows]
    profitable_windows = sum(1 for r in returns_list if r > 0)

    return {
        "n_windows": n_windows,
        "windows": windows,
        "profitable_windows": profitable_windows,
        "consistency_rate": round(profitable_windows / n_windows, 4),
        "return_mean": round(float(np.mean(returns_list)), 6),
        "return_std": round(float(np.std(returns_list)), 6),
        "sharpe_mean": round(float(np.mean(sharpes_list)), 4),
        "sharpe_std": round(float(np.std(sharpes_list)), 4),
    }


# ─── Runner integration ───


def run_validation(
    config: Dict[str, Any],
    equity_curve: pd.Series,
    trades: List[TradeRecord],
    initial_capital: float,
    bars_per_year: int = 252,
    positions_df: pd.DataFrame | None = None,
    returns_df: pd.DataFrame | None = None,
) -> Dict[str, Any]:
    """Run statistical validation on backtest results.

    All four tests run by default:
      - Monte Carlo trade-order permutation
      - Monte Carlo return-randomization (signal-timing significance)
      - Bootstrap Sharpe CI
      - Walk-Forward consistency

    Use ``config["validation"]`` to supply custom parameters for any test,
    or set ``"skip": true`` on a test to disable it.

    Config example (all optional — defaults are sensible)::

        "validation": {
            "monte_carlo": {"n_simulations": 2000},
            "monte_carlo_returns": {"n_simulations": 10000},
            "bootstrap": {"confidence": 0.99},
            "walk_forward": {"n_windows": 8},
            "min_trades": 5,        # threshold checks (separate system)
            "max_drawdown": -0.70
        }

    Args:
        config: Backtest config dict.
        equity_curve: Equity time series.
        trades: Completed trades.
        initial_capital: Starting capital.
        bars_per_year: Annualisation factor.
        positions_df: Optional DataFrame of daily target weights (from
            backtest).  Passed to ``monte_carlo_returns_test`` for accurate
            exposure detection.

    Returns:
        Dict keyed by validation type with results.
    """
    v_cfg = config.get("validation", {})
    results: Dict[str, Any] = {}

    # ── Monte Carlo: always run unless explicitly skipped ──
    mc_cfg = v_cfg.get("monte_carlo", {})
    if not isinstance(mc_cfg, dict):
        mc_cfg = {}
    if not mc_cfg.get("skip"):
        results["monte_carlo"] = monte_carlo_test(
            trades, initial_capital,
            n_simulations=mc_cfg.get("n_simulations", 1000),
            seed=mc_cfg.get("seed", 42),
        )

    # ── Monte Carlo Return-Randomization: always run unless explicitly skipped ──
    mcr_cfg = v_cfg.get("monte_carlo_returns", {})
    if not isinstance(mcr_cfg, dict):
        mcr_cfg = {}
    if not mcr_cfg.get("skip"):
        results["monte_carlo_returns"] = monte_carlo_returns_test(
            equity_curve, positions_df=positions_df,
            returns_df=returns_df,
            bars_per_year=bars_per_year,
            n_simulations=mcr_cfg.get("n_simulations", 10000),
            seed=mcr_cfg.get("seed", 42),
        )

    # ── Bootstrap Sharpe CI: always run unless explicitly skipped ──
    bs_cfg = v_cfg.get("bootstrap", {})
    if not isinstance(bs_cfg, dict):
        bs_cfg = {}
    if not bs_cfg.get("skip"):
        results["bootstrap"] = bootstrap_sharpe_ci(
            equity_curve, bars_per_year=bars_per_year,
            n_bootstrap=bs_cfg.get("n_bootstrap", 1000),
            confidence=bs_cfg.get("confidence", 0.95),
            seed=bs_cfg.get("seed", 42),
        )

    # ── Walk-Forward: always run unless explicitly skipped ──
    wf_cfg = v_cfg.get("walk_forward", {})
    if not isinstance(wf_cfg, dict):
        wf_cfg = {}
    if not wf_cfg.get("skip"):
        results["walk_forward"] = walk_forward_analysis(
            equity_curve, trades,
            n_windows=wf_cfg.get("n_windows", 5),
            bars_per_year=bars_per_year,
        )

    return results


# ─── Standalone CLI ───


def _load_equity(run_dir: Path) -> pd.Series:
    """Load equity curve from artifacts/equity.csv."""
    path = run_dir / "artifacts" / "equity.csv"
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df["equity"]


def _load_trades(run_dir: Path) -> List[TradeRecord]:
    """Load trades from artifacts/trades.csv and convert to TradeRecord list."""
    path = run_dir / "artifacts" / "trades.csv"
    df = pd.read_csv(path)
    if df.empty:
        return []

    # trades.csv has entry+exit row pairs; extract exit rows (they have pnl != 0)
    trades = []
    exit_rows = df[df["pnl"] != 0].reset_index(drop=True)
    for _, row in exit_rows.iterrows():
        trades.append(TradeRecord(
            symbol=str(row.get("code", "")),
            direction=1 if row.get("side") == "sell" else -1,
            entry_price=0.0,
            exit_price=float(row.get("price", 0)),
            entry_time=pd.Timestamp(row.get("timestamp", "2000-01-01")),
            exit_time=pd.Timestamp(row.get("timestamp", "2000-01-01")),
            size=float(row.get("qty", 0)),
            leverage=1.0,
            pnl=float(row.get("pnl", 0)),
            pnl_pct=float(row.get("return_pct", 0)),
            exit_reason=str(row.get("reason", "signal")),
            holding_bars=int(row.get("holding_days", 0)),
            commission=0.0,
        ))
    return trades


def main(run_dir: Path) -> Dict[str, Any]:
    """Run all three validations on existing backtest artifacts.

    Reads equity.csv, trades.csv, and config.json from run_dir.

    Args:
        run_dir: Directory with artifacts/ subdirectory.

    Returns:
        Validation results dict.
    """
    import json

    # Load config for initial_cash
    config_path = run_dir / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        config = {}
    initial_capital = config.get("initial_cash", 1_000_000)

    equity = _load_equity(run_dir)
    trades = _load_trades(run_dir)

    results = {
        "monte_carlo": monte_carlo_test(trades, initial_capital),
        "monte_carlo_returns": monte_carlo_returns_test(equity),
        "bootstrap": bootstrap_sharpe_ci(equity),
        "walk_forward": walk_forward_analysis(equity, trades),
    }

    # Write results
    out = run_dir / "artifacts" / "validation.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: python -m backtest.validation <run_dir>")
        sys.exit(1)
    main(Path(sys.argv[1]))
