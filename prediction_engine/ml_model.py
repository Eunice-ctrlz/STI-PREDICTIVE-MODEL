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
        print(">>> DEBUG feature_names:", self.feature_names)
        print(">>> DEBUG X:", X)
        
        # Calculate patient-specific risk factor attributions (varies per patient)
        top_factors = self._calculate_patient_factors(patient_data)
        
        # Predict likely STIs (one or two most likely)
        likely_stis = self._calculate_likely_stis(patient_data)

        if self.model is None:
            # Fallback heuristic model
            res = self._heuristic_predict(X, patient_data)
            res['top_risk_factors'] = top_factors
            res['likely_stis'] = likely_stis
            return res
        
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
        
        # Generate recommendations dynamically based on risk level and factors
        recommendations = self._generate_recommendations(proba, risk_level, patient_data)
        
        return {
            'risk_score': round(proba, 4),
            'risk_level': risk_level,
            'confidence_interval_lower': round(max(0, proba - 0.1), 4),
            'confidence_interval_upper': round(min(1, proba + 0.1), 4),
            'top_risk_factors': top_factors,
            'likely_stis': likely_stis,
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
        
        recommendations = self._generate_recommendations(score, risk_level, patient_data)

        return {
            'risk_score': round(score, 4),
            'risk_level': risk_level,
            'confidence_interval_lower': round(max(0, score - 0.15), 4),
            'confidence_interval_upper': round(min(1, score + 0.15), 4),
            'top_risk_factors': {},  # Will be populated by predict()
            'likely_stis': [],       # Will be populated by predict()
            'recommended_tests': recommendations['tests'],
            'recommended_actions': recommendations['actions'],
            'model_version': 'heuristic_v1',
            'model_name': 'Rule-based Heuristic',
        }
    
    def _calculate_patient_factors(self, patient_data) -> Dict[str, float]:
        """Calculate patient-specific risk factor attributions (scaled 0.0 - 1.0)."""
        from patients.models import Patient
        
        # Get patient attributes
        if isinstance(patient_data, Patient):
            age = patient_data.age
            gender = patient_data.gender
            num_partners_12m = patient_data.number_of_partners_12m
            num_partners_lifetime = patient_data.number_of_partners_lifetime
            condom_use_freq = patient_data.condom_use_frequency
            substance_use = 1.0 if patient_data.substance_use else 0.0
            prior_sti_history = 1.0 if patient_data.prior_sti_history else 0.0
            symptoms_present = 1.0 if patient_data.symptoms_present else 0.0
            hiv_status = patient_data.hiv_status
            marital = patient_data.marital_status
        else:
            data = patient_data
            age = data.get('age', 25)
            gender = data.get('gender', 'U')
            num_partners_12m = data.get('number_of_partners_12m', 0)
            num_partners_lifetime = data.get('number_of_partners_lifetime', 0)
            condom_use_freq = data.get('condom_use_frequency', 1.0)
            substance_use = 1.0 if data.get('substance_use') else 0.0
            prior_sti_history = 1.0 if data.get('prior_sti_history') else 0.0
            symptoms_present = 1.0 if data.get('symptoms_present') else 0.0
            hiv_status = data.get('hiv_status', 'unknown')
            marital = data.get('marital_status', 'single')

        # Retrieve global feature importances
        global_importances = {}
        if self.model is not None and hasattr(self.model, 'feature_importances_'):
            importances = self.model.feature_importances_
            for i, feat in enumerate(self.feature_names):
                global_importances[feat] = float(importances[i])
        elif self.model is not None and hasattr(self.model, 'coef_'):
            coefs = np.abs(self.model.coef_[0])
            for i, feat in enumerate(self.feature_names):
                global_importances[feat] = float(coefs[i])
        else:
            # Default fallback importances reflecting clinical feature relevance
            global_importances = {
                'age': 0.05,
                'num_partners_12m': 0.25,
                'num_partners_lifetime': 0.10,
                'condom_use_freq': 0.20,
                'substance_use': 0.10,
                'prior_sti_history': 0.15,
                'hiv_positive': 0.10,
                'hiv_unknown': 0.05,
                'symptoms_present': 0.20,
                'gender_male': 0.02,
                'gender_female': 0.02,
                'gender_other': 0.01,
                'marital_single': 0.03,
                'marital_married': 0.03,
                'marital_divorced': 0.02,
                'marital_cohabiting': 0.02,
            }

        # Calculate patient-specific risk intensity / presence (0 to 1 scale)
        patient_risk_presence = {
            'age': max(0.0, (25.0 - age) / 10.0) if age < 25 else 0.0,
            'gender_male': 1.0 if gender == 'M' else 0.0,
            'gender_female': 1.0 if gender == 'F' else 0.0,
            'gender_other': 1.0 if gender in ('O', 'U') else 0.0,
            'num_partners_12m': min(num_partners_12m / 3.0, 2.0),
            'num_partners_lifetime': min(num_partners_lifetime / 10.0, 2.0),
            'condom_use_freq': max(0.0, 1.0 - condom_use_freq),
            'substance_use': substance_use,
            'prior_sti_history': prior_sti_history,
            'hiv_positive': 1.0 if hiv_status == 'positive' else 0.0,
            'hiv_unknown': 1.0 if hiv_status == 'unknown' else 0.0,
            'symptoms_present': symptoms_present,
            'marital_single': 1.0 if marital == 'single' else 0.0,
            'marital_married': 0.0, # married indicates reduced/baseline risk
            'marital_divorced': 1.0 if marital == 'divorced' else 0.0,
            'marital_cohabiting': 1.0 if marital == 'cohabiting' else 0.0,
        }

        # Combine global importance with patient risk presence
        patient_contributions = {}
        for feat, glob_imp in global_importances.items():
            presence = patient_risk_presence.get(feat, 0.0)
            val = glob_imp * presence
            if val > 0:
                patient_contributions[feat] = round(val, 4)

        if not patient_contributions:
            return {'low_behavioral_risk': 0.01}

        # Sort and return top 5
        return dict(sorted(patient_contributions.items(), key=lambda x: x[1], reverse=True)[:5])

    def _calculate_likely_stis(self, patient_data) -> List[str]:
        """Calculate the probability score for specific STIs and return the top 1 or 2 most likely STIs."""
        from patients.models import Patient
        
        if isinstance(patient_data, Patient):
            age = patient_data.age
            gender = patient_data.gender
            num_partners_12m = patient_data.number_of_partners_12m
            num_partners_lifetime = patient_data.number_of_partners_lifetime
            condom_use_freq = patient_data.condom_use_frequency
            substance_use = patient_data.substance_use
            prior_sti_history = patient_data.prior_sti_history
            symptoms_present = patient_data.symptoms_present
            hiv_status = patient_data.hiv_status
        else:
            data = patient_data
            age = data.get('age', 25)
            gender = data.get('gender', 'U')
            num_partners_12m = data.get('number_of_partners_12m', 0)
            num_partners_lifetime = data.get('number_of_partners_lifetime', 0)
            condom_use_freq = data.get('condom_use_frequency', 1.0)
            substance_use = data.get('substance_use', False)
            prior_sti_history = data.get('prior_sti_history', False)
            symptoms_present = data.get('symptoms_present', False)
            hiv_status = data.get('hiv_status', 'unknown')

        sti_scores = {}

        # 1. Gonorrhea
        gonorrhea_score = 0.10
        if symptoms_present:
            gonorrhea_score += 0.45
        if age < 25:
            gonorrhea_score += 0.15
        if condom_use_freq < 0.5:
            gonorrhea_score += 0.15
        if num_partners_12m > 2:
            gonorrhea_score += 0.15
        sti_scores['Gonorrhea'] = gonorrhea_score

        # 2. Chlamydia
        chlamydia_score = 0.15
        if symptoms_present:
            chlamydia_score += 0.40
        if age < 25:
            chlamydia_score += 0.20
        if condom_use_freq < 0.5:
            chlamydia_score += 0.15
        if num_partners_12m > 2:
            chlamydia_score += 0.10
        sti_scores['Chlamydia'] = chlamydia_score

        # 3. Syphilis
        syphilis_score = 0.05
        if prior_sti_history:
            syphilis_score += 0.20
        if symptoms_present:
            syphilis_score += 0.20
        if num_partners_12m > 3:
            syphilis_score += 0.15
        if condom_use_freq < 0.5:
            syphilis_score += 0.10
        sti_scores['Syphilis'] = syphilis_score

        # 4. HPV
        hpv_score = 0.08
        if gender == 'F':
            hpv_score += 0.15
        if num_partners_lifetime > 5:
            hpv_score += 0.20
        if condom_use_freq < 0.5:
            hpv_score += 0.15
        if age < 30:
            hpv_score += 0.10
        sti_scores['HPV'] = hpv_score

        # 5. HIV
        hiv_score = 0.01
        if hiv_status == 'positive':
            hiv_score = -1.0 # Patient already has HIV
        else:
            if hiv_status == 'unknown' and condom_use_freq < 0.5:
                hiv_score += 0.10
            if prior_sti_history:
                hiv_score += 0.15
            if num_partners_12m > 4:
                hiv_score += 0.20
            if substance_use:
                hiv_score += 0.10
        sti_scores['HIV'] = hiv_score

        # 6. Hepatitis B
        hepb_score = 0.02
        if substance_use:
            hepb_score += 0.20
        if condom_use_freq < 0.5:
            hepb_score += 0.10
        if num_partners_12m > 3:
            hepb_score += 0.10
        sti_scores['Hepatitis B'] = hepb_score

        # Sort STIs by score descending
        sorted_stis = sorted(sti_scores.items(), key=lambda x: x[1], reverse=True)

        # Select the top 1 or 2 with score > 0.15
        selected = [name for name, score in sorted_stis if score > 0.15][:2]
        
        # If none met the threshold, just return the single highest score if it's positive
        if not selected and sorted_stis[0][1] > 0.05:
            selected = [sorted_stis[0][0]]

        return selected

    def _generate_recommendations(self, score: float, level: str, patient_data) -> Dict:
        """Generate test recommendations dynamically based on risk level and factors."""
        from patients.models import Patient
        
        if isinstance(patient_data, Patient):
            symptoms_present = patient_data.symptoms_present
            prior_sti_history = patient_data.prior_sti_history
            condom_use_freq = patient_data.condom_use_frequency
            num_partners_12m = patient_data.number_of_partners_12m
            substance_use = patient_data.substance_use
            hiv_status = patient_data.hiv_status
        else:
            symptoms_present = patient_data.get('symptoms_present', False)
            prior_sti_history = patient_data.get('prior_sti_history', False)
            condom_use_freq = patient_data.get('condom_use_frequency', 1.0)
            num_partners_12m = patient_data.get('number_of_partners_12m', 0)
            substance_use = patient_data.get('substance_use', False)
            hiv_status = patient_data.get('hiv_status', 'unknown')

        tests = ['HIV', 'Syphilis']  # Baseline recommendations
        actions = []

        # Symptom-driven recommendations
        if symptoms_present:
            tests.extend(['Gonorrhea', 'Chlamydia'])
            actions.append("Symptom-driven diagnostic screening initiated for active urethritis/cervicitis symptoms.")

        # Behavioral-driven recommendations
        if condom_use_freq < 0.5 or num_partners_12m > 2:
            if 'Gonorrhea' not in tests:
                tests.append('Gonorrhea')
            if 'Chlamydia' not in tests:
                tests.append('Chlamydia')
            actions.append("Advise routine screening due to multiple partners or inconsistent condom use. Provide risk reduction counseling.")

        # History and substance-use driven recommendations
        if prior_sti_history or substance_use:
            tests.append('Hepatitis B')
            actions.append("Recommend Hepatitis B screening and check vaccination history due to clinical history/substance use.")

        # High risk level extras
        if level in ('high', 'very_high'):
            if 'Gonorrhea' not in tests:
                tests.append('Gonorrhea')
            if 'Chlamydia' not in tests:
                tests.append('Chlamydia')
            if 'Hepatitis B' not in tests:
                tests.append('Hepatitis B')
            tests.append('HPV')
            actions.append("Comprehensive panel recommended. Counsel on PrEP (Pre-Exposure Prophylaxis) and partner referral services.")
        elif level == 'moderate':
            actions.append("Follow-up evaluation recommended in 3 months.")
        else:
            actions.append("Continue standard routine screening per guidelines.")

        # Deduplicate tests
        unique_tests = []
        for t in tests:
            if t not in unique_tests:
                unique_tests.append(t)

        return {
            'tests': unique_tests,
            'actions': " ".join(actions)
        }


def get_predictor(model_name: str = None, sti_type: str = "general") -> STIPredictor:
    """Factory function to get predictor instance."""
    if model_name is None:
        model_name = "sti_risk_v1"
    return STIPredictor(model_name=model_name, sti_type=sti_type)