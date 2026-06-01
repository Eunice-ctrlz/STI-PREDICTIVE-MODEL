import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from datetime import datetime
from scipy.stats import chi2_contingency

from ..models import DriftDetectionResult

class DriftDetector:
    """
    Population Stability Index (PSI) monitoring.
    Spec Section 4.3: PSI computed weekly, threshold 0.2 triggers retraining alert.
    """
    
    PSI_THRESHOLD = 0.2
    CRITICAL_THRESHOLD = 0.3
    
    def __init__(self, model_version: str):
        self.model_version = model_version
        self.drifted_features = []
    
    def calculate_psi(self, expected: np.ndarray, actual: np.ndarray, 
                     bins: int = 10) -> float:
        """
        Calculate Population Stability Index.
        PSI = sum((Actual% - Expected%) * ln(Actual% / Expected%))
        """
        # Create bins from expected distribution
        breakpoints = np.percentile(expected, np.linspace(0, 100, bins + 1))
        breakpoints[0] = -np.inf
        breakpoints[-1] = np.inf
        
        # Bin both distributions
        expected_counts, _ = np.histogram(expected, breakpoints)
        actual_counts, _ = np.histogram(actual, breakpoints)
        
        # Convert to percentages
        expected_pct = expected_counts / len(expected)
        actual_pct = actual_counts / len(actual)
        
        # Avoid division by zero
        expected_pct = np.clip(expected_pct, 0.0001, 1.0)
        actual_pct = np.clip(actual_pct, 0.0001, 1.0)
        
        # Calculate PSI
        psi = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
        
        return float(psi)
    
    def check_feature(self, feature_name: str,
                      training_data: np.ndarray,
                      current_data: np.ndarray) -> Dict:
        """Check PSI for a single feature"""
        psi = self.calculate_psi(training_data, current_data)
        
        is_drifted = psi > self.PSI_THRESHOLD
        severity = "low"
        if psi > self.CRITICAL_THRESHOLD:
            severity = "critical"
        elif psi > self.PSI_THRESHOLD:
            severity = "high"
        elif psi > 0.1:
            severity = "moderate"
        
        result = {
            "feature_name": feature_name,
            "psi_score": round(psi, 4),
            "threshold": self.PSI_THRESHOLD,
            "is_drift_detected": is_drifted,
            "severity": severity,
            "training_distribution": {
                "mean": round(float(np.mean(training_data)), 4),
                "std": round(float(np.std(training_data)), 4),
                "min": round(float(np.min(training_data)), 4),
                "max": round(float(np.max(training_data)), 4)
            },
            "current_distribution": {
                "mean": round(float(np.mean(current_data)), 4),
                "std": round(float(np.std(current_data)), 4),
                "min": round(float(np.min(current_data)), 4),
                "max": round(float(np.max(current_data)), 4)
            }
        }
        
        if is_drifted:
            self.drifted_features.append(result)
        
        return result
    
    def run_full_check(self, training_df: pd.DataFrame,
                       current_df: pd.DataFrame,
                       feature_names: List[str]) -> List[DriftDetectionResult]:
        """Run PSI check on all features"""
        results = []
        
        for feature in feature_names:
            if feature in training_df.columns and feature in current_df.columns:
                check = self.check_feature(
                    feature_name=feature,
                    training_data=training_df[feature].dropna().values,
                    current_data=current_df[feature].dropna().values
                )
                
                # Save to database
                result = DriftDetectionResult.objects.create(
                    model_version=self.model_version,
                    feature_name=feature,
                    psi_score=check["psi_score"],
                    is_drift_detected=check["is_drift_detected"],
                    severity=check["severity"],
                    training_distribution=check["training_distribution"],
                    current_distribution=check["current_distribution"]
                )
                results.append(result)
        
        return results
    
    def should_trigger_retraining(self) -> Tuple[bool, List[str]]:
        """Determine if retraining should be triggered"""
        critical_features = [f["feature_name"] for f in self.drifted_features 
                            if f["severity"] in ["high", "critical"]]
        return len(critical_features) > 0, critical_features