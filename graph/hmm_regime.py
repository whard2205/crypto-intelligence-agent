from __future__ import annotations
import logging
import math

logger = logging.getLogger(__name__)

_REGIME_LABELS = ("bear_trending", "ranging", "bull_trending")


def detect_hmm_regime(ohlcv: list[dict], n_states: int = 3) -> dict | None:
    if len(ohlcv) < 30:
        logger.warning(
            "HMM regime detection requires >= 30 candles, got %d", len(ohlcv)
        )
        return None

    try:
        from hmmlearn.hmm import GaussianHMM
        import numpy as np
    except ImportError:
        logger.warning("hmmlearn not installed — market regime detection disabled")
        return None

    try:
        closes = [float(c["close"]) for c in ohlcv]
        log_returns = [
            math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
        ]

        volatility: list[float] = []
        for i in range(len(log_returns)):
            window = log_returns[max(0, i - 4): i + 1]
            mean_w = sum(window) / len(window)
            var_w = sum((x - mean_w) ** 2 for x in window) / len(window)
            volatility.append(math.sqrt(var_w))

        X = np.array([[r, v] for r, v in zip(log_returns, volatility)])

        model = GaussianHMM(
            n_components=n_states,
            covariance_type="diag",
            n_iter=100,
            random_state=42,
        )
        model.fit(X)
        states = model.predict(X)

        state_sums: dict[int, list[float]] = {i: [] for i in range(n_states)}
        for state, ret in zip(states.tolist(), log_returns):
            state_sums[int(state)].append(ret)

        state_means = {
            s: (sum(vs) / len(vs) if vs else 0.0)
            for s, vs in state_sums.items()
        }

        sorted_states = sorted(state_means, key=lambda s: state_means[s])
        label_map = {
            state: _REGIME_LABELS[rank]
            for rank, state in enumerate(sorted_states)
        }

        return {
            "regime":   label_map[int(states[-1])],
            "n_states": n_states,
            "source":   "hmm",
        }

    except Exception as exc:
        logger.warning("HMM regime detection failed: %s", exc)
        return None
