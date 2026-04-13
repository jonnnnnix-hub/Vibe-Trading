"""Cash-aware inverse-volatility optimizer.

Like equal_volatility but does NOT normalize weights to sum to 1.0.
Instead, it scales each active position by its inverse-volatility share
multiplied by a target exposure cap.  When the signal engine selects
fewer than the full universe (e.g. 8 / 55 stocks), the portfolio
naturally holds cash — enabling the MC return-randomization test to
distinguish signal timing from random.

Config keys (via optimizer_params):
    target_exposure: float — max gross exposure (default 0.55 = 55%)
    lookback: int — rolling vol window (default 60)
"""

from typing import Any, Dict, List

import numpy as np
import pandas as pd

from backtest.optimizers.base import BaseOptimizer


class CashAwareOptimizer(BaseOptimizer):
    """Inverse-volatility weights scaled to a target exposure cap."""

    def __init__(self, lookback: int = 60, target_exposure: float = 0.55, **kwargs: Any) -> None:
        super().__init__(lookback=lookback, **kwargs)
        self.target_exposure = target_exposure

    def _build_context(
        self, window: pd.DataFrame, active: List[str]
    ) -> "Dict[str, Any] | None":
        vols = window.std()
        if vols.isna().any() or (vols < 1e-12).any():
            return None
        return {"vols": vols, "n_active": len(active)}

    def _calc_weights(self, ctx: Dict[str, Any]) -> np.ndarray:
        """Inverse-volatility weights scaled to target exposure.

        Instead of normalizing to sum=1.0, we normalize to
        sum=target_exposure so the portfolio holds cash.
        """
        inv_vol = 1.0 / ctx["vols"]
        # Normalize to target_exposure instead of 1.0
        raw_weights = (inv_vol / inv_vol.sum()).values * self.target_exposure
        return raw_weights


def optimize(
    ret: pd.DataFrame,
    pos: pd.DataFrame,
    dates: pd.DatetimeIndex,
    lookback: int = 60,
    target_exposure: float = 0.55,
) -> pd.DataFrame:
    """Module-level entry: cash-aware inverse-volatility-adjusted positions.

    The returned position matrix will have row sums <= target_exposure,
    preserving cash allocation.  The ``skip_pos_normalization`` attribute
    is set on the returned DataFrame so that ``_align()`` in base.py
    knows NOT to re-normalize to sum=1.0.
    """
    result = CashAwareOptimizer(
        lookback=lookback, target_exposure=target_exposure
    ).optimize(ret, pos, dates)
    # Tag the DataFrame so _align knows to skip normalization
    result.attrs["skip_pos_normalization"] = True
    return result
