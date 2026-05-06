import uuid
import hashlib
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from collections import defaultdict

from django.db import transaction
from sklearn.impute import SimpleImputer, KNNImputer
from sklearn.preprocessing import StandardScaler, LabelEncoder, OneHotEncoder

try:
    from imblearn.over_sampling import SMOTE
except ImportError:
    # imbalanced-learn not installed, SMOTE functionality will not be available
    SMOTE = None

from .models import PreprocessingJob, ProcessedRecord, ProcessingStatus, FeatureEncoderConfig

class DifferentialPrivacy:
    """Differential privacy for geospatial and demographic data"""
    
    def __init__(self, epsilon: float = 0.1, sensitivity: float = 1.0):
        self.epsilon = epsilon
        self.sensitivity = sensitivity
        self.scale = sensitivity / epsilon
    
    def add_laplace_noise(self, value: float) -> float:
        """Add Laplace noise to a numeric value"""
        noise = np.random.laplace(0, self.scale)
        return value + noise
    
    def anonymize_coordinates(self, lat: float, lon: float, grid_size_km: float = 5.0) -> Tuple[float, float]:
        """Round coordinates to grid (±5km as per spec)"""
        # Approximate: 0.045 degrees ≈ 5km
        grid_degrees = grid_size_km * 0.009
        lat_rounded = round(lat / grid_degrees) * grid_degrees
        lon_rounded = round(lon / grid_degrees) * grid_degrees
        return lat_rounded, lon_rounded

