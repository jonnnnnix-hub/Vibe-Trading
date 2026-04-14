#!/usr/bin/env python3
"""Final stage: combine best elements to maximize WR while keeping trade count."""
import sys, os, json, copy, time
sys.path.insert(0, os.path.dirname(__file__))

from engine import discover_tickers, run_strategy, STRATEGY_CONFIGS

# Best base: tgt15/stop25/d38-44
BEST_BASE = {
    "target_pct":          5.0,
    "trailing_activation": 3.0,
    "trailing_distance":   2.0,
    "hard_stop_pct":       None,
    "option_stop_pct":     25.0,
    "option_target_pct":   15.0,
    "max_hold_days":       5,
    "min_hold_days":       1,
    "delta_min":           0.38,
    "delta_max":           0.44,
    "iv_filter":           True,
    "iv_decline_threshold": -5.0,
    "skip_days":           [],
    "confidence_dead_zone": None,
    "symbol_blacklist":    [],
}

ALL_TICKERS = discover_tickers()
BL = ["HD", "DHR", "BRK_B", "AMGN"]

def test(name, **overrides):
    c = copy.deepcopy(BEST_BASE)
    c.update(overrides)
    saved = copy.deepcopy(STRATEGY_CONFIGS["expert_committee"])
    STRATEGY_CONFIGS["expert_committee"] = c
    try:
        r = run_strategy("expert_committee", ALL_TICKERS)
    finally:
        STRATEGY_CONFIGS["expert_committee"] = saved
    row = {
        "name": name,
        "trades": r.get("total_trades",0),
        "wr": r.get("win_rate",0),
        "pnl": r.get("total_pnl",0),
        "sharpe": r.get("sharpe_ratio",0),
        "pf": r.get("profit_factor",0),
        "dd": r.get("max_drawdown_pct",0),
        "hold": r.get("avg_hold_days",0),
    }
    print(f"  {name:<55} {row['trades']:>4} tr | {row['wr']:>5.1%} WR | ${row['pnl']:>10,.0f} | Sh={row['sharpe']:.2f} PF={row['pf']:.2f} DD={row['dd']:.1f}%")
    sys.stdout.flush()
    return row

results = []
t0 = time.time()

# Winning combos from Stage 2 — now mix and match
print("── FINAL OPTIMIZATION: COMBO MIXES ──\n")

# Winner 1: stop30+hold4 (65.9%, 91 trades)
results.append(test("stop30+hold4", option_stop_pct=30.0, max_hold_days=4))
# Add skip_tue
results.append(test("stop30+hold4+skip_tue", option_stop_pct=30.0, max_hold_days=4, skip_days=[1]))
# Add d40-44
results.append(test("stop30+hold4+d40-44", option_stop_pct=30.0, max_hold_days=4, delta_min=0.40, delta_max=0.44))
# Triple combo
results.append(test("stop30+hold4+skip_tue+d40-44", option_stop_pct=30.0, max_hold_days=4, skip_days=[1], delta_min=0.40, delta_max=0.44))

# Winner 2: skip_tue (65.3%, 72 trades) — add stop30
results.append(test("skip_tue+stop30", skip_days=[1], option_stop_pct=30.0))
results.append(test("skip_tue+stop30+hold4", skip_days=[1], option_stop_pct=30.0, max_hold_days=4))

# Winner 3: d40-44 (64.6%, 65 trades) — add stop30
results.append(test("d40-44+stop30", delta_min=0.40, delta_max=0.44, option_stop_pct=30.0))
results.append(test("d40-44+stop30+hold4", delta_min=0.40, delta_max=0.44, option_stop_pct=30.0, max_hold_days=4))
results.append(test("d40-44+stop30+skip_tue", delta_min=0.40, delta_max=0.44, option_stop_pct=30.0, skip_days=[1]))

# Tgt12 combos (63.7% base)
results.append(test("tgt12+stop30+hold4", option_target_pct=12.0, option_stop_pct=30.0, max_hold_days=4))
results.append(test("tgt12+stop25+hold4", option_target_pct=12.0, option_stop_pct=25.0, max_hold_days=4))
results.append(test("tgt12+stop30+skip_tue", option_target_pct=12.0, option_stop_pct=30.0, skip_days=[1]))
results.append(test("tgt12+stop25+d40-44", option_target_pct=12.0, option_stop_pct=25.0, delta_min=0.40, delta_max=0.44))

# Nuclear combos with everything
results.append(test("tgt12+stop30+hold4+d40-44", option_target_pct=12.0, option_stop_pct=30.0, max_hold_days=4, delta_min=0.40, delta_max=0.44))
results.append(test("tgt12+stop30+hold4+skip_tue", option_target_pct=12.0, option_stop_pct=30.0, max_hold_days=4, skip_days=[1]))
results.append(test("stop30+hold4+dz60-70", option_stop_pct=30.0, max_hold_days=4, confidence_dead_zone=(0.60, 0.70)))

# Wider stop exploration (35%) with hold4
results.append(test("stop35+hold4", option_stop_pct=35.0, max_hold_days=4))
results.append(test("stop35+hold4+d40-44", option_stop_pct=35.0, max_hold_days=4, delta_min=0.40, delta_max=0.44))
results.append(test("stop35+hold3", option_stop_pct=35.0, max_hold_days=3))

# Tighter stops with hold4
results.append(test("stop20+hold4", option_stop_pct=20.0, max_hold_days=4))
results.append(test("tgt12+stop20+hold4", option_target_pct=12.0, option_stop_pct=20.0, max_hold_days=4))

print(f"\nTotal: {time.time()-t0:.0f}s\n")

# Summary
print("="*140)
print(f"{'Config':<57} {'Trades':>6} {'WR':>7} {'PnL':>12} {'Sharpe':>7} {'PF':>6} {'DD%':>7} {'Hold':>5}")
print("-"*140)
for r in sorted(results, key=lambda x: (-x['wr'], -x['trades'])):
    print(f"{r['name']:<57} {r['trades']:>6} {r['wr']:>6.1%} ${r['pnl']:>10,.0f} {r['sharpe']:>7.2f} {r['pf']:>6.2f} {r['dd']:>6.1f}% {r['hold']:>5.1f}")

with open("results/optimization_grid_final.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"\nSaved {len(results)} configs")
