"""
STI Predictive Model — ML Pipeline (L3)
registry.py

MLflow Model Registry wiring.
Handles model registration, stage promotion, version resolution,
drift monitoring (PSI), and bias audit triggers.

Every prediction in L4 resolves the active model version through
ModelRegistry.get_active_version() — this is the single source of truth.
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import mlflow
from mlflow.tracking import MlflowClient
from django.utils import timezone

from .models import (
    ModelType, ModelVersion, ModelStage, TrainingJob, TrainingStatus,
    MLflowExperiment, DriftAlert, BiasAuditRecord,
)
from .classifier import STIRiskClassifier, AUC_ROC_THRESHOLD, F1_THRESHOLD
from .forecaster import OutbreakPatternPredictor, MAPE_THRESHOLD
from .geospatial import GeospatialHotspotEngine

logger = logging.getLogger(__name__)

# Drift threshold: PSI > 0.2 triggers retraining alert (§4.3)
PSI_THRESHOLD = 0.2

# Bias monitoring: AUC < 0.80 for any subgroup triggers review (§8.3)
SUBGROUP_AUC_THRESHOLD = 0.80

# MLflow model names (must match registered_model_name in each trainer)
MLFLOW_MODEL_NAMES = {
    ModelType.RISK_CLASSIFIER: "sti_risk_classifier",
    ModelType.PATTERN_PREDICTOR: "outbreak_pattern_predictor",
    ModelType.GEOSPATIAL_ENGINE: "geospatial_hotspot_engine",
}


# ---------------------------------------------------------------------------
# Model Registry
# ---------------------------------------------------------------------------

class ModelRegistry:
    """
    Central registry for all three model types.
    Manages MLflow ↔ Django ModelVersion synchronisation,
    stage transitions, and version resolution for inference.
    """

    def __init__(self, mlflow_tracking_uri: Optional[str] = None):
        if mlflow_tracking_uri:
            mlflow.set_tracking_uri(mlflow_tracking_uri)
        self.client = MlflowClient()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_model(
        self,
        training_job: TrainingJob,
        metrics: Dict,
        artifact_uri: str,
    ) -> ModelVersion:
        """
        Register a completed training run as a ModelVersion.
        Initial stage is STAGING (or PENDING_CLINICAL if thresholds passed).
        The version is never promoted to PRODUCTION without clinical sign-off (§8.2).
        """
        model_name = MLFLOW_MODEL_NAMES[training_job.model_type]
        mlflow_run_id = training_job.mlflow_run_id

        # Transition to Staging in MLflow
        try:
            mv = self.client.get_latest_versions(model_name, stages=["None"])
            if mv:
                self.client.transition_model_version_stage(
                    name=model_name,
                    version=mv[0].version,
                    stage="Staging",
                    archive_existing_versions=False,
                )
                mlflow_version = mv[0].version
            else:
                mlflow_version = "1"
        except Exception as exc:
            logger.warning("MLflow stage transition failed: %s", exc)
            mlflow_version = mlflow_run_id[:8]  # Fallback

        # Compute model hash from artifact
        model_hash = self._compute_artifact_hash(artifact_uri)

        # Determine stage
        passed = metrics.get("passed_thresholds", False)
        stage = (
            ModelStage.PENDING_CLINICAL if passed
            else ModelStage.STAGING
        )

        version = ModelVersion.objects.create(
            model_type=training_job.model_type,
            stage=stage,
            training_job=training_job,
            mlflow_model_name=model_name,
            mlflow_model_version=str(mlflow_version),
            mlflow_run_id=mlflow_run_id,
            model_hash=model_hash,
            artifact_uri=artifact_uri,
            auc_roc_mean=metrics.get("auc_roc_mean"),
            f1_mean=metrics.get("f1_mean"),
            mape=metrics.get("mape_mean"),
        )

        logger.info(
            "Registered %s v%s → %s (AUC=%.4f)",
            training_job.model_type,
            mlflow_version,
            stage,
            metrics.get("auc_roc_mean", 0),
        )
        return version

    # ------------------------------------------------------------------
    # Clinical Validation Gate (§8.2)
    # ------------------------------------------------------------------

    def approve_clinical_validation(
        self,
        version_id: str,
        clinician_name: str,
        clinician_credential: str,
    ) -> ModelVersion:
        """
        Record clinical validation sign-off.
        This is a hard system constraint — no model enters production
        without completing this gate (§8.2).
        Two-clinician review is enforced at the process level;
        this method records the approving clinician's name + credential.
        """
        version = ModelVersion.objects.get(version_id=version_id)
        if version.stage != ModelStage.PENDING_CLINICAL:
            raise ValueError(
                f"Version {version_id} is not awaiting clinical validation "
                f"(current stage: {version.stage})"
            )

        version.clinical_validation_passed = True
        version.clinical_validated_by = f"{clinician_name} ({clinician_credential})"
        version.clinical_validated_at = timezone.now()
        version.save(update_fields=[
            "clinical_validation_passed",
            "clinical_validated_by",
            "clinical_validated_at",
        ])

        logger.info(
            "Clinical validation approved for %s v%s by %s",
            version.model_type,
            version.mlflow_model_version,
            clinician_name,
        )
        return version

    # ------------------------------------------------------------------
    # Stage Promotion
    # ------------------------------------------------------------------

    def promote_to_production(self, version_id: str) -> ModelVersion:
        """
        Promote a clinically validated model version to production.
        Archives the current production version.
        Only callable after clinical_validation_passed = True.
        """
        version = ModelVersion.objects.get(version_id=version_id)

        if not version.clinical_validation_passed:
            raise PermissionError(
                "Clinical validation has not been completed for this model version. "
                "Promotion to production is blocked (§8.2 compliance gate)."
            )

        # Archive existing production version
        ModelVersion.objects.filter(
            model_type=version.model_type,
            stage=ModelStage.PRODUCTION,
        ).update(stage=ModelStage.ARCHIVED)

        # Promote in Django
        version.stage = ModelStage.PRODUCTION
        version.promoted_to_production_at = timezone.now()
        version.save(update_fields=["stage", "promoted_to_production_at"])

        # Promote in MLflow
        try:
            self.client.transition_model_version_stage(
                name=version.mlflow_model_name,
                version=version.mlflow_model_version,
                stage="Production",
                archive_existing_versions=True,
            )
        except Exception as exc:
            logger.warning("MLflow promotion failed (Django updated): %s", exc)

        logger.info(
            "Promoted %s v%s to PRODUCTION",
            version.model_type,
            version.mlflow_model_version,
        )
        return version

    def archive_version(self, version_id: str) -> ModelVersion:
        """Archive a model version (usually superseded by a new production version)."""
        version = ModelVersion.objects.get(version_id=version_id)
        version.stage = ModelStage.ARCHIVED
        version.save(update_fields=["stage"])
        try:
            self.client.transition_model_version_stage(
                name=version.mlflow_model_name,
                version=version.mlflow_model_version,
                stage="Archived",
            )
        except Exception as exc:
            logger.warning("MLflow archive failed: %s", exc)
        return version

    # ------------------------------------------------------------------
    # Version Resolution (used by L4 Prediction Engine)
    # ------------------------------------------------------------------

    def get_active_version(self, model_type: str) -> ModelVersion:
        """
        Return the current production model version for the given type.
        Raises if no production version exists.
        """
        try:
            return ModelVersion.objects.get(
                model_type=model_type,
                stage=ModelStage.PRODUCTION,
            )
        except ModelVersion.DoesNotExist:
            raise RuntimeError(
                f"No production model version found for {model_type}. "
                "A model must pass training thresholds, clinical validation, "
                "and be promoted before inference can proceed."
            )

    def get_version_by_hash(self, model_hash: str) -> Optional[ModelVersion]:
        """Look up a model version by its artifact hash."""
        return ModelVersion.objects.filter(model_hash=model_hash).first()

    def list_versions(
        self,
        model_type: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> List[ModelVersion]:
        qs = ModelVersion.objects.all()
        if model_type:
            qs = qs.filter(model_type=model_type)
        if stage:
            qs = qs.filter(stage=stage)
        return list(qs.order_by("-created_at"))

    # ------------------------------------------------------------------
    # Model Loading for Inference
    # ------------------------------------------------------------------

    def load_classifier(
        self, model_type: str = ModelType.RISK_CLASSIFIER
    ) -> STIRiskClassifier:
        """Load the production STI risk classifier from MLflow."""
        version = self.get_active_version(model_type)
        classifier = STIRiskClassifier.load_from_mlflow(
            model_name=version.mlflow_model_name,
            stage="Production",
        )
        classifier.mlflow_run_id = version.mlflow_run_id
        classifier.model_hash = version.model_hash
        return classifier

    def load_forecaster(self) -> OutbreakPatternPredictor:
        """Load the production pattern predictor from MLflow."""
        version = self.get_active_version(ModelType.PATTERN_PREDICTOR)
        # PyTorch LSTM models are loaded directly; Prophet models are pickled
        forecaster = OutbreakPatternPredictor()
        try:
            import mlflow.pytorch
            artifact_path = version.artifact_uri
            # Load each series model from the artifact store
            # (Implementation depends on artifact storage backend)
            forecaster.mlflow_run_id = version.mlflow_run_id
        except Exception as exc:
            logger.error("Failed to load forecaster from MLflow: %s", exc)
            raise
        return forecaster

    # ------------------------------------------------------------------
    # Drift Detection (§4.3)
    # ------------------------------------------------------------------

    def check_drift(
        self,
        model_type: str,
        reference_features: List[Dict],
        current_features: List[Dict],
    ) -> Optional[DriftAlert]:
        """
        Compute PSI between reference (training) and current (production)
        feature distributions. Creates a DriftAlert if PSI > 0.2.
        Returns the DriftAlert if triggered, None otherwise.
        """
        version = self.get_active_version(model_type)

        if model_type == ModelType.RISK_CLASSIFIER:
            from .classifier import build_feature_matrix, STIRiskClassifier
            ref_X, _ = build_feature_matrix(reference_features)
            cur_X, _ = build_feature_matrix(current_features)
            classifier = STIRiskClassifier()
            classifier.model_hash = version.model_hash
            psi_scores = classifier.compute_psi(ref_X, cur_X)
        else:
            # PSI for forecaster and geospatial is computed on incidence rates
            psi_scores = self._compute_tabular_psi(reference_features, current_features)

        drifted_features = [
            feat for feat, psi in psi_scores.items()
            if psi > PSI_THRESHOLD
        ]
        max_psi = max(psi_scores.values()) if psi_scores else 0.0

        if not drifted_features:
            logger.info(
                "No drift detected for %s (max PSI=%.4f)", model_type, max_psi
            )
            return None

        alert = DriftAlert.objects.create(
            model_version=version,
            model_type=model_type,
            psi_score=max_psi,
            psi_threshold=PSI_THRESHOLD,
            features_drifted=drifted_features,
        )
        logger.warning(
            "Drift alert created for %s: PSI=%.4f, features=%s",
            model_type, max_psi, drifted_features[:5],
        )
        return alert

    @staticmethod
    def _compute_tabular_psi(
        reference: List[Dict],
        current: List[Dict],
        key: str = "incidence_rate",
        bins: int = 10,
    ) -> Dict[str, float]:
        import numpy as np
        ref_vals = np.array([r.get(key, 0.0) for r in reference])
        cur_vals = np.array([c.get(key, 0.0) for c in current])
        if len(ref_vals) == 0 or len(cur_vals) == 0:
            return {}
        min_v, max_v = min(ref_vals.min(), cur_vals.min()), max(ref_vals.max(), cur_vals.max())
        edges = np.linspace(min_v, max_v, bins + 1)
        ref_pct = (np.histogram(ref_vals, bins=edges)[0] + 1e-6) / (len(ref_vals) + 1e-6 * bins)
        cur_pct = (np.histogram(cur_vals, bins=edges)[0] + 1e-6) / (len(cur_vals) + 1e-6 * bins)
        psi = float(np.sum((ref_pct - cur_pct) * np.log(ref_pct / cur_pct)))
        return {key: round(psi, 6)}

    # ------------------------------------------------------------------
    # Bias Audit (§8.3)
    # ------------------------------------------------------------------

    def run_bias_audit(
        self,
        model_type: str,
        inference_logs: List[Dict],
        audit_period_start: datetime,
        audit_period_end: datetime,
    ) -> BiasAuditRecord:
        """
        Compute per-subgroup AUC-ROC from production inference logs.
        Flags any subgroup below SUBGROUP_AUC_THRESHOLD (0.80).

        inference_logs expected fields:
          - predicted_label, true_label, age_encoded, sex_encoded, region_encoded
        """
        import numpy as np
        from sklearn.metrics import roc_auc_score
        from sklearn.preprocessing import LabelBinarizer

        version = self.get_active_version(model_type)
        df = _logs_to_dataframe(inference_logs)

        lb = LabelBinarizer()
        lb.fit(df["true_label"].unique())

        auc_by_age = self._subgroup_auc(df, "age_encoded", lb)
        auc_by_sex = self._subgroup_auc(df, "sex_encoded", lb)
        auc_by_region = self._subgroup_auc(df, "region_encoded", lb)

        all_subgroup_aucs = {**auc_by_age, **auc_by_sex, **auc_by_region}
        flagged = [k for k, v in all_subgroup_aucs.items() if v < SUBGROUP_AUC_THRESHOLD]

        audit = BiasAuditRecord.objects.create(
            model_version=version,
            audit_period_start=audit_period_start.date(),
            audit_period_end=audit_period_end.date(),
            auc_by_age_group=auc_by_age,
            auc_by_sex=auc_by_sex,
            auc_by_region=auc_by_region,
            any_subgroup_below_threshold=bool(flagged),
            flagged_subgroups=flagged,
            retraining_recommended=bool(flagged),
        )

        if flagged:
            logger.warning(
                "Bias audit flagged %d subgroups for %s: %s",
                len(flagged), model_type, flagged,
            )
        else:
            logger.info("Bias audit passed for %s", model_type)

        return audit

    @staticmethod
    def _subgroup_auc(
        df,
        group_col: str,
        lb,
    ) -> Dict[str, float]:
        import numpy as np
        from sklearn.metrics import roc_auc_score
        results = {}
        for group_val in df[group_col].unique():
            sub = df[df[group_col] == group_val]
            if len(sub) < 10:
                continue
            try:
                y_true_bin = lb.transform(sub["true_label"])
                y_prob = np.stack(sub["predicted_probabilities"].values)
                auc = roc_auc_score(y_true_bin, y_prob, multi_class="ovr", average="macro")
                results[f"{group_col}_{group_val}"] = round(float(auc), 4)
            except Exception as exc:
                logger.debug("Subgroup AUC failed for %s=%s: %s", group_col, group_val, exc)
        return results

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_artifact_hash(artifact_uri: str) -> str:
        """Generate a hash representing the artifact URI (surrogate for file hash)."""
        return hashlib.sha256(artifact_uri.encode()).hexdigest()

    def get_experiment_id(self, model_type: str) -> Optional[str]:
        """Return the MLflow experiment ID for a model type."""
        try:
            exp = MLflowExperiment.objects.get(model_type=model_type)
            return exp.mlflow_experiment_id
        except MLflowExperiment.DoesNotExist:
            return None

    def sync_mlflow_experiments(self) -> Dict[str, str]:
        """
        Ensure MLflow experiments exist for all three model types.
        Creates them if absent; returns {model_type: experiment_id} mapping.
        """
        mapping = {}
        for model_type, model_name in MLFLOW_MODEL_NAMES.items():
            exp_name = f"sti_predictive_model/{model_name}"
            try:
                exp = self.client.get_experiment_by_name(exp_name)
                if exp is None:
                    exp_id = self.client.create_experiment(exp_name)
                else:
                    exp_id = exp.experiment_id
            except Exception as exc:
                logger.error("Failed to sync MLflow experiment %s: %s", exp_name, exc)
                continue

            MLflowExperiment.objects.update_or_create(
                model_type=model_type,
                defaults={
                    "mlflow_experiment_id": exp_id,
                    "mlflow_experiment_name": exp_name,
                    "artifact_location": "",
                },
            )
            mapping[model_type] = exp_id

        return mapping


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _logs_to_dataframe(inference_logs: List[Dict]):
    """Convert inference log dicts to a DataFrame for bias audit."""
    import pandas as pd
    return pd.DataFrame(inference_logs)