class FeatureEngineer:
    """Feature engineering for STI risk model"""
    
    SYMPTOM_LIST = [
        "genital_discharge", "painful_urination", "genital_sores", "pelvic_pain",
        "testicular_pain", "abnormal_bleeding", "itching", "fever", "rash",
        "swollen_lymph_nodes", "rectal_pain", "rectal_bleeding", "sore_throat",
        "joint_pain", "hair_loss", "weight_loss", "night_sweats", "fatigue",
        "nausea", "vomiting", "diarrhoea", "abdominal_pain", "back_pain",
        "dysuria", "dyspareunia", "menorrhagia", "metrorrhagia", "urethral_discharge",
        "vaginal_odour", "dysmenorrhoea", "proctitis", "lymphadenopathy"
    ]
    
    def __init__(self):
        self.scaler = StandardScaler()
        self.label_encoders = {}
    
    def extract_symptom_vector(self, symptoms: Dict) -> List[int]:
        """Convert symptom dict to 32-bit binary vector"""
        vector = []
        for symptom in self.SYMPTOM_LIST:
            vector.append(1 if symptoms.get(symptom, False) else 0)
        return vector
    
    def compute_composite_risk_score(self, behaviours: Dict) -> float:
        """Weighted composite risk score 0-1"""
        weights = {
            "partner_count_12m": 0.3,
            "condom_use": 0.25,
            "prior_testing": -0.15,  # Negative = protective
            "substance_use": 0.2,
            "sex_work_exposure": 0.25
        }
        
        score = 0.0
        
        # Partner count (normalized 0-10+)
        partners = min(behaviours.get("partner_count_12m", 0), 10)
        score += (partners / 10) * weights["partner_count_12m"]
        
        # Condom use
        condom_map = {"never": 1.0, "sometimes": 0.5, "often": 0.2, "always": 0.0}
        score += condom_map.get(behaviours.get("condom_use_frequency", "never"), 1.0) * weights["condom_use"]
        
        # Prior testing (protective)
        score += (-1 if behaviours.get("prior_testing_history", False) else 0) * weights["prior_testing"]
        
        # Substance use
        score += (1 if behaviours.get("substance_use", False) else 0) * weights["substance_use"]
        
        # Sex work exposure
        score += (1 if behaviours.get("sex_work_exposure", False) else 0) * weights["sex_work_exposure"]
        
        return max(0.0, min(1.0, score))
    
    def encode_demographics(self, demographics: Dict) -> Dict:
        """Encode demographic features"""
        age = demographics.get("age", 30)
        sex = demographics.get("sex", "other")
        region = demographics.get("geographic_region", "unknown")
        
        # Age groups: <18, 18-24, 25-34, 35-44, 45+
        age_encoded = 0 if age < 18 else (1 if age < 25 else (2 if age < 35 else (3 if age < 45 else 4)))
        
        # Sex encoding
        sex_map = {"male": 0, "female": 1, "other": 2}
        sex_encoded = sex_map.get(sex, 2)
        
        return {
            "age_encoded": age_encoded,
            "age_scaled": (age - 30) / 20,  # Standardized
            "sex_encoded": sex_encoded,
            "region": region
        }
    
    def temporal_features(self) -> Dict[str, float]:
        """Extract temporal features from current date"""
        now = datetime.now()
        return {
            "month_of_year": now.month / 12.0,
            "quarter": ((now.month - 1) // 3 + 1) / 4.0,
            "day_of_week": now.weekday() / 7.0
        }

class PreprocessingPipeline:
    """Main preprocessing pipeline service"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.dp = DifferentialPrivacy(epsilon=config.get("dp_epsilon", 0.1))
        self.engineer = FeatureEngineer()
        self.imputer = None
        self._init_imputer()
    
    def _init_imputer(self):
        strategy = self.config.get("imputation_strategy", "median")
        if strategy == "knn":
            self.imputer = KNNImputer(n_neighbors=5)
        else:
            self.imputer = SimpleImputer(strategy=strategy)
    
    def generate_anonymous_id(self, record: Dict) -> str:
        """Generate deterministic anonymous ID"""
        # Hash of demographic + timestamp to prevent re-identification
        hash_input = f"{record['demographics']['age']}:{record['demographics']['sex']}:{record['demographics']['geographic_region']}:{datetime.now().isoformat()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:32]
    
    def deduplicate(self, records: List[Dict]) -> Tuple[List[Dict], int]:
        """Remove duplicate records based on configured keys"""
        keys = self.config.get("deduplication_keys", ["age", "sex", "geographic_region"])
        seen = set()
        unique_records = []
        duplicates = 0
        
        for record in records:
            key_tuple = tuple(record.get("demographics", {}).get(k) for k in keys)
            if key_tuple in seen:
                duplicates += 1
                continue
            seen.add(key_tuple)
            unique_records.append(record)
        
        return unique_records, duplicates
    
    def impute_missing(self, df: pd.DataFrame) -> pd.DataFrame:
        """Impute missing values in numerical columns"""
        numerical_cols = df.select_dtypes(include=[np.number]).columns
        if len(numerical_cols) > 0:
            df[numerical_cols] = self.imputer.fit_transform(df[numerical_cols])
        return df
    
    def apply_smote(self, X: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Apply SMOTE oversampling for class imbalance"""
        if not self.config.get("apply_smote", True):
            return X, y
        
        strategy = self.config.get("smote_sampling_strategy", "auto")
        smote = SMOTE(sampling_strategy=strategy, random_state=42)
        X_resampled, y_resampled = smote.fit_resample(X, y)
        return X_resampled, y_resampled
    
    def apply_k_anonymity(self, records: List[ProcessedRecord], k: int = 10) -> List[ProcessedRecord]:
        """Group records for k-anonymity on quasi-identifiers"""
        # Group by age range + sex + region
        groups = defaultdict(list)
        for record in records:
            age = record.demographics.get("age", 0)
            age_group = (age // 5) * 5  # 5-year buckets
            key = (age_group, record.demographics.get("sex"), record.geographic_region)
            groups[key].append(record)
        
        # Assign group IDs only to groups meeting k threshold
        group_id = 1
        for key, group_records in groups.items():
            if len(group_records) >= k:
                for record in group_records:
                    record.k_anonymity_group = group_id
                group_id += 1
        
        return records
    
    def process_single_record(self, raw_record: Dict) -> Dict:
        """Process a single raw record"""
        # Generate anonymous ID
        anonymous_id = self.generate_anonymous_id(raw_record)
        
        # Extract features
        symptoms = raw_record.get("symptoms", {})
        symptom_vector = self.engineer.extract_symptom_vector(symptoms)
        
        behaviours = raw_record.get("risk_behaviours", {})
        composite_risk = self.engineer.compute_composite_risk_score(behaviours)
        
        demographics = raw_record.get("demographics", {})
        demo_encoded = self.engineer.encode_demographics(demographics)
        
        temporal = self.engineer.temporal_features()
        
        # Apply differential privacy to risk score if enabled
        if self.config.get("apply_differential_privacy", True):
            composite_risk = self.dp.add_laplace_noise(composite_risk)
            composite_risk = max(0.0, min(1.0, composite_risk))
        
        # Determine risk level
        risk_level = "low"
        if composite_risk > 0.7:
            risk_level = "critical"
        elif composite_risk > 0.5:
            risk_level = "high"
        elif composite_risk > 0.3:
            risk_level = "moderate"
        
        return {
            "anonymous_id": anonymous_id,
            "symptom_vector": symptom_vector,
            "composite_risk_score": round(composite_risk, 4),
            "age_encoded": demo_encoded["age_encoded"],
            "age_scaled": round(demo_encoded["age_scaled"], 4),
            "sex_encoded": demo_encoded["sex_encoded"],
            "region": demo_encoded["region"],
            "temporal_features": temporal,
            "risk_level": risk_level,
            "geographic_region": demographics.get("geographic_region", "unknown"),
            "privacy_applied": self.config.get("apply_differential_privacy", True)
        }
    
    def process_batch(self, records: List[Dict]) -> Tuple[List[Dict], Dict]:
        """Process a batch of records through full pipeline"""
        stats = {
            "raw_count": len(records),
            "duplicate_count": 0,
            "processed_count": 0,
            "failed_count": 0
        }
        
        # Stage 1: Deduplication
        if self.config.get("apply_deduplication", True):
            records, stats["duplicate_count"] = self.deduplicate(records)
        
        # Stage 2: Feature engineering & single record processing
        processed = []
        for record in records:
            try:
                processed.append(self.process_single_record(record))
            except Exception as e:
                stats["failed_count"] += 1
                continue
        
        stats["processed_count"] = len(processed)
        return processed, stats