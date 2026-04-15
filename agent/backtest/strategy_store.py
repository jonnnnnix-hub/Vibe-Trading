"""Strategy Memory Store — persistent record of every backtest run.

Phase 1 of the self-learning feedback loop. Records inputs, outputs,
validation results, and strategy fingerprints in SQLite so the system
can learn from its own history.

Design goals:
  - Zero-config: auto-creates DB on first use
  - Non-blocking: failures here never crash a backtest
  - Append-only: records are immutable once written
  - Queryable: SQL for cross-run analysis

Usage:
  from backtest.strategy_store import StrategyStore
  store = StrategyStore()  # uses default path
  store.record_run(run_dir, config, metrics)
  store.query_best("crypto", "sharpe", limit=5)
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "strategy_store.db"

_SCHEMA = """
-- Every backtest execution
CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,           -- directory name (e.g. "real_data_v3")
    timestamp       TEXT NOT NULL,              -- ISO 8601
    market_type     TEXT NOT NULL DEFAULT '',   -- us_equity / crypto / hk_equity / mixed
    instruments     TEXT NOT NULL DEFAULT '[]', -- JSON array of tickers
    date_range      TEXT NOT NULL DEFAULT '',   -- "2022-01-01 / 2026-04-11"
    strategy_type   TEXT NOT NULL DEFAULT '',   -- momentum / mean-reversion / factor / etc.
    config_json     TEXT NOT NULL DEFAULT '{}', -- full config.json snapshot
    signal_hash     TEXT NOT NULL DEFAULT '',   -- SHA-256 of AST-normalized signal engine
    signal_source   TEXT NOT NULL DEFAULT '',   -- full signal_engine.py source
    parent_run_id   TEXT,                       -- lineage: which run this iterated from
    notes           TEXT NOT NULL DEFAULT ''
);

-- Scalar metrics (one row per run)
CREATE TABLE IF NOT EXISTS metrics (
    run_id              TEXT PRIMARY KEY REFERENCES runs(run_id),
    total_return        REAL,
    annual_return       REAL,
    excess_return       REAL,
    benchmark_return    REAL,
    sharpe              REAL,
    sortino             REAL,
    calmar              REAL,
    max_drawdown        REAL,
    win_rate            REAL,
    profit_factor       REAL,
    profit_loss_ratio   REAL,
    trade_count         INTEGER,
    avg_holding_days    REAL,
    max_consecutive_loss INTEGER,
    information_ratio   REAL,
    quality_tier        INTEGER DEFAULT 0  -- 0=untested, 1/2/3=tier achieved
);

-- Statistical validation results
CREATE TABLE IF NOT EXISTS validation (
    run_id                  TEXT PRIMARY KEY REFERENCES runs(run_id),
    mc_p_value_sharpe       REAL,
    mc_p_value_max_dd       REAL,
    mc_actual_sharpe        REAL,
    mc_simulated_mean       REAL,
    mc_n_simulations        INTEGER,
    bs_observed_sharpe      REAL,
    bs_ci_lower             REAL,
    bs_ci_upper             REAL,
    bs_prob_positive        REAL,
    bs_confidence           REAL,
    wf_n_windows            INTEGER,
    wf_consistency_rate     REAL,
    wf_sharpe_mean          REAL,
    wf_sharpe_std           REAL,
    wf_return_mean          REAL,
    wf_windows_json         TEXT    -- JSON array of per-window stats
);

