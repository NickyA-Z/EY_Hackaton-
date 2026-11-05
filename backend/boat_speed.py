"""Short-horizon ILCA 7 speed forecasts from SailSync GPS tracks.

The model deliberately uses only information available at prediction time:
recent speed, acceleration, heading and turn rate.  It is trained on the other
boats in the fleet so the selected boat is an honest, unseen example.
"""

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from backend import race_analysis

KNOTS_PER_MPS = 1.943844
RESAMPLE_SECONDS = 10
MAX_INTERPOLATION_GAP_SECONDS = 30
MAX_PLAUSIBLE_SPEED_KT = 15.0
FEATURES = (
    "speed_kt",
    "speed_30s_kt",
    "speed_60s_kt",
    "acceleration_kt_s",
    "turn_rate_deg_s",
    "heading_sin",
    "heading_cos",
)

# All three areas can use the same class model. Only Outer Harbor currently
# has labelled SailSync telemetry, so the other areas are marked as transfers.
FORECAST_LOCATIONS = {
    "Belmont Shore": {"lat": 33.748, "lon": -118.140, "telemetry": False},
    "LA Outer Harbor": {"lat": 33.712, "lon": -118.272, "telemetry": True},
    "Outside Breakwater": {"lat": 33.695, "lon": -118.235, "telemetry": False},
}


@dataclass(frozen=True)
class SpeedModel:
    """Small ridge-regression model with its validation diagnostics."""

    coefficients: np.ndarray
    feature_mean: np.ndarray
    feature_scale: np.ndarray
    validation_mae_kt: float
    residual_low_kt: float
    residual_high_kt: float
    training_rows: int
    boats: int

    def predict(self, frame):
        values = frame.loc[:, FEATURES].to_numpy(dtype=float)
        scaled = (values - self.feature_mean) / self.feature_scale
        design = np.column_stack([np.ones(len(values)), scaled])
        return np.clip(design @ self.coefficients, 0.0, MAX_PLAUSIBLE_SPEED_KT)


def _bearing_degrees(lat1, lon1, lat2, lon2):
    """Vectorised initial bearing in degrees, clockwise from north."""
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    delta = np.radians(lon2 - lon1)
    y = np.sin(delta) * np.cos(phi2)
    x = np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(delta)
    return (np.degrees(np.arctan2(y, x)) + 360.0) % 360.0


def _distance_metres(lat1, lon1, lat2, lon2):
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = phi2 - phi1
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return 6_371_000.0 * 2.0 * np.arctan2(np.sqrt(a), np.sqrt(np.maximum(0.0, 1.0 - a)))


def _signed_angle_change(values):
    return (values.diff() + 180.0) % 360.0 - 180.0


def prepare_track(track, horizon_seconds=30):
    """Turn an irregular GPS track into leakage-free model rows."""
    if horizon_seconds < RESAMPLE_SECONDS or horizon_seconds % RESAMPLE_SECONDS:
        raise ValueError(f"horizon_seconds must be a positive multiple of {RESAMPLE_SECONDS}")

    raw = track[["time_epoch", "lat", "lng"]].dropna().sort_values("time_epoch")
    raw = raw.drop_duplicates("time_epoch")
    if len(raw) < 10:
        return pd.DataFrame()

    times = raw["time_epoch"].to_numpy(dtype=float)
    grid = np.arange(
        math.ceil(times[0] / RESAMPLE_SECONDS) * RESAMPLE_SECONDS,
        math.floor(times[-1] / RESAMPLE_SECONDS) * RESAMPLE_SECONDS + 1,
        RESAMPLE_SECONDS,
    )
    if len(grid) < 10:
        return pd.DataFrame()

    right = np.searchsorted(times, grid, side="left")
    left = np.maximum(right - 1, 0)
    right = np.minimum(right, len(times) - 1)
    gap = times[right] - times[left]
    valid_position = gap <= MAX_INTERPOLATION_GAP_SECONDS

    frame = pd.DataFrame({
        "time_epoch": grid,
        "lat": np.interp(grid, times, raw["lat"].to_numpy(dtype=float)),
        "lng": np.interp(grid, times, raw["lng"].to_numpy(dtype=float)),
        "valid_position": valid_position,
    })
    previous_valid = frame["valid_position"].shift(fill_value=False).astype(bool)
    distance = _distance_metres(
        frame["lat"].shift(), frame["lng"].shift(), frame["lat"], frame["lng"]
    )
    frame["speed_kt"] = distance / RESAMPLE_SECONDS * KNOTS_PER_MPS
    frame.loc[~(frame["valid_position"] & previous_valid), "speed_kt"] = np.nan
    frame.loc[frame["speed_kt"] > MAX_PLAUSIBLE_SPEED_KT, "speed_kt"] = np.nan

    frame["heading_deg"] = _bearing_degrees(
        frame["lat"].shift(), frame["lng"].shift(), frame["lat"], frame["lng"]
    )
    frame.loc[frame["speed_kt"] < 0.3, "heading_deg"] = np.nan
    # Three samples reduce consumer-GPS noise without looking into the future.
    frame["speed_kt"] = frame["speed_kt"].rolling(3, min_periods=2).median()
    frame["speed_30s_kt"] = frame["speed_kt"].rolling(3, min_periods=2).mean()
    frame["speed_60s_kt"] = frame["speed_kt"].rolling(6, min_periods=3).mean()
    frame["acceleration_kt_s"] = frame["speed_30s_kt"].diff() / RESAMPLE_SECONDS
    frame["turn_rate_deg_s"] = _signed_angle_change(frame["heading_deg"]).abs() / RESAMPLE_SECONDS
    radians = np.radians(frame["heading_deg"])
    frame["heading_sin"] = np.sin(radians)
    frame["heading_cos"] = np.cos(radians)

    steps = horizon_seconds // RESAMPLE_SECONDS
    frame["target_speed_kt"] = frame["speed_kt"].shift(-steps)
    frame["actual_future_time"] = frame["time_epoch"].shift(-steps)
    return frame.dropna(subset=[*FEATURES]).reset_index(drop=True)


