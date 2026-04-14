"""v3 Expanded — delegates to universal momentum engine.

All v3 variants (expanded, crypto, hk, multi) share identical 12-1 month
momentum logic. The universal engine handles asset-class detection
automatically. This file exists for backward compatibility with the
backtest runner.
"""

import sys
from pathlib import Path

# Add runs/ to path so we can import the universal engine
_runs_dir = str(Path(__file__).resolve().parent.parent.parent)
if _runs_dir not in sys.path:
    sys.path.insert(0, _runs_dir)

from v3_signal_universal import SignalEngine  # noqa: E402

__all__ = ["SignalEngine"]
