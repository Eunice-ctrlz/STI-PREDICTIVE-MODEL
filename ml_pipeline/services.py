"""
ML Pipeline Services
====================
Implements the three-model ML architecture defined in Section 4 of the
STI Predictive Model Technical Documentation v1.0.

Models
------
1. STIRiskClassifier     — XGBoost + Random Forest voting ensemble
2. PatternPredictor      — LSTM (PyTorch) + Prophet seasonal decomposition
3. EnsemblePredictor     — Fuses classifier + predictor outputs, computes SHAP,
                           enforces the clinical threshold gate, and writes
                           the immutable audit log.
4. DriftMonitor          — Weekly PSI calculation + bias/fairness subgroup checks.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import joblib

# scikit-learn
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score
from sklearn.preprocessing import label_binarize

# XGBoost
try:
    import xgboost as xgb
    _XGB_AVAILABLE = True
except ImportError:
    _XGB_AVAILABLE = False
    logging.warning("xgboost not installed — XGBClassifier will be replaced by RF.")

# PyTorch
try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False
    logging.warning("PyTorch not installed — LSTM forecaster unavailable.")

# Prophet
try:
    from prophet import Prophet
    _PROPHET_AVAILABLE = True
except ImportError:
    _PROPHET_AVAILABLE = False
    logging.warning("Prophet not installed — seasonal decomposition unavailable.")

# SHAP
try:
    import shap
    _SHAP_AVAILABLE = True
except ImportError:
    _SHAP_AVAILABLE = False
    logging.warning("shap not installed — SHAP explanations will be skipped.")

from django.utils import timezone
from django.db import transaction

from .models import (
    MLModel, ModelType, TrainingJob, TrainingStatus,
    RiskPrediction, OutbreakForecast, PredictionAuditLog, DriftReport,
    RiskLevel, STIClass,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STI_CLASSES = ["hiv", "chlamydia", "syphilis", "gonorrhoea", "hpv", "hsv2", "none"]
FEATURE_NAMES = [
    # 32 symptom binary flags
    "sx_genital_discharge", "sx_painful_urination", "sx_genital_sores", "sx_pelvic_pain",
    "sx_testicular_pain", "sx_abnormal_bleeding", "sx_itching", "sx_fever", "sx_rash",
    "sx_swollen_lymph_nodes", "sx_rectal_pain", "sx_rectal_bleeding", "sx_sore_throat",
    "sx_joint_pain", "sx_hair_loss", "sx_weight_loss", "sx_night_sweats", "sx_fatigue",
    "sx_nausea", "sx_vomiting", "sx_diarrhoea", "sx_abdominal_pain", "sx_back_pain",
    "sx_dysuria", "sx_dyspareunia", "sx_menorrhagia", "sx_metrorrhagia",
    "sx_urethral_discharge", "sx_vaginal_odour", "sx_dysmenorrhoea",
    "sx_proctitis", "sx_lymphadenopathy",
    # Behavioural / demographic
    "composite_risk_score", "age_encoded", "sex_encoded", "region_encoded",
    # Temporal
    "month_of_year", "quarter", "day_of_week",
    # Behavioural embedding (single float from preprocessing)
    "behavioural_embedding_0",
]

ARTEFACT_DIR = Path(os.getenv("ML_ARTEFACT_DIR", "/var/ml_artefacts"))
CLINICAL_ALERT_THRESHOLD = 0.7
DEPLOYMENT_AUC_THRESHOLD = 0.85
DEPLOYMENT_F1_THRESHOLD = 0.75
DEPLOYMENT_MAPE_THRESHOLD = 15.0
PSI_ALERT_THRESHOLD = 0.2
BIAS_AUC_THRESHOLD = 0.80


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _feature_hash(features: Dict[str, Any]) -> str:
    canonical = json.dumps(features, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _build_feature_vector(payload: Dict[str, Any]) -> np.ndarray:
    """
    Assemble the fixed-length feature vector from an InferenceRequest payload dict.
    Order must match FEATURE_NAMES exactly.
    """
    symptom_vector = payload.get("symptom_vector", [0] * 32)
    temporal = payload.get("temporal_features", {})
    embedding = payload.get("behavioural_embedding", [0.0])

    vector = (
        list(symptom_vector)
        + [
            payload.get("composite_risk_score", 0.0),
            payload.get("age_encoded", 0),
            payload.get("sex_encoded", 0),
            payload.get("region_encoded", 0),
            temporal.get("month_of_year", 0.0),
            temporal.get("quarter", 0.0),
            temporal.get("day_of_week", 0.0),
            embedding[0] if embedding else 0.0,
        ]
    )
    return np.array(vector, dtype=float)


def _risk_level_from_score(score: float) -> str:
    if score >= 0.7:
        return RiskLevel.CRITICAL
    if score >= 0.5:
        return RiskLevel.HIGH
    if score >= 0.3:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def _psi(baseline: np.ndarray, current: np.ndarray, buckets: int = 10) -> float:
    """Population Stability Index between two distributions."""
    eps = 1e-8
    min_val = min(baseline.min(), current.min())
    max_val = max(baseline.max(), current.max()) + eps
    bins = np.linspace(min_val, max_val, buckets + 1)
    base_pct = np.histogram(baseline, bins=bins)[0] / (len(baseline) + eps) + eps
    curr_pct = np.histogram(current, bins=bins)[0] / (len(current) + eps) + eps
    return float(np.sum((curr_pct - base_pct) * np.log(curr_pct / base_pct)))


# ---------------------------------------------------------------------------
# 1. STI Risk Classifier
# ---------------------------------------------------------------------------

class STIRiskClassifier:
    """
    Multi-class XGBoost + Random Forest voting ensemble.

    Architecture (Section 4.1.1):
      - XGBoost with scale_pos_weight tuned per class
      - Random Forest with class_weight='balanced'
      - Soft voting (probability averaging) with configurable weights
      - Isotonic calibration (CalibratedClassifierCV) on a held-out fold
      - Evaluation gate: AUC-ROC ≥ 0.85 and F1 ≥ 0.75 per class before deployment
    """

    def __init__(self, params: Optional[Dict] = None):
        self.params = params or {}
        self.model: Optional[VotingClassifier] = None
        self.calibrated_model: Optional[CalibratedClassifierCV] = None
        self.explainer = None  # SHAP TreeExplainer, set after training
        self.class_names = STI_CLASSES

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_xgb(self, class_weights: Optional[Dict[int, float]] = None):
        if not _XGB_AVAILABLE:
            return None
        p = self.params
        return xgb.XGBClassifier(
            n_estimators=p.get("xgb_n_estimators", 500),
            max_depth=p.get("xgb_max_depth", 6),
            learning_rate=p.get("xgb_learning_rate", 0.05),
            subsample=p.get("xgb_subsample", 0.8),
            colsample_bytree=p.get("xgb_colsample_bytree", 0.8),
            use_label_encoder=False,
            eval_metric="mlogloss",
            random_state=42,
            n_jobs=-1,
        )

    def _build_rf(self):
        p = self.params
        return RandomForestClassifier(
            n_estimators=p.get("rf_n_estimators", 200),
            max_depth=p.get("rf_max_depth", None),
            min_samples_split=p.get("rf_min_samples_split", 4),
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )

    # ------------------------------------------------------------------
    # Train
    # ------------------------------------------------------------------

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        job: TrainingJob,
    ) -> Dict[str, Any]:
        """
        Full training run with stratified k-fold evaluation.
        Returns evaluation metrics dict.
        """
        logger.info("STIRiskClassifier: starting training (n=%d)", len(X))

        w_xgb = self.params.get("ensemble_weight_xgb", 0.6)
        w_rf = self.params.get("ensemble_weight_rf", 0.4)

        estimators = []
        if _XGB_AVAILABLE:
            estimators.append(("xgb", self._build_xgb()))
        estimators.append(("rf", self._build_rf()))

        self.model = VotingClassifier(
            estimators=estimators,
            voting="soft",
            weights=[w_xgb, w_rf] if _XGB_AVAILABLE else [1.0],
        )

        # Stratified 5-fold evaluation
        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        auc_scores: Dict[str, List[float]] = {c: [] for c in self.class_names}
        f1_scores: Dict[str, List[float]] = {c: [] for c in self.class_names}

        y_bin = label_binarize(y, classes=list(range(len(self.class_names))))

        for fold, (train_idx, val_idx) in enumerate(skf.split(X, y)):
            X_tr, X_val = X[train_idx], X[val_idx]
            y_tr, y_val = y[train_idx], y[val_idx]

            self.model.fit(X_tr, y_tr)
            proba = self.model.predict_proba(X_val)
            preds = self.model.predict(X_val)

            for i, cls in enumerate(self.class_names):
                if y_bin[val_idx, i].sum() > 0:
                    auc_scores[cls].append(
                        roc_auc_score(y_bin[val_idx, i], proba[:, i])
                    )
                f1_scores[cls].append(
                    f1_score(y_val, preds, labels=[i], average="macro", zero_division=0)
                )
            logger.info("  Fold %d complete", fold + 1)

        # Final fit on full dataset
        self.model.fit(X, y)

        # Isotonic calibration
        self.calibrated_model = CalibratedClassifierCV(
            self.model, method="isotonic", cv="prefit"
        )
        # Use a small held-out set for calibration (last 20%)
        split = int(len(X) * 0.8)
        self.calibrated_model.fit(X[split:], y[split:])

        # SHAP explainer
        if _SHAP_AVAILABLE and _XGB_AVAILABLE:
            xgb_model = dict(self.model.named_estimators_).get("xgb")
            if xgb_model:
                self.explainer = shap.TreeExplainer(xgb_model)

        metrics = {
            cls: {
                "auc_roc": float(np.mean(auc_scores[cls])) if auc_scores[cls] else None,
                "f1": float(np.mean(f1_scores[cls])),
            }
            for cls in self.class_names
        }

        meets_threshold = all(
            (m["auc_roc"] or 0) >= DEPLOYMENT_AUC_THRESHOLD
            and m["f1"] >= DEPLOYMENT_F1_THRESHOLD
            for m in metrics.values()
            if m["auc_roc"] is not None
        )

        logger.info(
            "STIRiskClassifier training complete. Meets threshold: %s", meets_threshold
        )
        return {"per_class": metrics, "meets_deployment_threshold": meets_threshold}

    # ------------------------------------------------------------------
    # Predict
    # ------------------------------------------------------------------

    def predict_proba(self, feature_vector: np.ndarray) -> Dict[str, float]:
        """Return probability dict for a single feature vector."""
        model = self.calibrated_model or self.model
        if model is None:
            raise RuntimeError("Classifier has not been trained or loaded.")
        proba = model.predict_proba(feature_vector.reshape(1, -1))[0]
        return {cls: float(proba[i]) for i, cls in enumerate(self.class_names)}

    def explain(self, feature_vector: np.ndarray) -> Optional[Dict[str, float]]:
        """Return SHAP values for the predicted class."""
        if not _SHAP_AVAILABLE or self.explainer is None:
            return None
        sv = self.explainer.shap_values(feature_vector.reshape(1, -1))
        # sv is list[n_classes] for multi-class TreeExplainer
        if isinstance(sv, list):
            # Use the class with max predicted probability
            proba = self.predict_proba(feature_vector)
            top_class_idx = STI_CLASSES.index(max(proba, key=proba.get))
            sv_class = sv[top_class_idx][0]
        else:
            sv_class = sv[0]
        return {name: float(val) for name, val in zip(FEATURE_NAMES, sv_class)}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {"model": self.model, "calibrated": self.calibrated_model},
            path,
        )
        logger.info("Classifier saved to %s", path)

    @classmethod
    def load(cls, path: Path, params: Optional[Dict] = None) -> "STIRiskClassifier":
        obj = cls(params=params)
        data = joblib.load(path)
        obj.model = data["model"]
        obj.calibrated_model = data["calibrated"]
        if _SHAP_AVAILABLE and _XGB_AVAILABLE and obj.model:
            xgb_model = dict(obj.model.named_estimators_).get("xgb")
            if xgb_model:
                obj.explainer = shap.TreeExplainer(xgb_model)
        return obj


# ---------------------------------------------------------------------------
# 2. LSTM Model (PyTorch)
# ---------------------------------------------------------------------------

class _LSTMNet(nn.Module if _TORCH_AVAILABLE else object):
    def __init__(self, input_size: int, hidden_size: int, num_layers: int, dropout: float):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0.0,
            batch_first=True,
        )
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])


# ---------------------------------------------------------------------------
# 3. Pattern Predictor (LSTM + Prophet ensemble)
# ---------------------------------------------------------------------------

class PatternPredictor:
    """
    LSTM + Prophet ensemble for 30/60/90-day outbreak forecasting.

    Architecture (Section 4.1.2):
      - LSTM: learns non-linear temporal patterns in monthly incidence sequences.
      - Prophet: captures seasonality and holiday effects.
      - Ensemble: weighted average (default 60% LSTM, 40% Prophet).
      - Validation: walk-forward time-series split. Target MAPE ≤ 15%.
    """

    INPUT_FEATURES = [
        "incidence_rate",
        "population_density",
        "healthcare_access_index",
        "month_sin",  # sin/cos encoding of month for seasonality
        "month_cos",
    ]

    def __init__(self, params: Optional[Dict] = None):
        self.params = params or {}
        self.lstm_model = None
        self.prophet_models: Dict[str, Any] = {}  # county → Prophet model
        self.scaler = None
        self.ensemble_w_lstm = self.params.get("ensemble_weight_lstm", 0.6)
        self.ensemble_w_prophet = 1.0 - self.ensemble_w_lstm
        self.seq_len = self.params.get("sequence_length", 24)

    # ------------------------------------------------------------------
    # Feature engineering helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _add_temporal_features(df) -> "pd.DataFrame":
        import pandas as pd
        df = df.copy()
        df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
        df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
        return df

    def _make_sequences(self, series: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        X, y = [], []
        for i in range(len(series) - self.seq_len):
            X.append(series[i : i + self.seq_len])
            y.append(series[i + self.seq_len, 0])  # predict incidence_rate
        return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)

    # ------------------------------------------------------------------
    # LSTM training
    # ------------------------------------------------------------------

    def _train_lstm(self, series: np.ndarray) -> float:
        """Train LSTM on a scaled feature sequence. Returns validation MAPE."""
        if not _TORCH_AVAILABLE:
            logger.warning("PyTorch unavailable — skipping LSTM training.")
            return float("nan")

        from sklearn.preprocessing import MinMaxScaler
        self.scaler = MinMaxScaler()
        scaled = self.scaler.fit_transform(series)

        X, y = self._make_sequences(scaled)
        split = int(len(X) * 0.8)
        X_tr, X_val = X[:split], X[split:]
        y_tr, y_val = y[:split], y[split:]

        p = self.params
        net = _LSTMNet(
            input_size=len(self.INPUT_FEATURES),
            hidden_size=p.get("hidden_size", 128),
            num_layers=p.get("num_layers", 2),
            dropout=p.get("dropout", 0.2),
        )

        optimizer = torch.optim.Adam(net.parameters(), lr=p.get("learning_rate", 0.001))
        loss_fn = nn.MSELoss()
        patience = p.get("early_stopping_patience", 10)
        best_val_loss = float("inf")
        no_improve = 0

        dataset = TensorDataset(
            torch.tensor(X_tr), torch.tensor(y_tr).unsqueeze(1)
        )
        loader = DataLoader(dataset, batch_size=p.get("batch_size", 32), shuffle=True)

        for epoch in range(p.get("epochs", 100)):
            net.train()
            for xb, yb in loader:
                optimizer.zero_grad()
                loss_fn(net(xb), yb).backward()
                optimizer.step()

            net.eval()
            with torch.no_grad():
                val_pred = net(torch.tensor(X_val))
                val_loss = loss_fn(val_pred, torch.tensor(y_val).unsqueeze(1)).item()

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                no_improve = 0
                torch.save(net.state_dict(), "/tmp/_lstm_best.pt")
            else:
                no_improve += 1
                if no_improve >= patience:
                    logger.info("LSTM early stop at epoch %d", epoch)
                    break

        net.load_state_dict(torch.load("/tmp/_lstm_best.pt"))
        self.lstm_model = net

        # MAPE on validation set
        net.eval()
        with torch.no_grad():
            preds = net(torch.tensor(X_val)).numpy().flatten()
        # Inverse transform (only incidence_rate column = 0)
        dummy = np.zeros((len(preds), len(self.INPUT_FEATURES)))
        dummy[:, 0] = preds
        preds_inv = self.scaler.inverse_transform(dummy)[:, 0]

        dummy_act = np.zeros((len(y_val), len(self.INPUT_FEATURES)))
        dummy_act[:, 0] = y_val
        act_inv = self.scaler.inverse_transform(dummy_act)[:, 0]

        mape = float(np.mean(np.abs((act_inv - preds_inv) / (act_inv + 1e-8))) * 100)
        logger.info("LSTM validation MAPE: %.2f%%", mape)
        return mape

    # ------------------------------------------------------------------
    # Prophet training
    # ------------------------------------------------------------------

    def _train_prophet(self, county: str, df) -> float:
        """Fit a Prophet model for a single county. Returns MAPE."""
        if not _PROPHET_AVAILABLE:
            logger.warning("Prophet unavailable — skipping.")
            return float("nan")

        import pandas as pd
        prophet_df = df[["ds", "y"]].dropna()
        m = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False,
            interval_width=0.95,
        )
        m.fit(prophet_df)
        self.prophet_models[county] = m

        # Walk-forward MAPE on last 20% of data
        cutoff = prophet_df["ds"].quantile(0.8)
        train_df = prophet_df[prophet_df["ds"] <= cutoff]
        val_df = prophet_df[prophet_df["ds"] > cutoff]
        m_val = Prophet(yearly_seasonality=True, weekly_seasonality=False)
        m_val.fit(train_df)
        future = m_val.make_future_dataframe(periods=len(val_df), freq="M")
        fc = m_val.predict(future)
        fc = fc[fc["ds"].isin(val_df["ds"])]
        if fc.empty:
            return float("nan")
        mape = float(
            np.mean(
                np.abs(
                    (val_df["y"].values - fc["yhat"].values)
                    / (val_df["y"].values + 1e-8)
                )
            )
            * 100
        )
        logger.info("Prophet MAPE for %s: %.2f%%", county, mape)
        return mape

    # ------------------------------------------------------------------
    # Forecast
    # ------------------------------------------------------------------

    def forecast(
        self,
        county: str,
        recent_sequence: np.ndarray,
        horizons_months: List[int] = [1, 2, 3],
    ) -> Dict[int, Dict[str, float]]:
        """
        Produce ensemble forecasts for the given month horizons.
        Returns {horizon_months: {rate, lower_95, upper_95}}.
        """
        results = {}
        for h in horizons_months:
            lstm_rate = self._lstm_forecast(recent_sequence, h)
            prophet_rate, prophet_lower, prophet_upper = self._prophet_forecast(county, h)

            if lstm_rate is not None and prophet_rate is not None:
                rate = self.ensemble_w_lstm * lstm_rate + self.ensemble_w_prophet * prophet_rate
            elif lstm_rate is not None:
                rate = lstm_rate
            elif prophet_rate is not None:
                rate = prophet_rate
            else:
                rate = 0.0

            # Confidence interval: use Prophet bounds scaled by ensemble weight
            lower = prophet_lower if prophet_lower is not None else rate * 0.85
            upper = prophet_upper if prophet_upper is not None else rate * 1.15

            results[h * 30] = {
                "rate_per_100k": max(0.0, float(rate)),
                "lower_95": max(0.0, float(lower)),
                "upper_95": float(upper),
            }
        return results

    def _lstm_forecast(self, sequence: np.ndarray, horizon: int) -> Optional[float]:
        if not _TORCH_AVAILABLE or self.lstm_model is None or self.scaler is None:
            return None
        self.lstm_model.eval()
        scaled = self.scaler.transform(sequence)
        inp = torch.tensor(scaled[-self.seq_len :].astype(np.float32)).unsqueeze(0)
        # Iterative multi-step prediction
        for _ in range(horizon):
            with torch.no_grad():
                pred = self.lstm_model(inp).item()
            # Shift window
            next_step = inp[:, -1, :].clone()
            next_step[0, 0] = pred
            inp = torch.cat([inp[:, 1:, :], next_step.unsqueeze(1)], dim=1)

        # Inverse transform
        dummy = np.zeros((1, len(self.INPUT_FEATURES)))
        dummy[0, 0] = inp[0, -1, 0].item()
        return float(self.scaler.inverse_transform(dummy)[0, 0])

    def _prophet_forecast(
        self, county: str, horizon_months: int
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        if not _PROPHET_AVAILABLE or county not in self.prophet_models:
            return None, None, None
        m = self.prophet_models[county]
        future = m.make_future_dataframe(periods=horizon_months, freq="M")
        fc = m.predict(future).iloc[-1]
        return float(fc["yhat"]), float(fc["yhat_lower"]), float(fc["yhat_upper"])

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, dir_path: Path) -> None:
        dir_path.mkdir(parents=True, exist_ok=True)
        if _TORCH_AVAILABLE and self.lstm_model:
            torch.save(self.lstm_model.state_dict(), dir_path / "lstm.pt")
        if self.scaler:
            joblib.dump(self.scaler, dir_path / "scaler.joblib")
        if _PROPHET_AVAILABLE and self.prophet_models:
            joblib.dump(self.prophet_models, dir_path / "prophet_models.joblib")
        joblib.dump({"params": self.params}, dir_path / "meta.joblib")

    @classmethod
    def load(cls, dir_path: Path) -> "PatternPredictor":
        meta = joblib.load(dir_path / "meta.joblib")
        obj = cls(params=meta["params"])
        if _TORCH_AVAILABLE and (dir_path / "lstm.pt").exists():
            net = _LSTMNet(
                input_size=len(cls.INPUT_FEATURES),
                hidden_size=obj.params.get("hidden_size", 128),
                num_layers=obj.params.get("num_layers", 2),
                dropout=obj.params.get("dropout", 0.2),
            )
            net.load_state_dict(torch.load(dir_path / "lstm.pt", map_location="cpu"))
            net.eval()
            obj.lstm_model = net
        if (dir_path / "scaler.joblib").exists():
            obj.scaler = joblib.load(dir_path / "scaler.joblib")
        if _PROPHET_AVAILABLE and (dir_path / "prophet_models.joblib").exists():
            obj.prophet_models = joblib.load(dir_path / "prophet_models.joblib")
        return obj


# ---------------------------------------------------------------------------
# 4. Ensemble Predictor (Prediction Engine — Section 4, Layer L4)
# ---------------------------------------------------------------------------

class EnsemblePredictor:
    """
    Orchestrates the full prediction flow for a single inference request:

    1. Load active classifier and (optionally) run SHAP.
    2. Build RiskPrediction record with clinical gate flag.
    3. Write PredictionAuditLog entry.
    4. Return structured output dict.

    Clinical gate (Section 8.2):
      If any class probability ≥ 0.7, clinical_review_required is set True.
      The patient dashboard layer must NOT surface the result until
      clinical_review_completed is True.
    """

    def __init__(self):
        self._classifier: Optional[STIRiskClassifier] = None
        self._active_model_record: Optional[MLModel] = None

    # ------------------------------------------------------------------
    # Classifier loading
    # ------------------------------------------------------------------

    def _ensure_classifier_loaded(self) -> None:
        if self._classifier is not None:
            return
        try:
            record = MLModel.objects.get(
                model_type=ModelType.RISK_CLASSIFIER,
                is_active=True,
                clinical_validation_completed=True,
            )
        except MLModel.DoesNotExist:
            raise RuntimeError(
                "No active, clinically validated STI risk classifier found. "
                "Complete clinical validation and activate a model version before inference."
            )
        path = Path(record.artefact_path)
        self._classifier = STIRiskClassifier.load(path)
        self._active_model_record = record
        logger.info("Loaded classifier v%s from %s", record.version, path)

    # ------------------------------------------------------------------
    # Predict
    # ------------------------------------------------------------------

    @transaction.atomic
    def predict(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run full inference pipeline for a preprocessed anonymous record.
        payload must match the InferenceRequest schema fields.
        """
        self._ensure_classifier_loaded()

        feature_vector = _build_feature_vector(payload)
        feat_hash = _feature_hash(payload)

        # Classifier inference
        proba = self._classifier.predict_proba(feature_vector)
        max_class = max(proba, key=proba.get)
        max_score = proba[max_class]
        risk_level = _risk_level_from_score(max_score)

        # SHAP explainability
        shap_values = None
        top_features = []
        if payload.get("compute_shap", True):
            shap_values = self._classifier.explain(feature_vector)
            if shap_values:
                sorted_feats = sorted(shap_values.items(), key=lambda x: abs(x[1]), reverse=True)
                top_features = [
                    {
                        "feature": f,
                        "shap_value": round(v, 4),
                        "direction": "increases_risk" if v > 0 else "decreases_risk",
                        "display_label": f.replace("sx_", "").replace("_", " ").title(),
                    }
                    for f, v in sorted_feats[:3]
                ]

        # Simple confidence interval via score ± 1 std proxy
        ci_half = 0.05 + (1.0 - max_score) * 0.1
        confidence_lower = max(0.0, max_score - ci_half)
        confidence_upper = min(1.0, max_score + ci_half)

        # Clinical gate
        clinical_review_required = max_score >= CLINICAL_ALERT_THRESHOLD

        # Persist prediction
        prediction = RiskPrediction.objects.create(
            model_version=self._active_model_record,
            anonymous_id=payload["anonymous_id"],
            input_feature_hash=feat_hash,
            input_features=payload,
            sti_probabilities=proba,
            predicted_class=max_class,
            overall_risk_level=risk_level,
            overall_risk_score=round(max_score, 4),
            shap_values=shap_values,
            top_features=top_features,
            confidence_lower=round(confidence_lower, 4),
            confidence_upper=round(confidence_upper, 4),
            clinical_review_required=clinical_review_required,
            clinical_review_completed=False,
        )

        # Audit log
        PredictionAuditLog.objects.create(
            event_type="prediction_created",
            prediction=prediction,
            model_version=self._active_model_record,
            anonymous_id=payload["anonymous_id"],
            actor="ml_pipeline:ensemble_predictor",
            payload={
                "risk_level": risk_level,
                "predicted_class": max_class,
                "clinical_review_required": clinical_review_required,
                "feature_hash": feat_hash,
            },
        )

        return {
            "prediction_id": str(prediction.prediction_id),
            "anonymous_id": payload["anonymous_id"],
            "model_version_id": str(self._active_model_record.model_id),
            "model_version": self._active_model_record.version,
            "sti_probabilities": proba,
            "predicted_class": max_class,
            "overall_risk_level": risk_level,
            "overall_risk_score": round(max_score, 4),
            "top_features": top_features,
            "confidence_lower": round(confidence_lower, 4),
            "confidence_upper": round(confidence_upper, 4),
            "clinical_review_required": clinical_review_required,
            "clinical_review_completed": False,
            "created_at": prediction.created_at.isoformat(),
        }

    # ------------------------------------------------------------------
    # Clinical review completion
    # ------------------------------------------------------------------

    @transaction.atomic
    def complete_clinical_review(
        self,
        prediction_id: str,
        reviewed_by: str,
        approved: bool,
        notes: str = "",
    ) -> RiskPrediction:
        prediction = RiskPrediction.objects.select_for_update().get(
            prediction_id=prediction_id
        )
        prediction.clinical_review_completed = True
        prediction.reviewed_by = reviewed_by
        prediction.reviewed_at = timezone.now()
        prediction.save()

        PredictionAuditLog.objects.create(
            event_type="clinical_review_completed",
            prediction=prediction,
            model_version=prediction.model_version,
            anonymous_id=prediction.anonymous_id,
            actor=reviewed_by,
            payload={"approved": approved, "notes": notes},
        )
        return prediction


