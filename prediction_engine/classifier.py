"""
STI Predictive Model — ML Pipeline (L3)
classifier.py

STI Risk Classifier: XGBoost + Random Forest ensemble with soft voting.
Handles training, evaluation, threshold checking, SHAP explanation,
and inference. All runs are logged to MLflow.

Target classes: hiv, chlamydia, syphilis, gonorrhoea, hpv, hsv2, none
Performance thresholds (§4.1.1): AUC-ROC ≥ 0.85, F1 ≥ 0.75 per class
"""

import hashlib
import logging
import pickle
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
import shap
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.metrics import (
    classification_report,
    roc_auc_score,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import LabelBinarizer
from xgboost import XGBClassifier

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STI_CLASSES = ["hiv", "chlamydia", "syphilis", "gonorrhoea", "hpv", "hsv2", "none"]

# Performance gates (§4.1.1)
AUC_ROC_THRESHOLD = 0.85
F1_THRESHOLD = 0.75

FEATURE_COLS = (
    # 32 symptom binary features
    [f"sym_{i}" for i in range(32)]
    # Behavioural + demographic
    + ["composite_risk_score", "age_encoded", "sex_encoded", "region_encoded"]
    # Temporal
    + ["month_of_year", "quarter"]
    # Prior STI history flags
    + ["prior_hiv", "prior_chlamydia", "prior_syphilis", "prior_gonorrhoea",
       "prior_hpv", "prior_hsv2"]
)

DEFAULT_XGB_PARAMS = {
    "n_estimators": 400,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "use_label_encoder": False,
    "eval_metric": "mlogloss",
    "random_state": 42,
    "n_jobs": -1,
}

DEFAULT_RF_PARAMS = {
    "n_estimators": 300,
    "max_depth": 12,
    "min_samples_split": 10,
    "class_weight": "balanced",
    "random_state": 42,
    "n_jobs": -1,
}


# ---------------------------------------------------------------------------
# Data Preparation
# ---------------------------------------------------------------------------

def build_feature_matrix(records: List[Dict]) -> Tuple[pd.DataFrame, Optional[pd.Series]]:
    """
    Convert preprocessed record dicts (from L2 output) into a feature
    matrix and optional label series.

    Each record dict is expected to contain:
      - symptom_vector: List[int] of length 32
      - composite_risk_score, age_encoded, sex_encoded, region_encoded
      - temporal_features: {month_of_year, quarter}
      - prior_sti_history: List[str]
      - sti_label (optional, for training)
    """
    rows = []
    labels = []

    for rec in records:
        sv = rec.get("symptom_vector", [0] * 32)
        row = {f"sym_{i}": int(sv[i]) if i < len(sv) else 0 for i in range(32)}

        row["composite_risk_score"] = float(rec.get("composite_risk_score", 0.0))
        row["age_encoded"] = int(rec.get("age_encoded", 0))
        row["sex_encoded"] = int(rec.get("sex_encoded", 0))
        row["region_encoded"] = int(rec.get("region_encoded", 0))

        temporal = rec.get("temporal_features", {})
        row["month_of_year"] = float(temporal.get("month_of_year", 0.5))
        row["quarter"] = float(temporal.get("quarter", 0.5))

        prior = rec.get("prior_sti_history", [])
        for sti in ["hiv", "chlamydia", "syphilis", "gonorrhoea", "hpv", "hsv2"]:
            row[f"prior_{sti}"] = 1 if sti in prior else 0

        rows.append(row)
        if "sti_label" in rec:
            labels.append(rec["sti_label"])

    X = pd.DataFrame(rows, columns=FEATURE_COLS)
    y = pd.Series(labels) if labels else None
    return X, y


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class STIRiskClassifier:
    """
    Ensemble: XGBoost + Random Forest with soft voting.
    Calibrated with isotonic regression for reliable probabilities.
    """

    def __init__(
        self,
        xgb_params: Optional[Dict] = None,
        rf_params: Optional[Dict] = None,
        mlflow_experiment_id: Optional[str] = None,
    ):
        self.xgb_params = {**DEFAULT_XGB_PARAMS, **(xgb_params or {})}
        self.rf_params = {**DEFAULT_RF_PARAMS, **(rf_params or {})}
        self.mlflow_experiment_id = mlflow_experiment_id

        self.model: Optional[CalibratedClassifierCV] = None
        self.label_binarizer = LabelBinarizer()
        self.classes_ = STI_CLASSES
        self.feature_cols = FEATURE_COLS
        self.shap_explainer: Optional[shap.TreeExplainer] = None
        self.model_hash: Optional[str] = None
        self.mlflow_run_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(
        self,
        records: List[Dict],
        run_name: Optional[str] = None,
        cv_folds: int = 5,
    ) -> Dict:
        """
        Full training pipeline with cross-validated evaluation.
        Returns metrics dict. Logs everything to MLflow.
        """
        X, y = build_feature_matrix(records)
        if y is None:
            raise ValueError("Training records must include 'sti_label' field")
        if len(X) < 10_000:
            logger.warning(
                "Training set has %d records — minimum recommended is 10,000 (§4.1.1)",
                len(X),
            )

        if self.mlflow_experiment_id:
            mlflow.set_experiment(experiment_id=self.mlflow_experiment_id)

        with mlflow.start_run(run_name=run_name or "sti_risk_classifier") as run:
            self.mlflow_run_id = run.info.run_id

            # Log hyperparameters
            mlflow.log_params({f"xgb_{k}": v for k, v in self.xgb_params.items()})
            mlflow.log_params({f"rf_{k}": v for k, v in self.rf_params.items()})
            mlflow.log_param("cv_folds", cv_folds)
            mlflow.log_param("training_samples", len(X))
            mlflow.log_param("class_distribution", y.value_counts().to_dict())

            # Build ensemble
            xgb = XGBClassifier(**self.xgb_params)
            rf = RandomForestClassifier(**self.rf_params)
            ensemble = VotingClassifier(
                estimators=[("xgb", xgb), ("rf", rf)],
                voting="soft",
                n_jobs=-1,
            )
            self.model = CalibratedClassifierCV(
                ensemble, method="isotonic", cv=3
            )

            # Cross-validated evaluation
            cv_metrics = self._cross_validate(X, y, cv_folds)

            # Final fit on full dataset
            self.model.fit(X, y)

            # SHAP explainer (fitted on XGBoost sub-estimator)
            try:
                xgb_fitted = self.model.estimator.estimators_[0]
                self.shap_explainer = shap.TreeExplainer(xgb_fitted)
            except Exception as exc:
                logger.warning("SHAP explainer init failed: %s", exc)

            # Log metrics to MLflow
            for metric_name, value in cv_metrics.items():
                mlflow.log_metric(metric_name, value)

            # Save and hash the model artifact
            self.model_hash = self._compute_model_hash(self.model)
            mlflow.log_param("model_hash", self.model_hash)

            # Log model to MLflow registry
            mlflow.sklearn.log_model(
                self.model,
                artifact_path="sti_risk_classifier",
                registered_model_name="sti_risk_classifier",
            )

            # Threshold check
            cv_metrics["passed_thresholds"] = self._check_thresholds(cv_metrics)
            mlflow.log_param(
                "passed_thresholds", cv_metrics["passed_thresholds"]
            )
            mlflow.set_tag(
                "threshold_status",
                "PASS" if cv_metrics["passed_thresholds"] else "FAIL",
            )

        return cv_metrics

    def _cross_validate(
        self, X: pd.DataFrame, y: pd.Series, n_folds: int
    ) -> Dict:
        """
        Stratified k-fold evaluation. Returns mean metrics across folds.
        """
        skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
        lb = LabelBinarizer().fit(STI_CLASSES)

        fold_auc, fold_f1, fold_precision, fold_recall = [], [], [], []

        for fold, (train_idx, val_idx) in enumerate(skf.split(X, y)):
            X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]

            xgb = XGBClassifier(**self.xgb_params)
            rf = RandomForestClassifier(**self.rf_params)
            fold_model = CalibratedClassifierCV(
                VotingClassifier(
                    estimators=[("xgb", xgb), ("rf", rf)],
                    voting="soft",
                ),
                method="isotonic",
                cv=3,
            )
            fold_model.fit(X_tr, y_tr)

            y_prob = fold_model.predict_proba(X_val)
            y_pred = fold_model.predict(X_val)
            y_val_bin = lb.transform(y_val)

            # Handle classes not present in validation fold
            classes_in_val = [c for c in STI_CLASSES if c in y_val.values]
            class_indices = [STI_CLASSES.index(c) for c in classes_in_val]

            auc = roc_auc_score(
                y_val_bin[:, class_indices],
                y_prob[:, class_indices],
                multi_class="ovr",
                average="macro",
            )
            f1 = f1_score(y_val, y_pred, average="macro", zero_division=0)
            prec = precision_score(y_val, y_pred, average="macro", zero_division=0)
            rec = recall_score(y_val, y_pred, average="macro", zero_division=0)

            fold_auc.append(auc)
            fold_f1.append(f1)
            fold_precision.append(prec)
            fold_recall.append(rec)

            logger.info("Fold %d — AUC=%.4f  F1=%.4f", fold + 1, auc, f1)

        return {
            "auc_roc_mean": float(np.mean(fold_auc)),
            "auc_roc_std": float(np.std(fold_auc)),
            "f1_mean": float(np.mean(fold_f1)),
            "f1_std": float(np.std(fold_f1)),
            "precision_mean": float(np.mean(fold_precision)),
            "recall_mean": float(np.mean(fold_recall)),
        }

    def _check_thresholds(self, metrics: Dict) -> bool:
        """AUC-ROC ≥ 0.85 and F1 ≥ 0.75 required for deployment (§4.1.1)."""
        auc_ok = metrics.get("auc_roc_mean", 0) >= AUC_ROC_THRESHOLD
        f1_ok = metrics.get("f1_mean", 0) >= F1_THRESHOLD
        if not auc_ok:
            logger.warning(
                "AUC-ROC %.4f below threshold %.2f",
                metrics["auc_roc_mean"], AUC_ROC_THRESHOLD,
            )
        if not f1_ok:
            logger.warning(
                "F1 %.4f below threshold %.2f",
                metrics["f1_mean"], F1_THRESHOLD,
            )
        return auc_ok and f1_ok

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict(self, record: Dict) -> Dict:
        """
        Run inference on a single preprocessed record.
        Returns per-class probability dict, overall risk level,
        and top-3 SHAP feature contributions.
        """
        if self.model is None:
            raise RuntimeError("Model not loaded. Call train() or load().")

        X, _ = build_feature_matrix([record])
        proba = self.model.predict_proba(X)[0]
        classes = self.model.classes_

        probabilities = {cls: round(float(p), 4) for cls, p in zip(classes, proba)}

        # Risk level based on highest non-"none" probability
        non_none = {k: v for k, v in probabilities.items() if k != "none"}
        max_prob = max(non_none.values()) if non_none else 0.0
        risk_level = (
            "critical" if max_prob > 0.7
            else "high" if max_prob > 0.5
            else "moderate" if max_prob > 0.3
            else "low"
        )

        # Clinical review flag (§3.2)
        clinical_review_required = max_prob > 0.7

        # SHAP top-3 features
        shap_values = self._explain(X)

        return {
            "sti_probabilities": probabilities,
            "risk_level": risk_level,
            "clinical_review_required": clinical_review_required,
            "top_features": shap_values,
            "model_hash": self.model_hash,
            "mlflow_run_id": self.mlflow_run_id,
        }

    def predict_batch(self, records: List[Dict]) -> List[Dict]:
        """Batch inference — returns list of prediction dicts."""
        X, _ = build_feature_matrix(records)
        probas = self.model.predict_proba(X)
        classes = self.model.classes_

        results = []
        for i, proba in enumerate(probas):
            probabilities = {cls: round(float(p), 4) for cls, p in zip(classes, proba)}
            non_none = {k: v for k, v in probabilities.items() if k != "none"}
            max_prob = max(non_none.values()) if non_none else 0.0
            results.append({
                "sti_probabilities": probabilities,
                "risk_level": (
                    "critical" if max_prob > 0.7
                    else "high" if max_prob > 0.5
                    else "moderate" if max_prob > 0.3
                    else "low"
                ),
                "clinical_review_required": max_prob > 0.7,
                "model_hash": self.model_hash,
            })
        return results

    # ------------------------------------------------------------------
    # Explainability (SHAP)
    # ------------------------------------------------------------------

    def _explain(self, X: pd.DataFrame, top_n: int = 3) -> List[Dict]:
        """Return top-N SHAP feature contributions for the prediction."""
        if self.shap_explainer is None:
            return []
        try:
            shap_vals = self.shap_explainer.shap_values(X)
            # Sum absolute SHAP across classes for feature importance
            if isinstance(shap_vals, list):
                mean_abs = np.mean([np.abs(sv) for sv in shap_vals], axis=0)[0]
            else:
                mean_abs = np.abs(shap_vals)[0]

            top_indices = mean_abs.argsort()[::-1][:top_n]
            return [
                {
                    "feature": self.feature_cols[i],
                    "shap_value": round(float(mean_abs[i]), 4),
                }
                for i in top_indices
            ]
        except Exception as exc:
            logger.warning("SHAP explanation failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> str:
        """Serialise model to disk; returns SHA-256 hash."""
        with open(path, "wb") as f:
            pickle.dump(
                {
                    "model": self.model,
                    "feature_cols": self.feature_cols,
                    "classes": self.classes_,
                    "mlflow_run_id": self.mlflow_run_id,
                },
                f,
            )
        return self._compute_model_hash_from_path(path)

    @classmethod
    def load(cls, path: str, mlflow_run_id: Optional[str] = None) -> "STIRiskClassifier":
        """Load a serialised model from disk."""
        with open(path, "rb") as f:
            data = pickle.load(f)
        instance = cls()
        instance.model = data["model"]
        instance.feature_cols = data["feature_cols"]
        instance.classes_ = data["classes"]
        instance.mlflow_run_id = data.get("mlflow_run_id") or mlflow_run_id
        instance.model_hash = instance._compute_model_hash(instance.model)
        return instance

    @classmethod
    def load_from_mlflow(cls, model_name: str, stage: str = "Production") -> "STIRiskClassifier":
        """Load the production model version from the MLflow registry."""
        model_uri = f"models:/{model_name}/{stage}"
        loaded = mlflow.sklearn.load_model(model_uri)
        instance = cls()
        instance.model = loaded
        instance.model_hash = instance._compute_model_hash(loaded)
        return instance

    # ------------------------------------------------------------------
    # Drift Detection
    # ------------------------------------------------------------------

    def compute_psi(
        self,
        reference_X: pd.DataFrame,
        current_X: pd.DataFrame,
        bins: int = 10,
    ) -> Dict[str, float]:
        """
        Compute Population Stability Index per feature.
        PSI > 0.2 triggers a drift alert (§4.3).
        """
        psi_scores = {}
        for col in self.feature_cols:
            if col not in reference_X.columns or col not in current_X.columns:
                continue
            ref = reference_X[col].dropna()
            cur = current_X[col].dropna()
            if ref.nunique() < 2:
                continue
            min_val = min(ref.min(), cur.min())
            max_val = max(ref.max(), cur.max())
            bin_edges = np.linspace(min_val, max_val, bins + 1)
            ref_counts, _ = np.histogram(ref, bins=bin_edges)
            cur_counts, _ = np.histogram(cur, bins=bin_edges)
            # Smoothing to avoid division by zero
            ref_pct = (ref_counts + 1e-6) / (len(ref) + 1e-6 * bins)
            cur_pct = (cur_counts + 1e-6) / (len(cur) + 1e-6 * bins)
            psi = float(np.sum((ref_pct - cur_pct) * np.log(ref_pct / cur_pct)))
            psi_scores[col] = round(psi, 6)
        return psi_scores

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_model_hash(model) -> str:
        return hashlib.sha256(pickle.dumps(model)).hexdigest()

    @staticmethod
    def _compute_model_hash_from_path(path: str) -> str:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()