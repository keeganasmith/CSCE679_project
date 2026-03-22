from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

import numpy as np

SmoothingMethod = Literal["none", "ema", "moving_average"]
RegressionMethod = Literal["ols", "theil_sen"]


@dataclass
class TrendOptions:
    smoothing: SmoothingMethod = "ema"
    smoothing_window: int = 5
    ema_alpha: float = 0.35
    regression: RegressionMethod = "theil_sen"
    min_points: int = 6
    bootstrap_samples: int = 300
    change_point_z: float = 2.0


@dataclass
class DegradationCriteria:
    min_negative_slope: float = 0.0
    drawdown_threshold: float = 0.08
    sustained_decline_window: int = 5
    sustained_decline_min_drop: float = 0.02


def _to_array(values: Sequence[Optional[float]]) -> np.ndarray:
    arr = np.asarray([np.nan if v is None else float(v) for v in values], dtype=np.float64)
    return arr


def _interp_nan(values: np.ndarray) -> np.ndarray:
    arr = values.copy()
    if np.all(np.isnan(arr)):
        return arr
    idx = np.arange(len(arr))
    valid = ~np.isnan(arr)
    arr[~valid] = np.interp(idx[~valid], idx[valid], arr[valid])
    return arr


def smooth_values(values: Sequence[Optional[float]], method: SmoothingMethod, window: int = 5, alpha: float = 0.35) -> List[Optional[float]]:
    arr = _to_array(values)
    if len(arr) == 0:
        return []

    if method == "none":
        return [None if np.isnan(v) else float(v) for v in arr]

    interp = _interp_nan(arr)

    if method == "moving_average":
        w = max(1, int(window))
        kernel = np.ones(w) / w
        smoothed = np.convolve(interp, kernel, mode="same")
    elif method == "ema":
        a = float(np.clip(alpha, 0.01, 1.0))
        smoothed = np.empty_like(interp)
        smoothed[0] = interp[0]
        for i in range(1, len(interp)):
            smoothed[i] = a * interp[i] + (1.0 - a) * smoothed[i - 1]
    else:
        raise ValueError(f"Unsupported smoothing method: {method}")

    out = []
    for orig, val in zip(arr, smoothed):
        out.append(None if np.isnan(orig) else float(val))
    return out


def _ols_fit(x: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    slope, intercept = np.polyfit(x, y, 1)
    return float(slope), float(intercept)


def _theil_sen_fit(x: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    n = len(x)
    slopes = []
    for i in range(n - 1):
        dx = x[i + 1 :] - x[i]
        dy = y[i + 1 :] - y[i]
        valid = dx != 0
        if np.any(valid):
            slopes.extend((dy[valid] / dx[valid]).tolist())
    slope = float(np.median(slopes)) if slopes else 0.0
    intercept = float(np.median(y - slope * x))
    return slope, intercept


def fit_trend(values: Sequence[Optional[float]], method: RegressionMethod = "theil_sen", min_points: int = 6, bootstrap_samples: int = 300) -> Dict[str, Any]:
    arr = _to_array(values)
    valid = ~np.isnan(arr)
    if int(np.sum(valid)) < min_points:
        return {"slope": None, "intercept": None, "confidence": None, "n_points": int(np.sum(valid))}

    x = np.arange(len(arr), dtype=np.float64)[valid]
    y = arr[valid]

    fit_fn = _theil_sen_fit if method == "theil_sen" else _ols_fit
    slope, intercept = fit_fn(x, y)

    rng = np.random.default_rng(42)
    boot_slopes: List[float] = []
    n = len(x)
    sample_count = max(50, int(bootstrap_samples))
    for _ in range(sample_count):
        indices = rng.integers(0, n, n)
        xb = x[indices]
        yb = y[indices]
        order = np.argsort(xb)
        xb = xb[order]
        yb = yb[order]
        if np.unique(xb).shape[0] < 2:
            continue
        try:
            bs, _ = fit_fn(xb, yb)
            boot_slopes.append(float(bs))
        except Exception:
            continue

    if boot_slopes:
        lo = float(np.percentile(boot_slopes, 2.5))
        hi = float(np.percentile(boot_slopes, 97.5))
        confidence = float(np.mean((np.asarray(boot_slopes) > 0) == (slope > 0)))
    else:
        lo, hi, confidence = slope, slope, None

    return {
        "slope": slope,
        "intercept": intercept,
        "slope_ci": [lo, hi],
        "confidence": confidence,
        "n_points": int(np.sum(valid)),
    }


def detect_change_points(values: Sequence[Optional[float]], z_threshold: float = 2.0) -> List[int]:
    arr = _to_array(values)
    interp = _interp_nan(arr)
    if len(interp) < 5:
        return []

    diffs = np.diff(interp)
    mean = float(np.mean(diffs))
    std = float(np.std(diffs))
    if std == 0:
        return []

    z = (diffs - mean) / std
    return [int(i + 1) for i, score in enumerate(z) if abs(score) >= z_threshold]


def evaluate_degradation(values: Sequence[Optional[float]], trend: Dict[str, Any], criteria: DegradationCriteria) -> Dict[str, Any]:
    arr = _to_array(values)
    interp = _interp_nan(arr)
    if len(interp) == 0:
        return {
            "is_degrading": False,
            "checks": {"negative_slope": False, "drawdown": False, "sustained_decline": False},
        }

    slope = trend.get("slope")
    negative_slope = bool(slope is not None and slope < -abs(criteria.min_negative_slope))

    running_max = np.maximum.accumulate(interp)
    denom = np.maximum(np.abs(running_max), 1e-9)
    drawdowns = (running_max - interp) / denom
    max_drawdown = float(np.max(drawdowns)) if len(drawdowns) else 0.0
    drawdown_hit = max_drawdown >= criteria.drawdown_threshold

    w = max(2, int(criteria.sustained_decline_window))
    sustained_hit = False
    windows: List[Dict[str, Any]] = []
    for start in range(0, len(interp) - w + 1):
        seg = interp[start : start + w]
        drop = float(seg[0] - seg[-1])
        monotonic = bool(np.all(np.diff(seg) <= 1e-12))
        if monotonic and drop >= criteria.sustained_decline_min_drop:
            sustained_hit = True
            windows.append({"start_index": start, "end_index": start + w - 1, "drop": drop})

    checks = {
        "negative_slope": negative_slope,
        "drawdown": drawdown_hit,
        "sustained_decline": sustained_hit,
    }
    is_degrading = any(checks.values())

    return {
        "is_degrading": is_degrading,
        "checks": checks,
        "max_drawdown": max_drawdown,
        "sustained_decline_windows": windows,
    }


def annotate_series(points: Sequence[Dict[str, Any]], value_key: str, options: Optional[TrendOptions] = None) -> Dict[str, Any]:
    opts = options or TrendOptions()
    raw_values = [p.get(value_key) for p in points]
    smoothed = smooth_values(raw_values, method=opts.smoothing, window=opts.smoothing_window, alpha=opts.ema_alpha)
    trend = fit_trend(smoothed, method=opts.regression, min_points=opts.min_points, bootstrap_samples=opts.bootstrap_samples)
    change_points = detect_change_points(smoothed, z_threshold=opts.change_point_z)

    return {
        "points": [
            {
                **p,
                "smoothed_value": smoothed[idx],
            }
            for idx, p in enumerate(points)
        ],
        "trend": {
            **trend,
            "change_points": change_points,
            "change_point_dates": [points[i]["match_date"] for i in change_points if i < len(points)],
        },
    }