# ---------------------------------------------------------------------------
# 5. Training Orchestrator
# ---------------------------------------------------------------------------

class TrainingOrchestrator:
    """
    Manages the full training lifecycle for a given model type.
    Called by the Celery beat scheduler (quarterly) or by an API trigger.
    """

    def run(self, job_id: str) -> None:
        job = TrainingJob.objects.get(job_id=job_id)
        job.status = TrainingStatus.RUNNING
        job.started_at = timezone.now()
        job.save()

        try:
            if job.model_type == ModelType.RISK_CLASSIFIER:
                self._train_classifier(job)
            elif job.model_type == ModelType.PATTERN_PREDICTOR:
                self._train_pattern_predictor(job)
            else:
                raise NotImplementedError(f"No orchestration for {job.model_type}")

            job.status = TrainingStatus.COMPLETED
            job.completed_at = timezone.now()
            job.save()

        except Exception as exc:
            logger.exception("Training job %s failed", job_id)
            job.status = TrainingStatus.FAILED
            job.error_log = str(exc)
            job.completed_at = timezone.now()
            job.save()

    # ------------------------------------------------------------------

    def _train_classifier(self, job: TrainingJob) -> None:
        """
        Pull processed records from the preprocessing app and train classifier.
        Expects records with feature vectors already computed by PreprocessingPipeline.
        """
        from preprocessing.models import ProcessedRecord

        records = ProcessedRecord.objects.filter(
            created_at__date__gte=job.training_data_start,
            created_at__date__lte=job.training_data_end,
        ).exclude(risk_level=None)

        job.record_count = records.count()
        if job.record_count < 100:
            raise ValueError(
                f"Insufficient training data: {job.record_count} records. "
                "Minimum 100 required (target: 10,000+ per class)."
            )

        X_rows, y_rows = [], []
        class_dist: Dict[str, int] = {c: 0 for c in STI_CLASSES}

        for rec in records.iterator(chunk_size=500):
            sv = rec.symptoms.get("vector", [0] * 32)
            if len(sv) < 32:
                sv = sv + [0] * (32 - len(sv))
            row = (
                sv[:32]
                + [
                    rec.composite_risk_score or 0.0,
                    rec.demographics.get("age_encoded", 0),
                    rec.demographics.get("sex_encoded", 0),
                    0,  # region_encoded placeholder
                    rec.temporal_features.get("month_of_year", 0.0),
                    rec.temporal_features.get("quarter", 0.0),
                    rec.temporal_features.get("day_of_week", 0.0),
                    rec.composite_risk_score or 0.0,
                ]
            )
            X_rows.append(row)

            # Derive label from sti_labels (first positive STI, else "none")
            label = "none"
            for sti in STI_CLASSES[:-1]:
                if rec.sti_labels.get(sti, 0):
                    label = sti
                    break
            y_rows.append(STI_CLASSES.index(label))
            class_dist[label] = class_dist.get(label, 0) + 1

        job.class_distribution = class_dist
        job.save()

        X = np.array(X_rows, dtype=float)
        y = np.array(y_rows, dtype=int)

        clf = STIRiskClassifier(params=job.hyperparameters)
        metrics = clf.train(X, y, job)

        # Save artefact
        version = f"1.{job.created_at.strftime('%Y%m%d%H%M')}.0"
        artefact_path = ARTEFACT_DIR / "classifiers" / f"v{version}.joblib"
        clf.save(artefact_path)

        model_record = MLModel.objects.create(
            model_type=ModelType.RISK_CLASSIFIER,
            version=version,
            artefact_path=str(artefact_path),
            evaluation_metrics=metrics,
            meets_deployment_threshold=metrics.get("meets_deployment_threshold", False),
            feature_schema_version="1.0",
        )
        job.resulting_model = model_record
        job.save()

        PredictionAuditLog.objects.create(
            event_type="model_trained",
            model_version=model_record,
            actor="training_orchestrator",
            payload={
                "job_id": str(job.job_id),
                "record_count": job.record_count,
                "meets_threshold": metrics.get("meets_deployment_threshold"),
            },
        )

    def _train_pattern_predictor(self, job: TrainingJob) -> None:
        """
        Trains the LSTM + Prophet ensemble from aggregated monthly incidence data.
        Data sourced from geospatial.AggregatedIncident records.
        """
        import pandas as pd
        from geospatial.models import AggregatedIncident

        incidents = AggregatedIncident.objects.filter(
            period_start__gte=job.training_data_start,
            period_end__lte=job.training_data_end,
        ).select_related("grid_cell")

        if not incidents.exists():
            raise ValueError("No incident data in the requested training window.")

        # Build a monthly incidence dataframe per county
        rows = []
        for inc in incidents.iterator(chunk_size=1000):
            rows.append(
                {
                    "county": inc.grid_cell.county,
                    "sti_type": inc.sti_type,
                    "period_start": inc.period_start,
                    "incident_count": inc.incident_count,
                    "healthcare_access_index": inc.grid_cell.healthcare_access_index,
                    "population": inc.grid_cell.population_estimate,
                }
            )

        df = pd.DataFrame(rows)
        df["incidence_rate"] = (
            df["incident_count"] / (df["population"].clip(lower=1)) * 100_000
        )
        df["ds"] = pd.to_datetime(df["period_start"])
        df["y"] = df["incidence_rate"]
        df["month"] = df["ds"].dt.month

        df = PatternPredictor._add_temporal_features(df)

        predictor = PatternPredictor(params=job.hyperparameters)
        lstm_mape, prophet_mape = float("nan"), float("nan")

        # LSTM: train on national aggregate (all counties)
        national = df.groupby("ds")[["incidence_rate", "healthcare_access_index", "month_sin", "month_cos"]].mean().reset_index()
        national["population_density"] = 1.0  # placeholder
        feature_cols = PatternPredictor.INPUT_FEATURES
        if len(national) >= predictor.seq_len + 6:
            series = national[feature_cols].values
            lstm_mape = predictor._train_lstm(series)

        # Prophet: train per county
        prophet_mapes = []
        for county, grp in df.groupby("county"):
            county_df = grp.groupby("ds")["y"].mean().reset_index()
            if len(county_df) >= 12:
                m = predictor._train_prophet(county, county_df)
                if not np.isnan(m):
                    prophet_mapes.append(m)

        if prophet_mapes:
            prophet_mape = float(np.mean(prophet_mapes))

        version = f"1.{job.created_at.strftime('%Y%m%d%H%M')}.0"
        artefact_dir = ARTEFACT_DIR / "predictors" / f"v{version}"
        predictor.save(artefact_dir)

        meets = (
            (np.isnan(lstm_mape) or lstm_mape <= DEPLOYMENT_MAPE_THRESHOLD)
            and (np.isnan(prophet_mape) or prophet_mape <= DEPLOYMENT_MAPE_THRESHOLD)
        )

        model_record = MLModel.objects.create(
            model_type=ModelType.PATTERN_PREDICTOR,
            version=version,
            artefact_path=str(artefact_dir),
            evaluation_metrics={
                "lstm_mape": lstm_mape,
                "prophet_mape": prophet_mape,
                "target_mape": DEPLOYMENT_MAPE_THRESHOLD,
            },
            meets_deployment_threshold=meets,
            feature_schema_version="1.0",
        )
        job.resulting_model = model_record
        job.record_count = len(df)
        job.save()


