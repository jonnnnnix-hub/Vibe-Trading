"""v3 Crypto — delegates to universal momentum engine.

The universal engine auto-detects crypto tickers (ending in -USDT)
and applies crypto-specific parameters (365-day momentum, 30-day skip).
"""

import sys
from pathlib import Path

_runs_dir = str(Path(__file__).resolve().parent.parent.parent)
if _runs_dir not in sys.path:
    sys.path.insert(0, _runs_dir)

from v3_signal_universal import SignalEngine  # noqa: E402

__all__ = ["SignalEngine"]
