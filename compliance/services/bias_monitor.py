import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from datetime import date
from collections import defaultdict

from ..models import BiasAuditReport

class BiasMonitor:
    """
    Demographic parity and calibration monitoring.
    Spec Section 8.3: AUC-ROC drops below 0.80 for any subgroup = retraining flag.
    """
    
    MIN_SAMPLES = 50  # Minimum samples for reliable subgroup metrics
    AUC_THRESHOLD = 0.80
    F1_THRESHOLD = 0.75
    
    def __init__(self, model_version: str, model_type: str):
        self.model_version = model_version
        self.model_type = model_type
        self.results = {}
        self.violations = []
    
    def evaluate_subgroup(self, subgroup_name: str, 
                          y_true: np.ndarray, 
                          y_pred: np.ndarray,
                          y_proba: np.ndarray) -> Dict:
        """Evaluate model performance for a demographic subgroup"""
        from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score
        
        n_samples = len(y_true)
        if n_samples < self.MIN_SAMPLES:
            return {
                "subgroup_name": subgroup_name,
                "sample_count": n_samples,
                "insufficient_data": True
            }
        
        # Handle multi-class for AUC
        try:
            auc = roc_auc_score(y_true, y_proba, multi_class="ovr", average="macro")
        except ValueError:
            auc = roc_auc_score(y_true, y_proba[:, 1]) if y_proba.ndim > 1 else 0.5
        
        f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
        precision = precision_score(y_true, y_pred, average="macro", zero_division=0)
        recall = recall_score(y_true, y_pred, average="macro", zero_division=0)
        
        passes = auc >= self.AUC_THRESHOLD and f1 >= self.F1_THRESHOLD
        
        result = {
            "subgroup_name": subgroup_name,
            "sample_count": n_samples,
            "auc_roc": round(auc, 4),
            "f1_score": round(f1, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "passes_threshold": passes
        }
        
        if not passes:
            self.violations.append({
                "subgroup": subgroup_name,
                "auc_roc": round(auc, 4),
                "f1": round(f1, 4),
                "threshold_auc": self.AUC_THRESHOLD,
                "threshold_f1": self.F1_THRESHOLD
            })
        
        self.results[subgroup_name] = result
        return result
    
    def run_full_audit(self, predictions_df: pd.DataFrame) -> BiasAuditReport:
        """
        Run complete bias audit across all demographic subgroups.
        """
        # Define subgroups to evaluate
        subgroup_columns = {
            "age_13_17": predictions_df["age"].between(13, 17),
            "age_18_24": predictions_df["age"].between(18, 24),
            "age_25_34": predictions_df["age"].between(25, 34),
            "age_35_44": predictions_df["age"].between(35, 44),
            "age_45_plus": predictions_df["age"] >= 45,
            "sex_male": predictions_df["sex"] == "male",
            "sex_female": predictions_df["sex"] == "female",
            "sex_other": predictions_df["sex"] == "other",
            "region_nairobi": predictions_df["region"] == "Nairobi",
            "region_mombasa": predictions_df["region"] == "Mombasa",
            "region_kisumu": predictions_df["region"] == "Kisumu",
            "region_other": ~predictions_df["region"].isin(["Nairobi", "Mombasa", "Kisumu"])
        }
        
        for subgroup_name, mask in subgroup_columns.items():
            subgroup_data = predictions_df[mask]
            if len(subgroup_data) > 0:
                self.evaluate_subgroup(
                    subgroup_name=subgroup_name,
                    y_true=subgroup_data["true_label"].values,
                    y_pred=subgroup_data["predicted_label"].values,
                    y_proba=subgroup_data["predicted_probability"].values
                )
        
        # Calibration check
        calibration_results = self._check_calibration(predictions_df)
        
        # Determine overall pass
        passes = len(self.violations) == 0
        
        # Recommended actions
        actions = []
        if not passes:
            actions.append(f"Retrain model with augmented data for underperforming subgroups: {[v['subgroup'] for v in self.violations]}")
            actions.append("Review feature engineering for demographic-specific biases")
            actions.append("Consider subgroup-specific model thresholds")
        
        # Save report
        report = BiasAuditReport.objects.create(
            period_start=date.today() - pd.Timedelta(days=90),
            period_end=date.today(),
            model_version=self.model_version,
            model_type=self.model_type,
            subgroup_results=self.results,
            violations_found=self.violations,
            calibration_by_subgroup=calibration_results,
            passes_bias_audit=passes,
            recommended_actions=actions
        )
        
        return report
    
    def _check_calibration(self, predictions_df: pd.DataFrame) -> Dict:
        """Check probability calibration per subgroup"""
        from sklearn.calibration import calibration_curve
        
        results = {}
        for subgroup in predictions_df["subgroup"].unique():
            mask = predictions_df["subgroup"] == subgroup
            subgroup_data = predictions_df[mask]
            
            prob_true, prob_pred = calibration_curve(
                subgroup_data["true_label"].values,
                subgroup_data["predicted_probability"].values,
                n_bins=10
            )
            
            results[subgroup] = {
                "calibration_error": round(np.mean(np.abs(prob_true - prob_pred)), 4),
                "bins": len(prob_true)
            }
        
        return results