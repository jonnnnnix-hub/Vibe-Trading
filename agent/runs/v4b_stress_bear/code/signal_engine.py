"""v4b Stress Test (Bear) — delegates to production v4b_crypto engine.

This stress test uses identical engine code as v4b_crypto but is
backtested against 2018 bear market dates. The stress scenario is
a backtest configuration, not a separate engine.
"""

import sys
from pathlib import Path

_v4b_dir = str(Path(__file__).resolve().parent.parent.parent / "v4b_crypto" / "code")
if _v4b_dir not in sys.path:
    sys.path.insert(0, _v4b_dir)

from signal_engine import SignalEngine  # noqa: E402

__all__ = ["SignalEngine"]