def build_dataset(horizon_seconds=30):
    """Return feature rows for all available ILCA 7 boats."""
    tracks, winners = race_analysis.load_tracks()
    frames = []
    for name, track in tracks.items():
        frame = prepare_track(track, horizon_seconds)
        if frame.empty:
            continue
        frame["boat"] = name
        frame["winner"] = name in winners
        frames.append(frame)
    if not frames:
        raise ValueError("No usable SailSync tracks were found")
    return pd.concat(frames, ignore_index=True)


def _fit_ridge(frame, ridge=1.0):
    values = frame.loc[:, FEATURES].to_numpy(dtype=float)
    target = frame["target_speed_kt"].to_numpy(dtype=float)
    mean = values.mean(axis=0)
    scale = values.std(axis=0)
    scale[scale < 1e-9] = 1.0
    design = np.column_stack([np.ones(len(values)), (values - mean) / scale])
    penalty = np.eye(design.shape[1]) * ridge
    penalty[0, 0] = 0.0
    coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ target)
    return coefficients, mean, scale


def train_model(dataset, excluded_boat=None):
    """Train on other boats and estimate error with a chronological split."""
    usable = dataset.dropna(subset=["target_speed_kt"]).copy()
    if excluded_boat is not None:
        usable = usable[usable["boat"] != excluded_boat]
    if len(usable) < 100:
        raise ValueError("Not enough GPS rows to train the speed model")

    usable["fraction"] = usable.groupby("boat").cumcount() / usable.groupby("boat")["boat"].transform("size")
    train = usable[usable["fraction"] < 0.8]
    validation = usable[usable["fraction"] >= 0.8]
    validation_coefficients, validation_mean, validation_scale = _fit_ridge(train)
    validation_model = SpeedModel(
        validation_coefficients, validation_mean, validation_scale, 0, 0, 0, len(train), train["boat"].nunique()
    )
    residuals = validation["target_speed_kt"].to_numpy() - validation_model.predict(validation)
    coefficients, mean, scale = _fit_ridge(usable)
    return SpeedModel(
        coefficients=coefficients,
        feature_mean=mean,
        feature_scale=scale,
        validation_mae_kt=float(np.mean(np.abs(residuals))),
        residual_low_kt=float(np.quantile(residuals, 0.1)),
        residual_high_kt=float(np.quantile(residuals, 0.9)),
        training_rows=len(usable),
        boats=usable["boat"].nunique(),
    )


def predict_row(model, row):
    """Predict one row and return a central estimate plus an 80% error band."""
    estimate = float(model.predict(pd.DataFrame([row]))[0])
    return {
        "predicted_speed_kt": estimate,
        "low_speed_kt": max(0.0, estimate + model.residual_low_kt),
        "high_speed_kt": min(MAX_PLAUSIBLE_SPEED_KT, estimate + model.residual_high_kt),
    }
