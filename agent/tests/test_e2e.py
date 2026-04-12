"""End-to-end tests: full pipeline from data loading through engine execution to metrics.

Tests cover:
  - yfinance loader → GlobalEquityEngine → metrics (US market)
  - OKX-style loader → CryptoEngine → metrics (with funding + liquidation)
  - Multi-symbol backtest with optimizer
  - Auto-source routing
  - CLI entry points (help, skills, swarm-presets)
  - API server import and route registration
  - Validation pipeline (monte carlo + bootstrap + walk-forward)
  - Signal engine code loading
  - Artifact file generation
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import pytest

from backtest.engines.base import BaseEngine, _align, _load_optimizer
from backtest.engines.china_a import ChinaAEngine
from backtest.engines.china_futures import ChinaFuturesEngine
from backtest.engines.crypto import CryptoEngine
from backtest.engines.forex import ForexEngine
from backtest.engines.global_equity import GlobalEquityEngine
from backtest.engines.global_futures import GlobalFuturesEngine
from backtest.loaders.registry import LOADER_REGISTRY, _ensure_registered, resolve_loader
from backtest.metrics import calc_bars_per_year, calc_metrics, win_rate_and_stats
from backtest.models import EquitySnapshot, Position, TradeRecord
from backtest.runner import (
    BacktestConfigSchema,
    _detect_market,
    _detect_source,
    _group_codes_by_market,
    _normalize_codes,
)
from backtest.validation import (
    bootstrap_sharpe_ci,
    monte_carlo_test,
    run_validation,
    walk_forward_analysis,
)


# ─── Helpers ───


def _make_ohlcv(n: int = 100, start: str = "2025-01-01", base: float = 100.0, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data with realistic random walk."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n)
    returns = rng.normal(0.0005, 0.02, n)
    close = base * np.exp(np.cumsum(returns))
    high = close * (1 + rng.uniform(0, 0.015, n))
    low = close * (1 - rng.uniform(0, 0.015, n))
    opn = close * (1 + rng.normal(0, 0.005, n))
    volume = rng.integers(1_000_000, 10_000_000, n).astype(float)
    return pd.DataFrame(
        {"open": opn, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


class _MockSignalEngine:
    """Generates alternating long/flat signals for testing."""

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        signals = {}
        for code, df in data_map.items():
            sig = pd.Series(0.0, index=df.index)
            sig.iloc[::5] = 1.0  # go long every 5th bar
            sig.iloc[2::5] = 0.0  # flatten 2 bars later
            signals[code] = sig
        return signals


class _MockLoader:
    """Returns pre-built data maps."""

    name = "mock"

    def __init__(self, data_map: dict):
        self._data = data_map

    def fetch(self, codes, start_date, end_date, fields=None, interval="1D"):
        return {c: self._data[c] for c in codes if c in self._data}


# ─── E2E: GlobalEquityEngine (US) ───


class TestE2EGlobalEquity:
    """Full pipeline: synthetic data → GlobalEquityEngine → metrics + artifacts."""

    def test_us_equity_full_pipeline(self, tmp_path):
        data = {"AAPL.US": _make_ohlcv(120, seed=1), "MSFT.US": _make_ohlcv(120, seed=2)}
        config = {
            "codes": ["AAPL.US", "MSFT.US"],
            "start_date": "2025-01-01",
            "end_date": "2025-07-01",
            "initial_cash": 1_000_000,
            "leverage": 1.0,
        }
        engine = GlobalEquityEngine(config, market="us")
        loader = _MockLoader(data)
        signal = _MockSignalEngine()
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        metrics = engine.run_backtest(config, loader, signal, run_dir)

        # Metrics sanity
        assert "final_value" in metrics
        assert "sharpe" in metrics
        assert "max_drawdown" in metrics
        assert metrics["trade_count"] >= 0
        assert metrics["final_value"] > 0

        # Artifacts written
        artifacts = run_dir / "artifacts"
        assert (artifacts / "equity.csv").exists()
        assert (artifacts / "trades.csv").exists()
        assert (artifacts / "metrics.csv").exists()
        assert (artifacts / "positions.csv").exists()

        # Equity CSV loadable and sane
        eq_df = pd.read_csv(artifacts / "equity.csv", index_col=0, parse_dates=True)
        assert "equity" in eq_df.columns
        assert len(eq_df) == 120

    def test_hk_equity_full_pipeline(self, tmp_path):
        data = {"0700.HK": _make_ohlcv(80, seed=3)}
        config = {
            "codes": ["0700.HK"],
            "start_date": "2025-01-01",
            "end_date": "2025-05-01",
            "initial_cash": 500_000,
        }
        engine = GlobalEquityEngine(config, market="hk")
        loader = _MockLoader(data)
        signal = _MockSignalEngine()
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        metrics = engine.run_backtest(config, loader, signal, run_dir)
        assert metrics["final_value"] > 0
        assert metrics["trade_count"] >= 0


# ─── E2E: CryptoEngine ───


class TestE2ECrypto:
    """Full pipeline: synthetic crypto data → CryptoEngine → metrics."""

    def test_crypto_full_pipeline(self, tmp_path):
        data = {"BTC-USDT": _make_ohlcv(90, base=60000, seed=10)}
        config = {
            "codes": ["BTC-USDT"],
            "start_date": "2025-01-01",
            "end_date": "2025-05-01",
            "initial_cash": 100_000,
            "leverage": 2.0,
            "maker_rate": 0.0002,
            "taker_rate": 0.0005,
            "funding_rate": 0.0001,
        }
        engine = CryptoEngine(config)
        loader = _MockLoader(data)
        signal = _MockSignalEngine()
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        metrics = engine.run_backtest(config, loader, signal, run_dir)
        assert metrics["final_value"] > 0
        assert metrics["trade_count"] >= 0
        assert "sharpe" in metrics


# ─── E2E: ChinaAEngine ───


class TestE2EChinaA:
    """Full pipeline: synthetic A-share data → ChinaAEngine → metrics."""

    def test_a_share_pipeline(self, tmp_path):
        data = {"000001.SZ": _make_ohlcv(100, seed=20)}
        config = {
            "codes": ["000001.SZ"],
            "start_date": "2025-01-01",
            "end_date": "2025-06-01",
            "initial_cash": 500_000,
        }
        engine = ChinaAEngine(config)
        loader = _MockLoader(data)
        signal = _MockSignalEngine()
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        metrics = engine.run_backtest(config, loader, signal, run_dir)
        assert metrics["final_value"] > 0


# ─── E2E: ForexEngine ───


class TestE2EForex:
    """Full pipeline: synthetic forex data → ForexEngine → metrics."""

    def test_forex_pipeline(self, tmp_path):
        data = {"EUR/USD": _make_ohlcv(80, base=1.08, seed=30)}
        config = {
            "codes": ["EUR/USD"],
            "start_date": "2025-01-01",
            "end_date": "2025-05-01",
            "initial_cash": 100_000,
            "leverage": 10.0,  # moderate leverage to avoid negative equity
        }
        engine = ForexEngine(config)
        loader = _MockLoader(data)
        signal = _MockSignalEngine()
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        metrics = engine.run_backtest(config, loader, signal, run_dir)
        assert metrics["final_value"] > 0

    def test_forex_high_leverage_no_crash(self, tmp_path):
        """Ensure 100x leverage doesn't crash metrics (negative equity edge case)."""
        data = {"EUR/USD": _make_ohlcv(80, base=1.08, seed=30)}
        config = {
            "codes": ["EUR/USD"],
            "start_date": "2025-01-01",
            "end_date": "2025-05-01",
            "initial_cash": 100_000,
            "leverage": 100.0,
        }
        engine = ForexEngine(config)
        loader = _MockLoader(data)
        signal = _MockSignalEngine()
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        # Should not raise (was crashing with complex number TypeError before fix)
        metrics = engine.run_backtest(config, loader, signal, run_dir)
        assert "final_value" in metrics
        assert "sharpe" in metrics