-- Strategy AST fingerprints for similarity search
CREATE TABLE IF NOT EXISTS fingerprints (
    signal_hash     TEXT PRIMARY KEY,
    ast_dump        TEXT NOT NULL,    -- normalized AST string
    indicators      TEXT NOT NULL DEFAULT '[]',  -- JSON: extracted indicator names
    strategy_dna    TEXT NOT NULL DEFAULT '{}'   -- JSON: structured strategy description
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_runs_market ON runs(market_type);
CREATE INDEX IF NOT EXISTS idx_runs_hash ON runs(signal_hash);
CREATE INDEX IF NOT EXISTS idx_metrics_sharpe ON metrics(sharpe);
CREATE INDEX IF NOT EXISTS idx_metrics_return ON metrics(total_return);
"""


def _detect_market(codes: List[str]) -> str:
    """Infer market type from ticker format."""
    markets = set()
    for c in codes:
        cu = c.upper()
        if cu.endswith(".HK"):
            markets.add("hk_equity")
        elif cu.endswith(".US") or (cu.isalpha() and len(cu) <= 5):
            markets.add("us_equity")
        elif "-USDT" in cu or "/USDT" in cu:
            markets.add("crypto")
        else:
            markets.add("other")
    if len(markets) == 1:
        return markets.pop()
    return "mixed"


def _detect_strategy_type(source: str) -> str:
    """Infer strategy archetype from signal engine source code."""
    src_lower = source.lower()
    if "momentum" in src_lower or "mom_" in src_lower or "pct_change" in src_lower:
        archetype = "momentum"
    elif "mean_revert" in src_lower or "z_score" in src_lower or "bollinger" in src_lower:
        archetype = "mean-reversion"
    elif "factor" in src_lower and "multi" in src_lower:
        archetype = "multi-factor"
    elif "regime" in src_lower or "gate" in src_lower:
        archetype = "regime-gated"
    else:
        archetype = "custom"

    # Append modifiers
    modifiers = []
    if "regime" in src_lower or "gate" in src_lower or "master" in src_lower:
        modifiers.append("regime-filtered")
    if "trailing_stop" in src_lower or "TRAILING_STOP" in source:
        modifiers.append("trailing-stop")
    if "vol_scale" in src_lower or "target_vol" in src_lower:
        modifiers.append("vol-targeted")

    if modifiers:
        return f"{archetype} ({', '.join(modifiers)})"
    return archetype


def _hash_ast(source: str) -> str:
    """SHA-256 of the normalized AST (ignores formatting, comments, docstrings)."""
    try:
        tree = ast.parse(source)
        # Strip docstrings
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                if (node.body and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                    node.body.pop(0)
        dump = ast.dump(tree, annotate_fields=False)
        return hashlib.sha256(dump.encode()).hexdigest()
    except SyntaxError:
        # Fallback to source hash
        return hashlib.sha256(source.encode()).hexdigest()


def _extract_indicators(source: str) -> List[str]:
    """Extract indicator function/variable names from signal engine source."""
    indicators = []
    keywords = {
        "sma": "SMA", "ema": "EMA", "rsi": "RSI", "macd": "MACD",
        "bollinger": "Bollinger", "atr": "ATR", "adx": "ADX",
        "pct_change": "returns", "rolling": "rolling_stat",
        "realized_vol": "realized_vol", "trailing_stop": "trailing_stop",
        "regime": "regime_filter", "golden": "golden_cross",
        "momentum": "momentum", "vol_scale": "vol_scaling",
    }
    src_lower = source.lower()
    for key, name in keywords.items():
        if key in src_lower:
            indicators.append(name)
    return sorted(set(indicators))


class StrategyStore:
    """SQLite-backed strategy memory store."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or _DEFAULT_DB_PATH
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=5)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _ensure_schema(self) -> None:
        try:
            conn = self._get_conn()
            conn.executescript(_SCHEMA)
            conn.commit()
        except Exception as exc:
            logger.warning("Strategy store schema init failed: %s", exc)

    def record_run(
        self,
        run_dir: Path,
        config: Dict[str, Any],
        metrics: Dict[str, Any],
        parent_run_id: Optional[str] = None,
    ) -> Optional[str]:
        """Record a completed backtest run.

        Args:
            run_dir: Path to the run directory.
            config: Full backtest config.
            metrics: Metrics dict (including nested 'validation').
            parent_run_id: Optional parent run for lineage tracking.

        Returns:
            run_id on success, None on failure.
        """
        try:
            run_id = run_dir.name
            codes = config.get("codes", [])
            start = config.get("start_date", "")
            end = config.get("end_date", "")

            # Read signal engine source
            sig_path = run_dir / "code" / "signal_engine.py"
            signal_source = sig_path.read_text(encoding="utf-8") if sig_path.exists() else ""
            signal_hash = _hash_ast(signal_source)
            market_type = _detect_market(codes)
            strategy_type = _detect_strategy_type(signal_source)

            conn = self._get_conn()

            # ── Insert run ──
            conn.execute("""
                INSERT OR REPLACE INTO runs
                (run_id, timestamp, market_type, instruments, date_range,
                 strategy_type, config_json, signal_hash, signal_source, parent_run_id)
                VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id, market_type, json.dumps(codes),
                f"{start} / {end}", strategy_type,
                json.dumps(config), signal_hash, signal_source,
                parent_run_id,
            ))

            # ── Insert metrics ──
            quality_tier = metrics.get("quality_gate", {}).get("quality_tier", 0)
            conn.execute("""
                INSERT OR REPLACE INTO metrics
                (run_id, total_return, annual_return, excess_return,
                 benchmark_return, sharpe, sortino, calmar, max_drawdown,
                 win_rate, profit_factor, profit_loss_ratio, trade_count,
                 avg_holding_days, max_consecutive_loss, information_ratio,
                 quality_tier)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                metrics.get("total_return"),
                metrics.get("annual_return"),
                metrics.get("excess_return"),
                metrics.get("benchmark_return"),
                metrics.get("sharpe"),
                metrics.get("sortino"),
                metrics.get("calmar"),
                metrics.get("max_drawdown"),
                metrics.get("win_rate"),
                metrics.get("profit_factor"),
                metrics.get("profit_loss_ratio"),
                metrics.get("trade_count"),
                metrics.get("avg_holding_days"),
                metrics.get("max_consecutive_loss"),
                metrics.get("information_ratio"),
                quality_tier,
            ))

            # ── Insert validation ──
            v = metrics.get("validation", {})
            mc = v.get("monte_carlo", {})
            bs = v.get("bootstrap", {})
            wf = v.get("walk_forward", {})

            conn.execute("""
                INSERT OR REPLACE INTO validation
                (run_id, mc_p_value_sharpe, mc_p_value_max_dd, mc_actual_sharpe,
                 mc_simulated_mean, mc_n_simulations,
                 bs_observed_sharpe, bs_ci_lower, bs_ci_upper,
                 bs_prob_positive, bs_confidence,
                 wf_n_windows, wf_consistency_rate, wf_sharpe_mean,
                 wf_sharpe_std, wf_return_mean, wf_windows_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                mc.get("p_value_sharpe"),
                mc.get("p_value_max_dd"),
                mc.get("actual_sharpe"),
                mc.get("simulated_sharpe_mean"),
                mc.get("n_simulations"),
                bs.get("observed_sharpe"),
                bs.get("ci_lower"),
                bs.get("ci_upper"),
                bs.get("prob_positive"),
                bs.get("confidence"),
                wf.get("n_windows"),
                wf.get("consistency_rate"),
                wf.get("sharpe_mean"),
                wf.get("sharpe_std"),
                wf.get("return_mean"),
                json.dumps(wf.get("windows", [])),
            ))

            # ── Insert fingerprint ──
            if signal_source:
                indicators = _extract_indicators(signal_source)
                try:
                    ast_dump = ast.dump(ast.parse(signal_source), annotate_fields=False)
                except SyntaxError:
                    ast_dump = ""

                conn.execute("""
                    INSERT OR IGNORE INTO fingerprints
                    (signal_hash, ast_dump, indicators)
                    VALUES (?, ?, ?)
                """, (signal_hash, ast_dump, json.dumps(indicators)))

            conn.commit()
            logger.info("Strategy store: recorded run %s (hash=%s)", run_id, signal_hash[:12])
            return run_id

        except Exception as exc:
            logger.warning("Strategy store: failed to record run: %s", exc)
            return None

    def query_best(
        self,
        market_type: Optional[str] = None,
        metric: str = "sharpe",
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Query top runs by a metric, optionally filtered by market.

        Args:
            market_type: Filter by market (None = all).
            metric: Column name in metrics table to sort by.
            limit: Max results.

        Returns:
            List of dicts with run_id, metric value, strategy_type.
        """
        allowed_metrics = {
            "sharpe", "total_return", "excess_return", "calmar",
            "sortino", "max_drawdown", "win_rate", "information_ratio",
        }
        if metric not in allowed_metrics:
            metric = "sharpe"

        try:
            conn = self._get_conn()
            if market_type:
                rows = conn.execute(f"""
                    SELECT r.run_id, r.strategy_type, r.market_type, r.date_range,
                           m.{metric}, m.total_return, m.sharpe, m.max_drawdown, m.trade_count
                    FROM runs r JOIN metrics m ON r.run_id = m.run_id
                    WHERE r.market_type = ?
                    ORDER BY m.{metric} DESC
                    LIMIT ?
                """, (market_type, limit)).fetchall()
            else:
                rows = conn.execute(f"""
                    SELECT r.run_id, r.strategy_type, r.market_type, r.date_range,
                           m.{metric}, m.total_return, m.sharpe, m.max_drawdown, m.trade_count
                    FROM runs r JOIN metrics m ON r.run_id = m.run_id
                    ORDER BY m.{metric} DESC
                    LIMIT ?
                """, (limit,)).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.warning("Strategy store query failed: %s", exc)
            return []

    def query_by_tier(
        self,
        min_tier: int = 2,
        market_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query runs that achieved a minimum quality tier.

        Args:
            min_tier: Minimum tier (1=Tier-1, 2=Tier-2, 3=Tier-3).
            market_type: Filter by market (None = all).

        Returns:
            List of qualifying runs.
        """
        try:
            conn = self._get_conn()
            if market_type:
                rows = conn.execute("""
                    SELECT r.run_id, r.strategy_type, r.market_type, r.date_range,
                           m.quality_tier, m.sharpe, m.total_return,
                           m.max_drawdown, m.trade_count
                    FROM runs r JOIN metrics m ON r.run_id = m.run_id
                    WHERE r.market_type = ? AND m.quality_tier >= ?
                    ORDER BY m.quality_tier DESC, m.sharpe DESC
                """, (market_type, min_tier)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT r.run_id, r.strategy_type, r.market_type, r.date_range,
                           m.quality_tier, m.sharpe, m.total_return,
                           m.max_drawdown, m.trade_count
                    FROM runs r JOIN metrics m ON r.run_id = m.run_id
                    WHERE m.quality_tier >= ?
                    ORDER BY m.quality_tier DESC, m.sharpe DESC
                """, (min_tier,)).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.warning("Strategy store query_by_tier failed: %s", exc)
            return []

    def find_similar(self, signal_source: str, threshold: float = 0.8) -> List[Dict[str, Any]]:
        """Find runs with similar strategy code (AST-based).

        Compares the AST fingerprint of the given source against stored
        fingerprints. Exact hash match = 100% similar.

        Args:
            signal_source: Python source code of a signal engine.
            threshold: Minimum similarity (0-1). Currently only exact match.

        Returns:
            List of matching runs with similarity scores.
        """
        target_hash = _hash_ast(signal_source)
        try:
            conn = self._get_conn()
            # Exact match first
            rows = conn.execute("""
                SELECT r.run_id, r.strategy_type, m.sharpe, m.total_return,
                       m.max_drawdown, r.date_range
                FROM runs r
                JOIN metrics m ON r.run_id = m.run_id
                WHERE r.signal_hash = ?
            """, (target_hash,)).fetchall()
            return [{"similarity": 1.0, **dict(r)} for r in rows]
        except Exception as exc:
            logger.warning("Strategy store similarity search failed: %s", exc)
            return []

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get full details for a single run."""
        try:
            conn = self._get_conn()
            row = conn.execute("""
                SELECT r.*, m.*, v.*
                FROM runs r
                LEFT JOIN metrics m ON r.run_id = m.run_id
                LEFT JOIN validation v ON r.run_id = v.run_id
                WHERE r.run_id = ?
            """, (run_id,)).fetchone()
            return dict(row) if row else None
        except Exception as exc:
            logger.warning("Strategy store get_run failed: %s", exc)
            return None

    def summary(self) -> Dict[str, Any]:
        """Get a summary of the strategy store contents."""
        try:
            conn = self._get_conn()
            total = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            by_market = conn.execute("""
                SELECT market_type, COUNT(*) as n,
                       ROUND(AVG(m.sharpe), 3) as avg_sharpe,
                       ROUND(MAX(m.sharpe), 3) as best_sharpe,
                       ROUND(AVG(m.max_drawdown), 3) as avg_dd
                FROM runs r JOIN metrics m ON r.run_id = m.run_id
                GROUP BY market_type
            """).fetchall()
            return {
                "total_runs": total,
                "by_market": [dict(r) for r in by_market],
            }
        except Exception as exc:
            logger.warning("Strategy store summary failed: %s", exc)
            return {"total_runs": 0, "by_market": []}

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
