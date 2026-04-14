"""v3 Multi-asset — delegates to universal momentum engine.

The universal engine handles multi-asset portfolios by grouping
tickers by asset class and ranking within each group independently.
"""

import sys
from pathlib import Path

_runs_dir = str(Path(__file__).resolve().parent.parent.parent)
if _runs_dir not in sys.path:
    sys.path.insert(0, _runs_dir)

from v3_signal_universal import SignalEngine  # noqa: E402

__all__ = ["SignalEngine"]
