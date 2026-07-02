"""
ML Model wrapper for STI prediction.
Supports scikit-learn, XGBoost, and ONNX models.
"""
import os
import json
import pickle
import joblib
import numpy as np
from typing import Dict, List, Tuple, Optional
from django.conf import settings


class STIPredictor:
    """
    Unified predictor for STI risk assessment.
    Loads model artifacts from MEDIA_ROOT/models/
    """
    
    FEATURE_ORDER = [
        'age', 'gender_male', 'gender_female', 'gender_other',
        'num_partners_12m', 'num_partners_lifetime',
        'condom_use_freq', 'substance_use',
        'prior_sti_history', 'hiv_positive', 'hiv_unknown',
        'symptoms_present', 'marital_single', 'marital_married',
        'marital_divorced', 'marital_cohabiting'
    ]
    
    def __init__(self, model_name: str = "sti_risk_v1", sti_type: str = "general"):
        self.model_name = model_name
        self.sti_type = sti_type
        self.model = None
        self.scaler = None
        self.feature_names = self.FEATURE_ORDER
        self._load_model()
    
    def _get_model_path(self) -> str:
        return os.path.join(settings.MEDIA_ROOT, 'models', self.model_name)
    
    def _load_model(self):
        """Load model, scaler, and metadata from disk."""
        model_dir = self._get_model_path()
        
        if not os.path.exists(model_dir):
            # Fallback: use a simple heuristic model if no trained model exists
            self.model = None
            return
        
        # Try joblib first, then pickle
        model_path = os.path.join(model_dir, 'model.joblib')
        if not os.path.exists(model_path):
            model_path = os.path.join(model_dir, 'model.pkl')
        
        scaler_path = os.path.join(model_dir, 'scaler.joblib')
        meta_path = os.path.join(model_dir, 'metadata.json')
        
        if os.path.exists(model_path):
            try:
                self.model = joblib.load(model_path)
            except Exception:
                with open(model_path, 'rb') as f:
                    self.model = pickle.load(f)
        
        if os.path.exists(scaler_path):
            self.scaler = joblib.load(scaler_path)
        
        if os.path.exists(meta_path):
            with open(meta_path, 'r') as f:
                self.metadata = json.load(f)
                if 'feature_names' in self.metadata:
                    self.feature_names = self.metadata['feature_names']
        else:
            self.metadata = {}
    
    def _preprocess_features(self, patient_data: Dict) -> np.ndarray:
        """Convert patient dict to model feature vector."""
        from patients.models import Patient
        
        # Handle Patient object or dict
        if isinstance(patient_data, Patient):
            data = {
                'age': patient_data.age,
                'num_partners_12m': patient_data.number_of_partners_12m,
                'num_partners_lifetime': patient_data.number_of_partners_lifetime,
                'condom_use_freq': patient_data.condom_use_frequency,
                'substance_use': 1 if patient_data.substance_use else 0,
                'prior_sti_history': 1 if patient_data.prior_sti_history else 0,
                'symptoms_present': 1 if patient_data.symptoms_present else 0,
            }
            # Gender one-hot
            g = patient_data.gender
            data['gender_male'] = 1 if g == 'M' else 0
            data['gender_female'] = 1 if g == 'F' else 0
            data['gender_other'] = 1 if g in ('O', 'U') else 0
            
            # HIV status
            data['hiv_positive'] = 1 if patient_data.hiv_status == 'positive' else 0
            data['hiv_unknown'] = 1 if patient_data.hiv_status == 'unknown' else 0
            
            # Marital status
            m = patient_data.marital_status
            data['marital_single'] = 1 if m == 'single' else 0
            data['marital_married'] = 1 if m == 'married' else 0
            data['marital_divorced'] = 1 if m == 'divorced' else 0
            data['marital_cohabiting'] = 1 if m == 'cohabiting' else 0
        else:
            data = patient_data
        
        # Build feature vector in correct order
        features = []
        for feat in self.feature_names:
            features.append(float(data.get(feat, 0)))
        
        X = np.array(features).reshape(1, -1)
        
        if self.scaler:
            X = self.scaler.transform(X)
        
        return X
    
    def predict(self, patient_data) -> Dict:
        """
        Run prediction and return structured result.
        """
        X = self._preprocess_features(patient_data)
        
        if self.model is None:
            # Fallback heuristic model
            return self._heuristic_predict(X, patient_data)
        
        # Get prediction probability
        if hasattr(self.model, 'predict_proba'):
            proba = self.model.predict_proba(X)[0][1]  # probability of positive class
        else:
            proba = float(self.model.predict(X)[0])
        
        # Clamp to [0, 1]
        proba = max(0.0, min(1.0, proba))
        
        # Determine risk level
        if proba < 0.25:
            risk_level = 'low'
        elif proba < 0.50:
            risk_level = 'moderate'
        elif proba < 0.75:
            risk_level = 'high'
        else:
            risk_level = 'very_high'
        
        # Feature importance (if available)
        top_factors = {}
        if hasattr(self.model, 'feature_importances_'):
            importances = self.model.feature_importances_
            for i, feat in enumerate(self.feature_names):
                top_factors[feat] = round(float(importances[i]), 4)
            # Sort by importance
            top_factors = dict(sorted(top_factors.items(), key=lambda x: x[1], reverse=True)[:5])
        elif hasattr(self.model, 'coef_'):
            coefs = np.abs(self.model.coef_[0])
            for i, feat in enumerate(self.feature_names):
                top_factors[feat] = round(float(coefs[i]), 4)
            top_factors = dict(sorted(top_factors.items(), key=lambda x: x[1], reverse=True)[:5])
        
        # Generate recommendations
        recommendations = self._generate_recommendations(proba, risk_level, patient_data)
        
        return {
            'risk_score': round(proba, 4),
            'risk_level': risk_level,
            'confidence_interval_lower': round(max(0, proba - 0.1), 4),
            'confidence_interval_upper': round(min(1, proba + 0.1), 4),
            'top_risk_factors': top_factors,
            'recommended_tests': recommendations['tests'],
            'recommended_actions': recommendations['actions'],
            'model_version': self.model_name,
            'model_name': self.metadata.get('model_type', 'unknown'),
        }
    
    def _heuristic_predict(self, X, patient_data) -> Dict:
        """Simple rule-based fallback when no ML model is loaded."""
        from patients.models import Patient
        
        if isinstance(patient_data, Patient):
            score = 0.0
            score += min(patient_data.number_of_partners_12m * 0.05, 0.3)
            score += 0.15 if patient_data.prior_sti_history else 0
            score += 0.1 if patient_data.substance_use else 0
            score += 0.1 if patient_data.symptoms_present else 0
            score += 0.15 if patient_data.hiv_status == 'positive' else 0
            score += 0.05 if patient_data.hiv_status == 'unknown' else 0
            score += (1 - patient_data.condom_use_frequency) * 0.2
            score += 0.05 if patient_data.gender == 'M' else 0
        else:
            score = 0.3  # default moderate
        
        score = min(1.0, score)
        
        if score < 0.25:
            risk_level = 'low'
        elif score < 0.50:
            risk_level = 'moderate'
        elif score < 0.75:
            risk_level = 'high'
        else:
            risk_level = 'very_high'
        
        return {
            'risk_score': round(score, 4),
            'risk_level': risk_level,
            'confidence_interval_lower': round(max(0, score - 0.15), 4),
            'confidence_interval_upper': round(min(1, score + 0.15), 4),
            'top_risk_factors': {'heuristic_model': 'Using rule-based fallback'},
            'recommended_tests': ['HIV', 'Syphilis', 'Gonorrhea', 'Chlamydia'] if score > 0.3 else ['HIV', 'Syphilis'],
            'recommended_actions': 'Schedule screening appointment. Provide risk reduction counseling.',
            'model_version': 'heuristic_v1',
            'model_name': 'Rule-based Heuristic',
        }
    
    def _generate_recommendations(self, score: float, level: str, patient_data) -> Dict:
        """Generate test recommendations based on risk."""
        tests = []
        actions = []
        
        if level in ('high', 'very_high'):
            tests = ['HIV', 'Syphilis', 'Gonorrhea', 'Chlamydia', 'Hepatitis B', 'HPV']
            actions = (
                "Immediate comprehensive STI screening recommended. "
                "Provide risk reduction counseling. "
                "Consider PrEP evaluation for HIV. "
                "Partner notification and contact tracing. "
                "Follow-up in 2-4 weeks."
            )
        elif level == 'moderate':
            tests = ['HIV', 'Syphilis', 'Gonorrhea', 'Chlamydia']
            actions = (
                "Routine STI screening recommended. "
                "Provide condom counseling and risk reduction education. "
                "Schedule follow-up in 3 months. "
                "Consider PrEP if ongoing risk factors."
            )
        else:
            tests = ['HIV', 'Syphilis']
            actions = (
                "Continue routine screening per guidelines. "
                "Reinforce safer sex practices. "
                "Annual rescreening recommended."
            )
        
        return {'tests': tests, 'actions': actions}


def get_predictor(model_name: str = None, sti_type: str = "general") -> STIPredictor:
    """Factory function to get predictor instance."""
    if model_name is None:
        model_name = "sti_risk_v1"
    return STIPredictor(model_name=model_name, sti_type=sti_type)