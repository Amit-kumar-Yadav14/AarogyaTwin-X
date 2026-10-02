"""Small serializable model wrappers used by the Day-1 pipeline.

The wrappers make edge cases explicit: a split can contain one class or no valid
rows, and metrics must then use ``None`` rather than NaN.  Classes live in this
module (rather than the ``-m aarogya.pipeline`` entrypoint) so joblib bundles can
be reloaded by a separately imported engine.
"""

from __future__ import annotations

from typing import Any, Iterable
import math

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression


def _as_2d(values: Any, width: int | None = None) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim == 1:
        array = array.reshape(1, -1)
    if array.ndim != 2:
        raise ValueError("feature matrix must be two-dimensional")
    if width is not None and array.shape[1] != width:
        raise ValueError(f"expected {width} features, received {array.shape[1]}")
    return array


class NumericPreprocessor:
    """Train-only median imputation, missing indicators, and standardization."""

    def __init__(self) -> None:
        self.n_features_in_: int | None = None
        self.medians_: np.ndarray | None = None
        self.means_: np.ndarray | None = None
        self.scales_: np.ndarray | None = None

    def fit(self, values: Any) -> "NumericPreprocessor":
        array = _as_2d(values)
        self.n_features_in_ = int(array.shape[1])
        medians = np.zeros(self.n_features_in_, dtype=float)
        for column in range(self.n_features_in_):
            finite = array[np.isfinite(array[:, column]), column]
            medians[column] = float(np.median(finite)) if finite.size else 0.0
        imputed = np.where(np.isfinite(array), array, medians[None, :])
        means = np.mean(imputed, axis=0)
        scales = np.std(imputed, axis=0)
        scales = np.where(np.isfinite(scales) & (scales > 1e-8), scales, 1.0)
        self.medians_ = medians
        self.means_ = means
        self.scales_ = scales
        return self

    @property
    def output_width(self) -> int:
        if self.n_features_in_ is None:
            return 0
        return self.n_features_in_ * 2

    def transform(self, values: Any) -> np.ndarray:
        if self.n_features_in_ is None or self.medians_ is None or self.means_ is None or self.scales_ is None:
            raise RuntimeError("preprocessor has not been fitted")
        array = _as_2d(values, self.n_features_in_)
        missing = (~np.isfinite(array)).astype(float)
        imputed = np.where(np.isfinite(array), array, self.medians_[None, :])
        standardized = (imputed - self.means_[None, :]) / self.scales_[None, :]
        result = np.concatenate([standardized, missing], axis=1)
        # Guard against a malformed caller introducing an infinity after the
        # imputation operation; model inputs are always finite by contract.
        return np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)

    def fit_transform(self, values: Any) -> np.ndarray:
        return self.fit(values).transform(values)


class ProbabilityEstimator:
    """Logistic probability estimator with deterministic one-class fallback."""

    def __init__(self, random_state: int = 2026) -> None:
        self.random_state = int(random_state)
        self.model: LogisticRegression | None = None
        self.constant_: float | None = None
        self.available_: bool = False
        self.n_train_: int = 0
        self.classes_: tuple[int, ...] = ()

    def fit(self, values: Any, target: Any) -> "ProbabilityEstimator":
        array = _as_2d(values)
        y = np.asarray(target, dtype=int).reshape(-1)
        if array.shape[0] != y.size:
            raise ValueError("feature and target row counts differ")
        self.n_train_ = int(y.size)
        if y.size == 0:
            self.available_ = False
            self.constant_ = None
            self.classes_ = ()
            return self
        unique = np.unique(y)
        self.classes_ = tuple(int(value) for value in unique.tolist())
        if unique.size < 2:
            self.constant_ = float(np.clip(np.mean(y), 0.0, 1.0))
            self.available_ = True
            self.model = None
            return self
        try:
            model = LogisticRegression(
                max_iter=400,
                class_weight="balanced",
                solver="lbfgs",
                random_state=self.random_state,
            )
            model.fit(array, y)
            self.model = model
            self.constant_ = None
            self.available_ = True
        except (ValueError, ArithmeticError, RuntimeError):
            self.model = None
            self.constant_ = float(np.clip(np.mean(y), 0.0, 1.0))
            self.available_ = True
        return self

    def predict_probability(self, values: Any) -> np.ndarray:
        array = _as_2d(values)
        if not self.available_:
            return np.full(array.shape[0], np.nan, dtype=float)
        if self.model is None:
            return np.full(array.shape[0], float(self.constant_ or 0.0), dtype=float)
        try:
            probabilities = self.model.predict_proba(array)
            # LogisticRegression orders columns according to classes_; locate the
            # positive class instead of assuming it is column one.
            classes = np.asarray(self.model.classes_)
            positive = np.flatnonzero(classes == 1)
            index = int(positive[0]) if positive.size else probabilities.shape[1] - 1
            result = probabilities[:, index]
            return np.clip(np.nan_to_num(result, nan=0.0, posinf=1.0, neginf=0.0), 0.0, 1.0)
        except (ValueError, RuntimeError, AttributeError):
            fallback = float(self.constant_ or 0.0)
            return np.full(array.shape[0], fallback, dtype=float)