# ─── E2E: Futures Engines ───


class TestE2EFutures:
    """Full pipeline tests for China and global futures engines."""

    def test_china_futures_pipeline(self, tmp_path):
        data = {"IF2406.CFFEX": _make_ohlcv(60, base=3800, seed=40)}
        config = {
            "codes": ["IF2406.CFFEX"],
            "start_date": "2025-01-01",
            "end_date": "2025-04-01",
            "initial_cash": 2_000_000,
        }
        engine = ChinaFuturesEngine(config)
        loader = _MockLoader(data)
        signal = _MockSignalEngine()
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        metrics = engine.run_backtest(config, loader, signal, run_dir)
        assert metrics["final_value"] > 0

    def test_global_futures_pipeline(self, tmp_path):
        data = {"ESZ4": _make_ohlcv(60, base=5100, seed=50)}
        config = {
            "codes": ["ESZ4"],
            "start_date": "2025-01-01",
            "end_date": "2025-04-01",
            "initial_cash": 500_000,
        }
        engine = GlobalFuturesEngine(config)
        loader = _MockLoader(data)
        signal = _MockSignalEngine()
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        metrics = engine.run_backtest(config, loader, signal, run_dir)
        assert metrics["final_value"] > 0


# ─── E2E: Validation Pipeline ───