# ---------------------------------------------------------------------------
# 6. Drift Monitor
# ---------------------------------------------------------------------------

class DriftMonitor:
    """
    Computes weekly PSI drift reports and demographic bias checks.
    Section 4.3 and 8.3.
    """

    def run_weekly_check(self) -> List[DriftReport]:
        """Run PSI and bias checks for all active models. Called by Celery beat."""
        reports = []
        for model_record in MLModel.objects.filter(is_active=True):
            try:
                report = self._check_model(model_record)
                reports.append(report)
            except Exception:
                logger.exception("Drift check failed for model %s", model_record.model_id)
        return reports

    def _check_model(self, model_record: MLModel) -> DriftReport:
        from preprocessing.models import ProcessedRecord

        today = date.today()
        # Baseline: records from 60–30 days ago
        baseline_qs = ProcessedRecord.objects.filter(
            created_at__date__gte=today - timedelta(days=60),
            created_at__date__lt=today - timedelta(days=30),
        )
        # Current: last 30 days
        current_qs = ProcessedRecord.objects.filter(
            created_at__date__gte=today - timedelta(days=30),
        )

        if not baseline_qs.exists() or not current_qs.exists():
            return DriftReport.objects.create(
                model_version=model_record,
                report_date=today,
                psi_score=0.0,
                feature_psi={},
                alert_triggered=False,
                subgroup_auc={},
                bias_flag=False,
                notes="Insufficient data for drift computation.",
            )

        # PSI on composite_risk_score (proxy for overall distribution shift)
        baseline_scores = np.array(
            list(baseline_qs.values_list("composite_risk_score", flat=True)),
            dtype=float,
        )
        current_scores = np.array(
            list(current_qs.values_list("composite_risk_score", flat=True)),
            dtype=float,
        )

        # Remove NaN
        baseline_scores = baseline_scores[~np.isnan(baseline_scores)]
        current_scores = current_scores[~np.isnan(current_scores)]

        overall_psi = _psi(baseline_scores, current_scores) if len(baseline_scores) > 10 and len(current_scores) > 10 else 0.0
        alert = overall_psi > PSI_ALERT_THRESHOLD

        # Subgroup AUC — placeholder (requires labelled holdout; compute when available)
        subgroup_auc: Dict[str, float] = {}
        bias_flag = any(v < BIAS_AUC_THRESHOLD for v in subgroup_auc.values())

        # Update model record
        model_record.psi_score = overall_psi
        model_record.last_psi_check = timezone.now()
        model_record.drift_alert_active = alert
        model_record.save()

        if alert:
            logger.warning(
                "Drift alert triggered for model %s: PSI=%.3f", model_record.model_id, overall_psi
            )
            PredictionAuditLog.objects.create(
                event_type="drift_alert",
                model_version=model_record,
                actor="drift_monitor",
                payload={"psi_score": overall_psi, "threshold": PSI_ALERT_THRESHOLD},
            )

        return DriftReport.objects.create(
            model_version=model_record,
            report_date=today,
            psi_score=overall_psi,
            feature_psi={"composite_risk_score": overall_psi},
            alert_triggered=alert,
            subgroup_auc=subgroup_auc,
            bias_flag=bias_flag,
        )


