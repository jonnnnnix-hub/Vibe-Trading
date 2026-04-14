"""v3 Hong Kong — delegates to universal momentum engine.

The universal engine auto-detects HK tickers (ending in .HK)
and applies equity parameters (252-day momentum, 21-day skip).
"""

import sys
from pathlib import Path

_runs_dir = str(Path(__file__).resolve().parent.parent.parent)
if _runs_dir not in sys.path:
    sys.path.insert(0, _runs_dir)

from v3_signal_universal import SignalEngine  # noqa: E402

__all__ = ["SignalEngine"]
