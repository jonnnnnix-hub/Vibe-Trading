# Tier 3 Promotion Criteria — v4 and Beyond

## Context

Tier 2 validates that a strategy is statistically real (Bootstrap CI above zero,
consistent across time windows, sufficient trade count). Tier 3 raises the bar
to **deployment-grade conviction**: the strategy must demonstrate that its edge
is large enough to survive transaction costs, slippage, and regime changes — and
that it can be distinguished from luck by multiple independent statistical tests.

### Where v3.0 Stands (Tier 2 Baseline)

| Metric | v3.0 (55 tickers) |
|--------|--------------------|
| Sharpe | 1.12 |
| Bootstrap CI | [0.17, 2.14] |
| WF consistency | 80% (4/5) |
| WF Sharpe std | 0.69 |
| MC return-rand p-value | 0.271 |
| Excess return | +34.3% |
| Max drawdown | -17.7% |
| Trade count | 147 |

### What Tier 3 Must Prove

1. **Signal significance** — the strategy's stock selection AND timing
   demonstrably beat random (not just order-independence or positive drift)
2. **Robustness** — consistent across every sub-period, not just 4 out of 5
3. **Precision** — narrow Sharpe confidence interval (the strategy's quality is
   well-characterized, not merely "somewhere between 0.17 and 2.14")
4. **Survivable drawdowns** — max drawdown within practical tolerance
5. **Excess return** — must beat the benchmark in absolute terms

---

## Tier 3 Criteria

### A. Statistical Significance

| Criterion | Threshold | Rationale |
|-----------|-----------|-----------|
| MC return-randomization p-value | **< 0.05** | Conventional significance. The strategy's timing must beat random day-selection at 95% confidence. At v3.0's 76% exposure, this requires either sharper timing (lower exposure fraction with higher per-day alpha) or a longer backtest window. |
| Bootstrap 95% CI lower bound | **> 0.30** | The entire CI must clear a non-trivial Sharpe. v3.0's lower bound (0.17) is above zero but still includes near-zero performance. A floor of 0.30 means even the pessimistic bound implies a usable strategy. |
| Bootstrap prob(Sharpe > 0) | **> 99%** | Near-certainty of positive risk-adjusted return. v3.0 is at 99.2% — already close. |

### B. Temporal Consistency

| Criterion | Threshold | Rationale |
|-----------|-----------|-----------|
| Walk-Forward consistency | **100% (5/5 windows profitable)** | No dead windows. v3.0's Window 1 (Jan–Nov 2022) produced 0 trades because the 200-SMA filter kept the strategy fully in cash during the bear market. Tier 3 requires either (a) generating trades in all regimes or (b) the cash allocation itself counting as a profitable decision vs benchmark. |
| Walk-Forward Sharpe std | **< 0.50** | Tight dispersion. v3.0 is at 0.69. Achieving < 0.50 requires more uniform alpha across windows — the strategy can't rely on one strong window to carry the average. |
| Walk-Forward min window Sharpe | **> 0.0** | Every individual window must have positive risk-adjusted return. No single window can drag the strategy negative. |

### C. Performance Floors

| Criterion | Threshold | Rationale |
|-----------|-----------|-----------|
| Sharpe ratio | **> 1.0** | Minimum annualized risk-adjusted return. Below 1.0, the strategy's return doesn't adequately compensate for volatility. v3.0 clears this (1.12). |
| Excess return vs benchmark | **> 0%** | Must beat equal-weight passive. v3.0 clears this (+34.3%). |
| Max drawdown | **> -25%** | Practical capital preservation. A 25% drawdown is recoverable; beyond that, behavioral risk (investor panic) increases sharply. v3.0 clears this (-17.7%). |
| Trade count | **> 100** | Sufficient statistical power for all tests. v3.0 clears this (147). |

### D. Cross-Validation (New for Tier 3)

| Criterion | Threshold | Rationale |
|-----------|-----------|-----------|
| Out-of-sample Sharpe decay | **< 30%** | If the strategy is run on a hold-out period (last 20% of data, excluded from parameter selection), Sharpe should not decay by more than 30% vs in-sample. This guards against overfitting. |
| Multi-asset transferability (optional) | Sharpe > 0.5 on one additional market | The same signal logic should produce positive risk-adjusted return on at least one other asset class (e.g., v3 momentum on HK equities). This is aspirational, not required. |

---

## Gap Analysis: What v4 Must Improve

| Tier 3 Criterion | v3.0 Status | Gap | Path to Close |
|-------------------|-------------|-----|---------------|
| MC return-rand p < 0.05 | 0.271 | **Large** | Lower exposure fraction (more selective entry) or extend backtest to 2015+ for more data points. A strategy with 50% exposure and the same alpha would produce p < 0.05. |
| Bootstrap CI lower > 0.30 | 0.167 | **Moderate** | Higher Sharpe (> 1.3) or longer history. CI width scales as ~1/sqrt(n_years). |
| WF 100% consistency | 80% (4/5) | **Moderate** | Window 1 has 0 trades. Options: (a) add a low-conviction signal for bear markets, (b) count benchmark-relative performance (cash vs -20% market = positive alpha). |
| WF Sharpe std < 0.50 | 0.69 | **Moderate** | More uniform signal quality. Current range: 0.0–1.98. v4 should aim for all windows in [0.5, 1.5]. |
| OOS Sharpe decay < 30% | Not tested | **Unknown** | Requires hold-out backtest design. |

### Recommended v4 Architecture Changes

1. **Selective exposure** — Tighter entry criteria to reduce exposure from 76% to ~50–60%, concentrating alpha on high-conviction days. This directly improves MC return-rand p-value.
2. **Bear-market signal** — Add a defensive momentum signal (e.g., short-term mean reversion or quality factor) that generates trades during bear markets to fill Window 1.
3. **Longer history** — Extend start_date to 2015-01-01 for ~11 years of data (vs 4.3 years). More observations narrow the Bootstrap CI and increase MC test power.
4. **Hold-out validation** — Reserve 2024-2026 as out-of-sample; train/select on 2015-2023. Report OOS decay metric.
5. **Regime-adaptive rebalancing** — Monthly rebalancing in trending markets, faster rebalancing (weekly) during high-volatility regimes to capture more timing alpha.

---

## Summary Table

| Criterion | Tier 1 | Tier 2 | Tier 3 |
|-----------|--------|--------|--------|
| Bootstrap CI lower | — | > 0.0 | **> 0.30** |
| Bootstrap prob_positive | > 90% | > 95% | **> 99%** |
| MC return-rand p-value | — | — | **< 0.05** |
| WF consistency | >= 60% | >= 80% | **100%** |
| WF Sharpe std | — | < 1.0 | **< 0.50** |
| WF min window Sharpe | — | — | **> 0.0** |
| Sharpe ratio | — | — | **> 1.0** |
| Excess return | — | — | **> 0%** |
| Max drawdown | > -50% | > -50% | **> -25%** |
| Trade count | >= 30 | > 100 | **> 100** |
| OOS Sharpe decay | — | — | **< 30%** |

---

*Authored 2026-04-12. Reference: Issue #6, v3.0 release.*