class TestE2EValidation:
    """Full validation pipeline on synthetic backtest output."""

    def test_full_validation_pipeline(self):
        rng = np.random.default_rng(99)
        equity = pd.Series(
            1_000_000 * np.exp(np.cumsum(rng.normal(0.001, 0.01, 200))),
            index=pd.bdate_range("2025-01-01", periods=200),
        )
        trades = [
            TradeRecord(
                symbol="TEST", direction=1,
                entry_price=100, exit_price=100 + rng.normal(2, 5),
                entry_time=pd.Timestamp("2025-01-10"), exit_time=pd.Timestamp("2025-01-15"),
                size=100, leverage=1.0, pnl=rng.normal(200, 500),
                pnl_pct=rng.normal(2, 5), exit_reason="signal",
                holding_bars=5, commission=10,
            )
            for _ in range(30)
        ]

        config = {
            "validation": {
                "monte_carlo": {"n_simulations": 100, "seed": 42},
                "bootstrap": {"n_bootstrap": 100, "confidence": 0.95, "seed": 42},
                "walk_forward": {"n_windows": 4},
            }
        }

        results = run_validation(config, equity, trades, 1_000_000, 252)

        assert "monte_carlo" in results
        assert "bootstrap" in results
        assert "walk_forward" in results
        assert 0 <= results["monte_carlo"]["p_value_sharpe"] <= 1
        assert results["bootstrap"]["ci_lower"] <= results["bootstrap"]["ci_upper"]
        assert results["walk_forward"]["n_windows"] == 4
        assert len(results["walk_forward"]["windows"]) == 4


# ─── E2E: Multi-symbol with optimizer ───


class TestE2EOptimizer:
    """Multi-symbol backtest with risk parity optimizer."""

    def test_risk_parity_optimizer(self, tmp_path):
        data = {
            "AAPL.US": _make_ohlcv(100, seed=60),
            "MSFT.US": _make_ohlcv(100, seed=61),
            "GOOGL.US": _make_ohlcv(100, seed=62),
        }
        config = {
            "codes": ["AAPL.US", "MSFT.US", "GOOGL.US"],
            "start_date": "2025-01-01",
            "end_date": "2025-06-01",
            "initial_cash": 1_000_000,
            "optimizer": "risk_parity",
        }
        engine = GlobalEquityEngine(config, market="us")
        loader = _MockLoader(data)
        signal = _MockSignalEngine()
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        metrics = engine.run_backtest(config, loader, signal, run_dir)
        assert metrics["final_value"] > 0
        assert metrics["trade_count"] >= 0


# ─── E2E: Auto-source routing ───


class TestE2EAutoRouting:
    """Market detection routes symbols to correct engines."""

    def test_market_detection_comprehensive(self):
        cases = {
            "000001.SZ": "a_share",
            "600519.SH": "a_share",
            "AAPL.US": "us_equity",
            "0700.HK": "hk_equity",
            "BTC-USDT": "crypto",
            "ETH/USDT": "crypto",
            "IF2406.CFFEX": "futures",
            "rb2410.SHFE": "futures",
            "ESZ4": "futures",
            "EUR/USD": "forex",
            "EURUSD.FX": "forex",
        }
        for code, expected in cases.items():
            assert _detect_market(code) == expected, f"{code} should be {expected}"

    def test_code_normalization(self):
        assert _normalize_codes(["BTC/USDT", "eth/usdt"], "okx") == ["BTC-USDT", "ETH-USDT"]
        assert _normalize_codes(["BTC/USDT"], "ccxt") == ["BTC-USDT"]
        assert _normalize_codes(["AAPL.US"], "yfinance") == ["AAPL.US"]

    def test_group_codes_by_market(self):
        codes = ["AAPL.US", "BTC-USDT", "000001.SZ", "EUR/USD"]
        groups = _group_codes_by_market(codes)
        assert "us_equity" in groups
        assert "crypto" in groups
        assert "a_share" in groups
        assert "forex" in groups


