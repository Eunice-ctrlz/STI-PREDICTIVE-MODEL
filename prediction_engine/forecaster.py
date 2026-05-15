"""
STI Predictive Model — ML Pipeline (L3)
forecaster.py

Outbreak Pattern Predictor: LSTM (PyTorch) + Facebook Prophet.
- Prophet handles seasonal decomposition and calendar effects
- LSTM captures non-linear temporal dependencies
- Outputs are ensemble-averaged with uncertainty quantification
- Produces 30/60/90-day incidence forecasts per county (§4.1.2)

Target metric: MAPE ≤ 15%
Training window: rolling 5-year, retrained quarterly
"""

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import mlflow
import mlflow.pytorch
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from prophet import Prophet
from sklearn.preprocessing import MinMaxScaler
from torch.utils.data import DataLoader, Dataset

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FORECAST_HORIZONS = [30, 60, 90]   # days
MAPE_THRESHOLD = 15.0               # % — deployment gate (§4.1.2)
SEQUENCE_LENGTH = 52                # 52 weeks of lookback for LSTM
STI_TYPES = ["hiv", "chlamydia", "syphilis", "gonorrhoea", "hpv", "hsv2"]

DEFAULT_LSTM_PARAMS = {
    "hidden_size": 128,
    "num_layers": 2,
    "dropout": 0.2,
    "learning_rate": 1e-3,
    "epochs": 100,
    "batch_size": 32,
    "early_stopping_patience": 10,
}

DEFAULT_PROPHET_PARAMS = {
    "seasonality_mode": "multiplicative",
    "yearly_seasonality": True,
    "weekly_seasonality": False,
    "daily_seasonality": False,
    "changepoint_prior_scale": 0.05,
    "seasonality_prior_scale": 10.0,
}


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class TimeSeriesDataset(Dataset):
    """
    Sliding window dataset for LSTM training.
    Input: sequences of (sequence_length, n_features)
    Target: next-step incidence rate
    """

    def __init__(
        self,
        data: np.ndarray,
        sequence_length: int = SEQUENCE_LENGTH,
    ):
        self.X, self.y = [], []
        for i in range(len(data) - sequence_length):
            self.X.append(data[i : i + sequence_length])
            self.y.append(data[i + sequence_length, 0])  # incidence rate target

        self.X = torch.tensor(np.array(self.X), dtype=torch.float32)
        self.y = torch.tensor(np.array(self.y), dtype=torch.float32)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


# ---------------------------------------------------------------------------
# LSTM Model
# ---------------------------------------------------------------------------

class LSTMForecaster(nn.Module):
    """
    Stacked LSTM with dropout for incidence rate forecasting.
    Input shape: (batch, sequence_length, n_features)
    Output shape: (batch, 1) — predicted incidence rate
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int = 128,
        num_layers: int = 2,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0.0,
            batch_first=True,
        )
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        out = self.dropout(out[:, -1, :])   # Last timestep
        return self.fc(out).squeeze(-1)


# ---------------------------------------------------------------------------
# Feature Engineering for Time Series
# ---------------------------------------------------------------------------

def build_timeseries_dataframe(records: List[Dict]) -> pd.DataFrame:
    """
    Aggregate monthly incidence records into a panel DataFrame.

    Expected record fields:
      - date: ISO date string (first of month)
      - county: str
      - sti_type: str
      - incidence_rate: float (cases per 100k)
      - population_density: float (optional)
      - healthcare_access_index: float (optional, 0-1)

    Returns: DataFrame with columns [ds, county, sti_type, y, density, access]
    sorted by county, sti_type, ds.
    """
    rows = []
    for rec in records:
        rows.append({
            "ds": pd.to_datetime(rec["date"]),
            "county": rec.get("county", "national"),
            "sti_type": rec.get("sti_type", "all"),
            "y": float(rec.get("incidence_rate", 0.0)),
            "density": float(rec.get("population_density", 0.0)),
            "access": float(rec.get("healthcare_access_index", 0.5)),
        })
    df = pd.DataFrame(rows)
    df = df.sort_values(["county", "sti_type", "ds"]).reset_index(drop=True)
    return df


def add_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add seasonal indicators per §4.2."""
    df = df.copy()
    df["month"] = df["ds"].dt.month
    df["quarter"] = df["ds"].dt.quarter
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    df["year"] = df["ds"].dt.year
    df["yoy_delta"] = df.groupby(["county", "sti_type"])["y"].pct_change(12)
    df["yoy_delta"] = df["yoy_delta"].fillna(0.0)
    return df