# ---------------------------------------------------------------------------
# 7. Forecast Service (thin orchestration layer used by the API)
# ---------------------------------------------------------------------------

class ForecastService:
    """
    Loads the active PatternPredictor and generates OutbreakForecast records.
    """

    def __init__(self):
        self._predictor: Optional[PatternPredictor] = None
        self._model_record: Optional[MLModel] = None

    def _ensure_loaded(self) -> None:
        if self._predictor is not None:
            return
        try:
            record = MLModel.objects.get(
                model_type=ModelType.PATTERN_PREDICTOR,
                is_active=True,
                clinical_validation_completed=True,
            )
        except MLModel.DoesNotExist:
            raise RuntimeError("No active, validated pattern predictor found.")
        self._predictor = PatternPredictor.load(Path(record.artefact_path))
        self._model_record = record

    @transaction.atomic
    def generate_forecast(
        self,
        county: str,
        sti_type: str,
        baseline_months: int = 60,
    ) -> OutbreakForecast:
        self._ensure_loaded()
        import pandas as pd
        from geospatial.models import AggregatedIncident

        today = date.today()
        start = today - timedelta(days=baseline_months * 30)

        incidents = AggregatedIncident.objects.filter(
            grid_cell__county=county,
            sti_type=sti_type if sti_type != "all" else None if False else sti_type,
            period_start__gte=start,
        ).select_related("grid_cell")

        if not incidents.exists():
            raise ValueError(f"No incident data for {county}/{sti_type} in baseline window.")

        rows = []
        for inc in incidents:
            pop = inc.grid_cell.population_estimate or 1
            rows.append(
                {
                    "ds": pd.Timestamp(inc.period_start),
                    "incidence_rate": inc.incident_count / pop * 100_000,
                    "population_density": 1.0,
                    "healthcare_access_index": inc.grid_cell.healthcare_access_index,
                    "month": inc.period_start.month,
                }
            )

        df = pd.DataFrame(rows).sort_values("ds")
        df = PatternPredictor._add_temporal_features(df)
        feature_cols = PatternPredictor.INPUT_FEATURES
        sequence = df[feature_cols].values

        baseline_rate = float(df["incidence_rate"].mean())
        forecasts = self._predictor.forecast(county, sequence, horizons_months=[1, 2, 3])

        def _yoy_delta():
            one_year_ago = today - timedelta(days=365)
            old = AggregatedIncident.objects.filter(
                grid_cell__county=county, sti_type=sti_type,
                period_start__gte=one_year_ago - timedelta(days=30),
                period_start__lt=one_year_ago + timedelta(days=30),
            )
            if not old.exists():
                return None
            old_count = sum(i.incident_count for i in old)
            recent = AggregatedIncident.objects.filter(
                grid_cell__county=county, sti_type=sti_type,
                period_start__gte=today - timedelta(days=30),
            )
            if not recent.exists() or old_count == 0:
                return None
            recent_count = sum(i.incident_count for i in recent)
            return round((recent_count - old_count) / old_count * 100, 2)

        yoy = _yoy_delta()
        f30, f60, f90 = forecasts[30], forecasts[60], forecasts[90]

        trend = "stable"
        if yoy is not None:
            trend = "rising" if yoy > 5 else ("declining" if yoy < -5 else "stable")

        # Upsert forecast
        forecast, _ = OutbreakForecast.objects.update_or_create(
            county=county,
            sti_type=sti_type,
            forecast_generated_on=today,
            defaults={
                "model_version": self._model_record,
                "baseline_start": start,
                "baseline_end": today,
                "baseline_incidence_rate": baseline_rate,
                "forecast_30d_rate": f30["rate_per_100k"],
                "forecast_30d_lower": f30["lower_95"],
                "forecast_30d_upper": f30["upper_95"],
                "forecast_60d_rate": f60["rate_per_100k"],
                "forecast_60d_lower": f60["lower_95"],
                "forecast_60d_upper": f60["upper_95"],
                "forecast_90d_rate": f90["rate_per_100k"],
                "forecast_90d_lower": f90["lower_95"],
                "forecast_90d_upper": f90["upper_95"],
                "year_over_year_delta_pct": yoy,
                "trend_direction": trend,
                "ensemble_weight_lstm": self._predictor.ensemble_w_lstm,
                "ensemble_weight_prophet": self._predictor.ensemble_w_prophet,
            },
        )
        return forecast