# ─── E2E: Loader registry ───


class TestE2ELoaderRegistry:
    """Verify all loaders register and resolve correctly."""

    def test_all_loaders_registered(self):
        _ensure_registered()
        expected = {"tushare", "okx", "yfinance", "akshare", "ccxt"}
        registered = set(LOADER_REGISTRY.keys())
        assert expected.issubset(registered), f"Missing loaders: {expected - registered}"

    def test_yfinance_is_available(self):
        _ensure_registered()
        loader = LOADER_REGISTRY["yfinance"]()
        assert loader.is_available()

    def test_resolve_us_equity(self):
        loader = resolve_loader("us_equity")
        assert loader.name in ("yfinance", "akshare")


# ─── E2E: Config validation ───


class TestE2EConfigValidation:
    """BacktestConfigSchema validates and rejects bad configs."""

    def test_valid_config(self):
        cfg = BacktestConfigSchema(
            codes=["AAPL.US"], start_date="2025-01-01", end_date="2025-06-01",
        )
        assert cfg.codes == ["AAPL.US"]

    def test_empty_codes_rejected(self):
        with pytest.raises(Exception):
            BacktestConfigSchema(codes=[], start_date="2025-01-01", end_date="2025-06-01")

    def test_reversed_dates_rejected(self):
        with pytest.raises(Exception):
            BacktestConfigSchema(codes=["X"], start_date="2025-12-01", end_date="2025-01-01")

    def test_invalid_interval_rejected(self):
        with pytest.raises(Exception):
            BacktestConfigSchema(
                codes=["X"], start_date="2025-01-01", end_date="2025-06-01",
                interval="2D",
            )


# ─── E2E: CLI smoke tests ───


class TestE2ECLI:
    """Smoke test CLI entry points (no LLM key needed)."""

    def test_cli_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "cli", "--help"],
            capture_output=True, text=True, cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        assert "vibe-trading" in result.stdout.lower() or "usage" in result.stdout.lower()

    def test_cli_skills(self):
        result = subprocess.run(
            [sys.executable, "-m", "cli", "--skills"],
            capture_output=True, text=True, cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        assert "strategy-generate" in result.stdout or "Skills" in result.stdout

    def test_cli_swarm_presets(self):
        result = subprocess.run(
            [sys.executable, "-m", "cli", "--swarm-presets"],
            capture_output=True, text=True, cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        assert "investment_committee" in result.stdout or "Swarm" in result.stdout


# ─── E2E: API server import ───


class TestE2EAPIServer:
    """Verify API server can be imported and routes are registered."""

    def test_api_server_importable(self):
        import api_server
        assert hasattr(api_server, "app")

    def test_api_routes_registered(self):
        import api_server
        routes = [r.path for r in api_server.app.routes]
        assert "/runs" in routes or any("/runs" in r for r in routes)


# ─── E2E: Signal engine code loading ───


class TestE2ESignalEngineLoading:
    """Test that signal engine modules load from file paths."""

    def test_load_signal_engine_from_file(self, tmp_path):
        code_dir = tmp_path / "code"
        code_dir.mkdir()
        sig_file = code_dir / "signal_engine.py"
        sig_file.write_text(
            "import pandas as pd\n"
            "class SignalEngine:\n"
            "    def generate(self, data_map):\n"
            "        return {c: pd.Series(1.0, index=df.index) for c, df in data_map.items()}\n"
        )

        from backtest.runner import _load_module_from_file
        mod = _load_module_from_file(sig_file, "test_signal_engine")
        assert hasattr(mod, "SignalEngine")
        engine = mod.SignalEngine()
        test_data = {"X": pd.DataFrame({"close": [1, 2, 3]}, index=pd.date_range("2025-01-01", periods=3))}
        result = engine.generate(test_data)
        assert "X" in result
        assert len(result["X"]) == 3