class RegressionEstimator:
    """CPU-friendly histogram gradient boosting with a constant fallback."""

    def __init__(self, random_state: int = 2026) -> None:
        self.random_state = int(random_state)
        self.model: HistGradientBoostingRegressor | None = None
        self.constant_: float | None = None
        self.available_: bool = False
        self.n_train_: int = 0

    def fit(self, values: Any, target: Any) -> "RegressionEstimator":
        array = _as_2d(values)
        y = np.asarray(target, dtype=float).reshape(-1)
        if array.shape[0] != y.size:
            raise ValueError("feature and target row counts differ")
        finite = np.isfinite(y)
        array = array[finite]
        y = y[finite]
        self.n_train_ = int(y.size)
        if y.size == 0:
            self.available_ = False
            self.constant_ = None
            self.model = None
            return self
        self.constant_ = float(np.mean(y))
        if y.size < 3 or float(np.std(y)) < 1e-8:
            self.available_ = True
            self.model = None
            return self
        try:
            model = HistGradientBoostingRegressor(
                max_iter=140,
                learning_rate=0.055,
                max_leaf_nodes=15,
                min_samples_leaf=max(8, min(24, y.size // 40 or 1)),
                l2_regularization=1.0,
                random_state=self.random_state,
            )
            model.fit(array, y)
            self.model = model
            self.available_ = True
        except (ValueError, ArithmeticError, RuntimeError):
            self.model = None
            self.available_ = True
        return self

    def predict_value(self, values: Any) -> np.ndarray:
        array = _as_2d(values)
        if not self.available_:
            return np.full(array.shape[0], np.nan, dtype=float)
        if self.model is None:
            return np.full(array.shape[0], float(self.constant_ or 0.0), dtype=float)
        try:
            result = np.asarray(self.model.predict(array), dtype=float)
            return np.nan_to_num(result, nan=float(self.constant_ or 0.0), posinf=400.0, neginf=40.0)
        except (ValueError, RuntimeError, AttributeError):
            return np.full(array.shape[0], float(self.constant_ or 0.0), dtype=float)


def finite_or_none(value: Any) -> float | int | str | bool | None:
    """Convert scalar NumPy values and non-finite floats to JSON-safe values."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    return value


def json_safe(value: Any) -> Any:
    """Recursively sanitize artifact/response payloads for strict JSON."""

    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return [json_safe(item) for item in value.tolist()]
    return finite_or_none(value)


def safe_mean(values: Iterable[float]) -> float | None:
    array = np.asarray(list(values), dtype=float)
    finite = array[np.isfinite(array)]
    return None if finite.size == 0 else float(np.mean(finite))


def safe_quantile(values: Iterable[float], quantile: float) -> float | None:
    array = np.asarray(list(values), dtype=float)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return None
    return float(np.quantile(finite, float(np.clip(quantile, 0.0, 1.0))))


__all__ = [
    "NumericPreprocessor",
    "ProbabilityEstimator",
    "RegressionEstimator",
    "finite_or_none",
    "json_safe",
    "safe_mean",
    "safe_quantile",
]
