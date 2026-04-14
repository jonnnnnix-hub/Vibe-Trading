#!/usr/bin/env python3
"""Show detailed P&L breakdown for Expert Committee v3."""

import json
import numpy as np
from collections import defaultdict

with open("backtest/results/expert_committee_results.json") as f:
    data = json.load(f)

trades = data["trades"]
winners = [t for t in trades if t["pnl"] > 0]
losers = [t for t in trades if t["pnl"] <= 0]

print("=" * 105)
print("EXPERT COMMITTEE v3 — FULL P&L BREAKDOWN")
print("=" * 105)

# ── Overall ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 50)
print(" OVERALL PERFORMANCE")
print("=" * 50)
print(f"  Starting Capital:    $100,000")
print(f"  Final Equity:        ${data['final_equity']:,.2f}")
print(f"  Net Profit/Loss:     ${data['total_pnl']:+,.2f}  ({data['total_return_pct']:+.2f}%)")
print(f"  Gross Profit:        ${data['gross_profit']:+,.2f}")
print(f"  Gross Loss:         -${data['gross_loss']:,.2f}")
print(f"  Profit Factor:       {data['profit_factor']:.2f}")
print(f"  Win Rate:            {data['win_rate']*100:.1f}%  ({len(winners)}W / {len(losers)}L)")
print(f"  Sharpe Ratio:        {data['sharpe_ratio']:.2f}")
print(f"  Max Drawdown:        {data['max_drawdown_pct']:.2f}%")
print(f"  Avg Hold:            {data['avg_hold_days']:.1f} days")
avg_win_pct = np.mean([t['pnl_pct'] for t in winners])
avg_loss_pct = np.mean([t['pnl_pct'] for t in losers])
print(f"  Avg Win:             ${data['avg_win']:+,.2f}  ({avg_win_pct:+.1f}% option return)")
print(f"  Avg Loss:            ${data['avg_loss']:+,.2f}  ({avg_loss_pct:+.1f}% option return)")

# ── Per Trade ────────────────────────────────────────────────────────────────
print("\n" + "=" * 105)
print(" PER-TRADE DETAIL")
print("=" * 105)
header = (
    f"  {'#':>3s}  {'W/L':>3s}  {'Symbol':>6s}  {'Entry':>10s}  {'Exit':>10s}  {'Days':>4s}  "
    f"{'Exit Reason':>15s}  {'Opt Ret%':>9s}  {'$ P&L':>11s}  {'$ Cumul':>11s}  {'Conf':>5s}  {'Delta':>5s}"
)
print(header)
print("  " + "-" * 101)

cumulative = 0.0
for i, t in enumerate(trades, 1):
    win = " W" if t["pnl"] > 0 else " L"
    cumulative += t["pnl"]
    print(
        f"  {i:3d}  {win:>3s}  {t['symbol']:>6s}  {t['entry_date']:>10s}  {t['exit_date']:>10s}  {t['days_held']:>4d}  "
        f"{t['exit_reason']:>15s}  {t['pnl_pct']:>+8.1f}%  ${t['pnl']:>+10,.2f}  ${cumulative:>+10,.2f}  "
        f"{t['avg_confidence']:.3f}  {t['delta_at_entry']:.3f}"
    )

# ── Exit Reason ──────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print(" EXIT REASON BREAKDOWN")
print("=" * 80)
by_exit = defaultdict(list)
for t in trades:
    by_exit[t["exit_reason"]].append(t)
for reason in ["option_target", "time_exit", "option_stop"]:
    group = by_exit.get(reason, [])
    if not group:
        continue
    w = sum(1 for t in group if t["pnl"] > 0)
    total_pnl = sum(t["pnl"] for t in group)
    avg_opt = np.mean([t["pnl_pct"] for t in group])
    avg_dollar = np.mean([t["pnl"] for t in group])
    wr = w / len(group) * 100
    print(
        f"  {reason:18s}: {len(group):2d} trades  WR={wr:5.1f}%  "
        f"avg ret={avg_opt:+6.1f}%  avg $={avg_dollar:+,.0f}  total ${total_pnl:+,.2f}"
    )

# ── Monthly ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print(" MONTHLY P&L")
print("=" * 70)
monthly = data.get("monthly_pnl", {})
running = 0.0
for month, pnl in sorted(monthly.items()):
    running += pnl
    bar_len = max(1, int(abs(pnl) / 1500))
    bar_char = "█" if pnl > 0 else "░"
    bar = bar_char * bar_len
    print(f"  {month}:  ${pnl:>+10,.2f}  (cumul: ${running:>+10,.2f})  {bar}")

# ── Version Comparison ───────────────────────────────────────────────────────
print("\n" + "=" * 80)
print(" v1 → v2 → v3 EVOLUTION")
print("=" * 80)

rows = [
    ("Trades",        "348",      "263",      str(data["total_trades"])),
    ("Win Rate",      "49.7%",    "46.4%",    f"{data['win_rate']*100:.1f}%"),
    ("Net P&L",       "+$397,159", "+$186,207", f"+${data['total_pnl']:,.0f}"),
    ("Sharpe",        "1.44",     "1.23",     f"{data['sharpe_ratio']:.2f}"),
    ("Max Drawdown",  "13.3%",    "43.4%",    f"{data['max_drawdown_pct']:.1f}%"),
    ("Profit Factor", "—",        "—",        f"{data['profit_factor']:.2f}"),
    ("Avg Hold",      "11.7d",    "6.6d",     f"{data['avg_hold_days']:.1f}d"),
    ("Avg Win",       "—",        "—",        f"+${data['avg_win']:,.0f}"),
    ("Avg Loss",      "—",        "—",        f"-${abs(data['avg_loss']):,.0f}"),
]

print(f"  {'Metric':<22s} {'v1':>14s} {'v2':>14s} {'v3':>14s}")
print(f"  {'-'*22}  {'-'*14}  {'-'*14}  {'-'*14}")
for label, v1, v2, v3 in rows:
    print(f"  {label:<22s} {v1:>14s} {v2:>14s} {v3:>14s}")