# ---------------------------------------------------------------------------
# Pattern Predictor Service
# ---------------------------------------------------------------------------

class OutbreakPatternPredictor:
    """
    Ensemble forecaster: LSTM + Prophet.
    Trains per (county, sti_type) combination.
    Final forecast is a weighted average:  60% LSTM + 40% Prophet.
    """

    LSTM_WEIGHT = 0.6
    PROPHET_WEIGHT = 0.4

    def __init__(
        self,
        lstm_params: Optional[Dict] = None,
        prophet_params: Optional[Dict] = None,
        mlflow_experiment_id: Optional[str] = None,
        sequence_length: int = SEQUENCE_LENGTH,
    ):
        self.lstm_params = {**DEFAULT_LSTM_PARAMS, **(lstm_params or {})}
        self.prophet_params = {**DEFAULT_PROPHET_PARAMS, **(prophet_params or {})}
        self.mlflow_experiment_id = mlflow_experiment_id
        self.sequence_length = sequence_length

        # Fitted models keyed by (county, sti_type)
        self.lstm_models: Dict[Tuple[str, str], LSTMForecaster] = {}
        self.prophet_models: Dict[Tuple[str, str], Prophet] = {}
        self.scalers: Dict[Tuple[str, str], MinMaxScaler] = {}

        self.mlflow_run_id: Optional[str] = None
        self.mape_results: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(
        self,
        records: List[Dict],
        run_name: Optional[str] = None,
    ) -> Dict:
        """
        Train forecasters for all (county, sti_type) combinations in records.
        Uses walk-forward cross-validation for evaluation.
        Returns metrics dict with per-combination and mean MAPE.
        """
        df = build_timeseries_dataframe(records)
        df = add_temporal_features(df)

        if self.mlflow_experiment_id:
            mlflow.set_experiment(experiment_id=self.mlflow_experiment_id)

        all_mapes = []

        with mlflow.start_run(run_name=run_name or "outbreak_pattern_predictor") as run:
            self.mlflow_run_id = run.info.run_id
            mlflow.log_params({
                **{f"lstm_{k}": v for k, v in self.lstm_params.items()},
                **{f"prophet_{k}": v for k, v in self.prophet_params.items()},
                "sequence_length": self.sequence_length,
                "training_series_count": df.groupby(["county", "sti_type"]).ngroups,
            })

            for (county, sti_type), group in df.groupby(["county", "sti_type"]):
                if len(group) < self.sequence_length + 12:
                    logger.warning(
                        "Insufficient data for %s/%s (%d rows) — skipping",
                        county, sti_type, len(group),
                    )
                    continue

                key = (county, sti_type)
                logger.info("Training %s / %s (%d rows)", county, sti_type, len(group))

                try:
                    mape = self._train_series(group, key)
                    self.mape_results[f"{county}/{sti_type}"] = mape
                    all_mapes.append(mape)
                except Exception as exc:
                    logger.error(
                        "Training failed for %s/%s: %s", county, sti_type, exc
                    )

            mean_mape = float(np.mean(all_mapes)) if all_mapes else 999.0
            passed = mean_mape <= MAPE_THRESHOLD

            mlflow.log_metric("mape_mean", mean_mape)
            mlflow.log_metric("series_trained", len(all_mapes))
            mlflow.log_param("passed_thresholds", passed)
            mlflow.set_tag(
                "threshold_status", "PASS" if passed else "FAIL"
            )

            # Log PyTorch models
            for key, model in self.lstm_models.items():
                county, sti_type = key
                mlflow.pytorch.log_model(
                    model,
                    artifact_path=f"lstm/{county}/{sti_type}",
                )

        return {
            "mape_mean": mean_mape,
            "mape_by_series": self.mape_results,
            "series_trained": len(all_mapes),
            "passed_thresholds": passed,
            "mlflow_run_id": self.mlflow_run_id,
        }

    def _train_series(
        self, group: pd.DataFrame, key: Tuple[str, str]
    ) -> float:
        """Train LSTM + Prophet for a single (county, sti_type) series."""
        feature_cols = ["y", "month_sin", "month_cos", "density", "access", "yoy_delta"]
        feature_data = group[feature_cols].fillna(0.0).values

        scaler = MinMaxScaler()
        scaled = scaler.fit_transform(feature_data)
        self.scalers[key] = scaler

        # Walk-forward split: last 12 months = validation
        train_scaled = scaled[:-12]
        val_scaled = scaled[-12:]

        # --- LSTM ---
        lstm_mape = self._train_lstm(train_scaled, val_scaled, key, feature_data.shape[1])

        # --- Prophet ---
        prophet_mape = self._train_prophet(group, key)

        # Ensemble MAPE
        return self.LSTM_WEIGHT * lstm_mape + self.PROPHET_WEIGHT * prophet_mape

    def _train_lstm(
        self,
        train_scaled: np.ndarray,
        val_scaled: np.ndarray,
        key: Tuple[str, str],
        n_features: int,
    ) -> float:
        dataset = TimeSeriesDataset(train_scaled, self.sequence_length)
        loader = DataLoader(
            dataset,
            batch_size=self.lstm_params["batch_size"],
            shuffle=True,
        )

        model = LSTMForecaster(
            input_size=n_features,
            hidden_size=self.lstm_params["hidden_size"],
            num_layers=self.lstm_params["num_layers"],
            dropout=self.lstm_params["dropout"],
        )
        optimizer = torch.optim.Adam(
            model.parameters(), lr=self.lstm_params["learning_rate"]
        )
        criterion = nn.MSELoss()

        best_val_loss = float("inf")
        patience_counter = 0

        for epoch in range(self.lstm_params["epochs"]):
            model.train()
            for X_batch, y_batch in loader:
                optimizer.zero_grad()
                pred = model(X_batch)
                loss = criterion(pred, y_batch)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()

            # Validation
            model.eval()
            with torch.no_grad():
                val_ds = TimeSeriesDataset(
                    np.vstack([train_scaled[-self.sequence_length:], val_scaled]),
                    self.sequence_length,
                )
                if len(val_ds) > 0:
                    val_X, val_y = val_ds.X, val_ds.y
                    val_pred = model(val_X)
                    val_loss = criterion(val_pred, val_y).item()

                    if val_loss < best_val_loss:
                        best_val_loss = val_loss
                        patience_counter = 0
                    else:
                        patience_counter += 1

                    if patience_counter >= self.lstm_params["early_stopping_patience"]:
                        logger.debug(
                            "Early stopping at epoch %d for %s/%s", epoch, *key
                        )
                        break

        self.lstm_models[key] = model

        # Compute MAPE on validation set
        model.eval()
        with torch.no_grad():
            val_ds = TimeSeriesDataset(
                np.vstack([train_scaled[-self.sequence_length:], val_scaled]),
                self.sequence_length,
            )
            if len(val_ds) == 0:
                return 999.0
            preds_scaled = model(val_ds.X).numpy()
            actuals_scaled = val_ds.y.numpy()

        # Inverse transform (only the first feature = incidence rate)
        dummy = np.zeros((len(preds_scaled), train_scaled.shape[1]))
        dummy[:, 0] = preds_scaled
        preds = self.scalers[key].inverse_transform(dummy)[:, 0]
        dummy[:, 0] = actuals_scaled
        actuals = self.scalers[key].inverse_transform(dummy)[:, 0]

        return float(_mape(actuals, preds))

    def _train_prophet(
        self, group: pd.DataFrame, key: Tuple[str, str]
    ) -> float:
        prophet_df = group[["ds", "y"]].copy()
        train_df = prophet_df.iloc[:-12]
        val_df = prophet_df.iloc[-12:]

        model = Prophet(**self.prophet_params)

        # Add density and access as additional regressors
        if "density" in group.columns:
            model.add_regressor("density")
            train_df = train_df.copy()
            train_df["density"] = group["density"].iloc[:-12].values

        model.fit(train_df)
        self.prophet_models[key] = model

        future = model.make_future_dataframe(periods=12, freq="MS")
        if "density" in group.columns:
            future["density"] = group["density"].values[-1]

        forecast = model.predict(future)
        preds = forecast["yhat"].iloc[-12:].values
        actuals = val_df["y"].values

        return float(_mape(actuals, preds))

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def forecast(
        self,
        county: str,
        sti_type: str,
        history: List[Dict],
        horizons: Optional[List[int]] = None,
    ) -> Dict:
        """
        Generate forecasts for the given county/sti_type combination.
        Returns forecasts at each horizon (30/60/90 days) with 95% CIs.
        """
        horizons = horizons or FORECAST_HORIZONS
        key = (county, sti_type)

        if key not in self.lstm_models or key not in self.prophet_models:
            raise ValueError(
                f"No trained model found for {county}/{sti_type}. "
                "Run train() first or load a saved model."
            )

        df = build_timeseries_dataframe(history)
        df = add_temporal_features(df)
        df = df[(df["county"] == county) & (df["sti_type"] == sti_type)]

        results = {}
        for horizon in horizons:
            lstm_forecast = self._forecast_lstm(df, key, horizon)
            prophet_forecast = self._forecast_prophet(df, key, horizon)

            # Ensemble: weighted average of point forecasts
            ensemble_mean = (
                self.LSTM_WEIGHT * lstm_forecast["mean"]
                + self.PROPHET_WEIGHT * prophet_forecast["mean"]
            )
            ensemble_lower = (
                self.LSTM_WEIGHT * lstm_forecast["lower"]
                + self.PROPHET_WEIGHT * prophet_forecast["lower"]
            )
            ensemble_upper = (
                self.LSTM_WEIGHT * lstm_forecast["upper"]
                + self.PROPHET_WEIGHT * prophet_forecast["upper"]
            )

            results[f"{horizon}d"] = {
                "forecast_mean": round(float(ensemble_mean), 4),
                "ci_lower_95": round(float(ensemble_lower), 4),
                "ci_upper_95": round(float(ensemble_upper), 4),
                "horizon_days": horizon,
                "lstm_contribution": round(float(lstm_forecast["mean"]), 4),
                "prophet_contribution": round(float(prophet_forecast["mean"]), 4),
            }

        return {
            "county": county,
            "sti_type": sti_type,
            "forecast_date": date.today().isoformat(),
            "forecasts": results,
            "mlflow_run_id": self.mlflow_run_id,
        }

    def _forecast_lstm(
        self, df: pd.DataFrame, key: Tuple[str, str], horizon_days: int
    ) -> Dict:
        """Autoregressive multi-step LSTM forecast."""
        model = self.lstm_models[key]
        scaler = self.scalers[key]

        feature_cols = ["y", "month_sin", "month_cos", "density", "access", "yoy_delta"]
        data = df[feature_cols].fillna(0.0).values
        scaled = scaler.transform(data)

        steps = max(1, horizon_days // 30)
        context = scaled[-self.sequence_length:].copy()

        preds_scaled = []
        model.eval()
        with torch.no_grad():
            for _ in range(steps):
                x = torch.tensor(context[np.newaxis, :, :], dtype=torch.float32)
                pred = model(x).item()
                # Shift context window forward
                new_row = context[-1].copy()
                new_row[0] = pred
                context = np.vstack([context[1:], new_row])
                preds_scaled.append(pred)

        # Inverse transform
        dummy = np.zeros((len(preds_scaled), data.shape[1]))
        dummy[:, 0] = preds_scaled
        preds = scaler.inverse_transform(dummy)[:, 0]
        mean_pred = float(np.mean(preds))
        std_pred = float(np.std(preds)) if len(preds) > 1 else mean_pred * 0.1

        return {
            "mean": mean_pred,
            "lower": max(0.0, mean_pred - 1.96 * std_pred),
            "upper": mean_pred + 1.96 * std_pred,
        }

    def _forecast_prophet(
        self, df: pd.DataFrame, key: Tuple[str, str], horizon_days: int
    ) -> Dict:
        """Prophet multi-step forecast with uncertainty intervals."""
        model = self.prophet_models[key]
        future = model.make_future_dataframe(periods=horizon_days, freq="D")
        if "density" in df.columns:
            future["density"] = df["density"].values[-1]
        forecast = model.predict(future)
        target_row = forecast.iloc[-horizon_days // 30 if horizon_days >= 30 else -1]
        return {
            "mean": max(0.0, float(target_row["yhat"])),
            "lower": max(0.0, float(target_row["yhat_lower"])),
            "upper": max(0.0, float(target_row["yhat_upper"])),
        }


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _mape(actuals: np.ndarray, predictions: np.ndarray) -> float:
    """Mean Absolute Percentage Error. Ignores zero actual values."""
    mask = actuals != 0
    if mask.sum() == 0:
        return 999.0
    return float(np.mean(np.abs((actuals[mask] - predictions[mask]) / actuals[mask])) * 100)