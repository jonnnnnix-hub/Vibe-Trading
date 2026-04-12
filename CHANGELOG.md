# Changelog

All notable changes to the Vibe-Trading backtesting framework.

## [v3.0] — 2026-04-12

**55-Ticker US Equity Momentum — Tier 2 Validated**

Tagged on commit `5cf4ff1`. Full release notes:
[GitHub Release](https://github.com/jonnnnnix-hub/Vibe-Trading/releases/tag/v3.0)

### Strategy

- 12-1 month relative momentum (Jegadeesh & Titman, 1993)
- Cross-sectional ranking: long top-half with positive momentum
- Per-stock 200-SMA regime filter with trend-strength scaling
- Monthly rebalance (21 trading days)
- 55 US large-cap equities across 11 GICS sectors

### Performance (Jan 2022 — Apr 2026)

| Metric | Value |
|--------|-------|
| Total Return | +89.4% |
| Excess Return | +34.3% |
| Annual Return | +16.2% |
| Sharpe Ratio | 1.12 |
| Sortino Ratio | 1.38 |
| Max Drawdown | -17.7% |
| Trade Count | 147 |

### Tier 2 Validation Pass

| Criterion | Target | Result | Status |
|-----------|--------|--------|--------|
| Bootstrap CI Lower | > 0.0 | 0.167 | Pass |
| Bootstrap prob_positive | > 95% | 99.2% | Pass |
| Walk-Forward Consistency | >= 80% | 80% (4/5) | Pass |
| Walk-Forward Sharpe std | < 0.75 | 0.69 | Pass |
| Trade Count | > 100 | 147 | Pass |

### Monte Carlo Validation

| Test | p-value | Interpretation |
|------|---------|----------------|
| Trade-order permutation | 0.480 | Trade ordering does not affect Sharpe (expected for diversified portfolio) |
| Return-randomization (signal timing) | 0.271 | Strategy timing outperforms random by 15% (Sharpe 1.13 vs 0.98); alpha from stock selection + regime filter, not pure timing |

### Added

- `monte_carlo_returns_test()` — signal-timing significance test (10k simulations, randomizes invested-day assignment)
- Validation pipeline now runs 4 tests automatically: MC trade-order, MC return-randomization, Bootstrap Sharpe CI, Walk-Forward
- `positions_df` parameter wired through base engine to validation for accurate exposure detection

---

## [v2.1] — 2026-04-12

**Phase 1: Validation Pipeline + Strategy Store**

Commit `fc9fe51`.

### Added

- `backtest/validation.py` — Monte Carlo, Bootstrap, Walk-Forward tests run automatically on every backtest
- `backtest/strategy_store.py` — SQLite-backed Phase 1 strategy memory store
- `backtest/backfill_store.py` — Backfill script for existing 11 runs
- `strategy_store.db` — SQLite database with all historical run data
- Automated validation integrated into `base.py` (non-optional)
- Strategy store auto-populates from `base.py` on every run (non-blocking)

### Fixed

- `validation.py` always runs MC/Bootstrap/WF by default (no config flag required)

### Quality

- 415 tests passing (19 validation + 396 existing)

---

## [v2.0] — 2026-04-12

**E2E Testing + Optimizations**

### Fixed

- OKX crypto loader: patched with `/market/history-candles` fallback for pre-2024 data
- MATIC-USDT handling: graceful skip for delisted/renamed tokens

### Optimized

- Pre-built index sets for O(1) bar membership checks in execution loop
- Pre-extracted target weights as numpy matrix for fast row access
- Batch trade CSV construction (pre-allocated list)
- Reduced redundant equity recalculations in bar loop
- Optimized signal engine close-price alignment
- Streamlined validation dispatcher
- Minimized per-bar position iteration overhead

### Quality

- 26 E2E tests added
- 415 tests passing total
- 2 bug fixes + 7 performance optimizations documented in Issue #2

---

## [v1.0] — 2026-04-12

**Initial Setup + Multi-Asset Backtesting**

### Added

- Forked from [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading)
- Environment setup: OpenRouter (deepseek-v3.2), yfinance (US/HK), OKX (crypto)
- BaseEngine with bar-by-bar execution, market rule enforcement, optimizer support
- GlobalEquity engine (yfinance) for US and HK equities
- CryptoEngine (OKX) with history-candles fallback
- Equal-volatility optimizer
- 389 tests passing on initial setup

### Backtest Runs

| Run | Asset Class | Return | Sharpe | Max DD |
|-----|------------|--------|--------|--------|
| v1 US Equity | US | -39.4% | -0.98 | -42.7% |
| v2 US Equity | US | +27.6% | 0.50 | -23.8% |
| v3 Momentum (15 tickers) | US | +85.4% | 0.95 | -19.4% |
| v3 Crypto | Crypto | -48.0% | -0.25 | -74.1% |
| v3 HK Equity | HK | +52.4% | 0.56 | -32.2% |
| v3 Multi-Asset | Mixed | -41.2% | -0.49 | -45.4% |
| v4 Crypto | Crypto | -50.9% | -0.23 | -62.8% |
| v4b Crypto (BTC-gated) | Crypto | +152.2% | 0.85 | -42.3% |
| v4b HK (HSI-gated) | HK | +51.4% | 0.58 | -27.2% |
| v4b Stress: Bear | Crypto | +66.1% | 0.70 | -34.7% |
| v4b Stress: COVID | Crypto | +1,160% | 2.08 | -35.2% |

---

## GitHub Issues

| Issue | Title | Status |
|-------|-------|--------|
| #1 | Initial Setup | Closed |
| #2 | Changelog: 2 bugs + 7 optimizations | Open |
| #3 | Stress-test v4b BTC regime gate | Closed |
| #4 | Look-ahead bias audit | Open |
| #5 | Phase 1 complete — validation + strategy store | Open |
| #6 | Validation acceptance criteria (Tier 1/2/3) | Open |

[v3.0]: https://github.com/jonnnnnix-hub/Vibe-Trading/releases/tag/v3.0
