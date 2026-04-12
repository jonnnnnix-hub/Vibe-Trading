"""Backfill the strategy store from existing run artifacts.

Scans all run directories under agent/runs/ and populates the SQLite
database with their configs, metrics, validation results, and strategy
fingerprints.

Usage:
    python -m backtest.backfill_store
"""

import json
import sys
from pathlib import Path

from backtest.strategy_store import StrategyStore


def backfill(runs_dir: Path) -> None:
    """Backfill strategy store from existing runs."""
    store = StrategyStore()

    run_dirs = sorted(
        d for d in runs_dir.iterdir()
        if d.is_dir() and (d / "config.json").exists()
    )

    print(f"Found {len(run_dirs)} runs to backfill")

    for run_dir in run_dirs:
        run_id = run_dir.name

        # Load config
        config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))

        # Load metrics
        metrics_path = run_dir / "artifacts" / "metrics.csv"
        metrics = {}
        if metrics_path.exists():
            import csv
            with open(metrics_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    metrics = {k: _safe_float(v) for k, v in row.items()}

        # Load validation
        val_path = run_dir / "artifacts" / "validation.json"
        if val_path.exists():
            val_text = val_path.read_text(encoding="utf-8").strip()
            if val_text and val_text != "{}":
                metrics["validation"] = json.loads(val_text)

        if not metrics:
            print(f"  {run_id}: SKIP (no metrics)")
            continue

        result = store.record_run(run_dir, config, metrics)
        status = "OK" if result else "FAIL"
        sharpe = metrics.get("sharpe", "?")
        print(f"  {run_id}: {status} (sharpe={sharpe})")

    # Summary
    summary = store.summary()
    print(f"\nStrategy store: {summary['total_runs']} runs")
    for m in summary.get("by_market", []):
        print(f"  {m['market_type']}: {m['n']} runs, "
              f"avg_sharpe={m['avg_sharpe']}, best_sharpe={m['best_sharpe']}")

    store.close()


def _safe_float(v: str) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


if __name__ == "__main__":
    runs_dir = Path(__file__).resolve().parent.parent / "runs"
    backfill(runs_dir)
