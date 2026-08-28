"""
ML Model wrapper for STI prediction.

Supports:
- Trained machine learning models
- Feature preprocessing
- Risk prediction
- SHAP-based explainability
- Rule-based fallback when no trained model exists
"""

import json
import os
import pickle

import joblib
import numpy as np

from typing import Dict

from django.conf import settings

from ml_pipeline.explainability import ModelExplainer


class STIPredictor:
    """
    Unified predictor for STI risk assessment.
    """

    FEATURE_ORDER = [
        "age",
        "gender_male",
        "gender_female",
        "gender_other",
        "num_partners_12m",
        "num_partners_lifetime",
        "condom_use_freq",
        "substance_use",
        "prior_sti_history",
        "hiv_positive",
        "hiv_unknown",
        "symptoms_present",
        "marital_single",
        "marital_married",
        "marital_divorced",
        "marital_cohabiting",
    ]

    def __init__(
        self,
        model_name: str = "sti_risk_v1",
        sti_type: str = "general",
    ):
        self.model_name = model_name
        self.sti_type = sti_type

        self.model = None
        self.scaler = None
        self.metadata = {}

        self.feature_names = list(self.FEATURE_ORDER)

        self.explainer = None

        # Load the trained model first
        self._load_model()

        # Initialize SHAP only after model loading
        if self.model is not None:
            try:
                self.explainer = ModelExplainer(
                    model=self.model,
                    feature_names=self.feature_names,
                )
            except Exception as error:
                print(
                    f"Warning: Could not initialize SHAP explainer: "
                    f"{error}"
                )
                self.explainer = None

    def _get_model_path(self) -> str:
        """
        Return the directory containing the saved
        model artifacts.
        """

        return os.path.join(
            settings.MEDIA_ROOT,
            "models",
            self.model_name,
        )

    def _load_model(self):
        """
        Load the trained model, scaler, and metadata.
        """

        model_dir = self._get_model_path()

        if not os.path.exists(model_dir):
            print(
                f"Model directory not found: {model_dir}"
            )
            self.model = None
            return

        model_path = os.path.join(
            model_dir,
            "model.joblib",
        )

        if not os.path.exists(model_path):
            model_path = os.path.join(
                model_dir,
                "model.pkl",
            )

        scaler_path = os.path.join(
            model_dir,
            "scaler.joblib",
        )

        metadata_path = os.path.join(
            model_dir,
            "metadata.json",
        )

        # Load model
        if os.path.exists(model_path):
            try:
                self.model = joblib.load(
                    model_path
                )

                print(
                    f"Model loaded successfully: "
                    f"{self.model_name}"
                )

            except Exception:
                try:
                    with open(
                        model_path,
                        "rb",
                    ) as file:
                        self.model = pickle.load(file)

                    print(
                        f"Model loaded using pickle: "
                        f"{self.model_name}"
                    )

                except Exception as error:
                    print(
                        f"Failed to load model: {error}"
                    )
                    self.model = None
        else:
            print(
                f"Model file not found: {model_path}"
            )
            self.model = None

        # Load scaler
        if os.path.exists(scaler_path):
            try:
                self.scaler = joblib.load(
                    scaler_path
                )

                print(
                    "Scaler loaded successfully."
                )

            except Exception as error:
                print(
                    f"Failed to load scaler: {error}"
                )

                self.scaler = None

        # Load metadata
        if os.path.exists(metadata_path):
            try:
                with open(
                    metadata_path,
                    "r",
                ) as file:
                    self.metadata = json.load(
                        file
                    )

                if (
                    "feature_names"
                    in self.metadata
                ):
                    self.feature_names = (
                        self.metadata[
                            "feature_names"
                        ]
                    )

                print(
                    "Model metadata loaded successfully."
                )

            except Exception as error:
                print(
                    f"Failed to load metadata: {error}"
                )

    def _preprocess_features(
        self,
        patient_data,
    ) -> np.ndarray:
        """
        Convert patient data into the exact feature
        vector expected by the trained model.
        """

        from patients.models import Patient

        if isinstance(
            patient_data,
            Patient,
        ):
            data = {
                "age": patient_data.age,

                "num_partners_12m":
                    patient_data.number_of_partners_12m,

                "num_partners_lifetime":
                    patient_data.number_of_partners_lifetime,

                "condom_use_freq":
                    patient_data.condom_use_frequency,

                "substance_use":
                    1
                    if patient_data.substance_use
                    else 0,

                "prior_sti_history":
                    1
                    if patient_data.prior_sti_history
                    else 0,

                "symptoms_present":
                    1
                    if patient_data.symptoms_present
                    else 0,
            }

            # -------------------------
            # Gender encoding
            # -------------------------

            gender = patient_data.gender

            data["gender_male"] = (
                1
                if gender == "M"
                else 0
            )

            data["gender_female"] = (
                1
                if gender == "F"
                else 0
            )

            data["gender_other"] = (
                1
                if gender in ("O", "U")
                else 0
            )

            # -------------------------
            # HIV status encoding
            # -------------------------

            data["hiv_positive"] = (
                1
                if patient_data.hiv_status
                == "positive"
                else 0
            )

            data["hiv_unknown"] = (
                1
                if patient_data.hiv_status
                == "unknown"
                else 0
            )

            # -------------------------
            # Marital status encoding
            # -------------------------

            marital_status = (
                patient_data.marital_status
            )

            data["marital_single"] = (
                1
                if marital_status == "single"
                else 0
            )

            data["marital_married"] = (
                1
                if marital_status == "married"
                else 0
            )

            data["marital_divorced"] = (
                1
                if marital_status == "divorced"
                else 0
            )

            data["marital_cohabiting"] = (
                1
                if marital_status == "cohabiting"
                else 0
            )

        else:
            data = patient_data

        # Build features in the exact order
        # expected by the model.
        features = []

        for feature in self.feature_names:
            features.append(
                float(
                    data.get(
                        feature,
                        0,
                    )
                )
            )

        X = np.array(
            features,
            dtype=float,
        ).reshape(1, -1)

        # Apply scaler if available
        if self.scaler is not None:
            X = self.scaler.transform(X)

        return X

    def predict(
        self,
        patient_data,
    ) -> Dict:
        """
        Generate an STI risk prediction and explanation.
        """

        # Create the exact feature vector
        # used by the model.
        X = self._preprocess_features(
            patient_data
        )

        # Existing risk factor logic remains
        # as the fallback explanation.
        top_factors = (
            self._calculate_patient_factors(
                patient_data
            )
        )

        explanation = {
            "positive_contributors": [],
            "negative_contributors": [],
            "method": (
                "feature_importance_fallback"
            ),
        }

        # Calculate possible STI types
        likely_stis = (
            self._calculate_likely_stis(
                patient_data
            )
        )

        # =====================================
        # FALLBACK WHEN MODEL IS NOT AVAILABLE
        # =====================================

        if self.model is None:

            result = self._heuristic_predict(
                X,
                patient_data,
            )

            result[
                "top_risk_factors"
            ] = top_factors

            result[
                "likely_stis"
            ] = likely_stis

            result["explanation"] = {
                "positive_contributors": [
                    {
                        "feature": feature,
                        "contribution": value,
                        "absolute_contribution": value,
                    }
                    for feature, value
                    in top_factors.items()
                ],

                "negative_contributors": [],

                "method": (
                    "heuristic_fallback"
                ),
            }

            return result

        # =====================================
        # MACHINE LEARNING PREDICTION
        # =====================================

        if hasattr(
            self.model,
            "predict_proba",
        ):
            proba = float(
                self.model.predict_proba(X)[0][1]
            )

        else:
            proba = float(
                self.model.predict(X)[0]
            )

        # Ensure probability stays valid
        proba = max(
            0.0,
            min(1.0, proba),
        )

        # =====================================
        # SHAP EXPLAINABILITY
        # =====================================

        if self.explainer is not None:

            shap_explanation = (
                self.explainer.explain(X)
            )

            # Only use SHAP if it succeeded.
            if (
                shap_explanation.get("method")
                == "SHAP"
            ):
                explanation = (
                    shap_explanation
                )

                positive_contributors = (
                    explanation.get(
                        "positive_contributors",
                        [],
                    )
                )

                # Keep backward compatibility
                # with top_risk_factors.
                if positive_contributors:

                    top_factors = {
                        item["feature"]:
                        item[
                            "absolute_contribution"
                        ]
                        for item
                        in positive_contributors
                    }

            else:
                # Preserve fallback information
                # if SHAP fails.
                explanation = (
                    shap_explanation
                )

        # =====================================
        # RISK CLASSIFICATION
        # =====================================

        if proba < 0.25:
            risk_level = "low"

        elif proba < 0.50:
            risk_level = "moderate"

        elif proba < 0.75:
            risk_level = "high"

        else:
            risk_level = "very_high"

        # =====================================
        # RECOMMENDATIONS
        # =====================================

        recommendations = (
            self._generate_recommendations(
                proba,
                risk_level,
                patient_data,
            )
        )

        # =====================================
        # FINAL RESPONSE
        # =====================================

        return {
            "risk_score": round(
                proba,
                4,
            ),

            "risk_level": risk_level,

            "confidence_interval_lower":
                round(
                    max(
                        0,
                        proba - 0.1,
                    ),
                    4,
                ),

            "confidence_interval_upper":
                round(
                    min(
                        1,
                        proba + 0.1,
                    ),
                    4,
                ),

            # Existing field
            "top_risk_factors":
                top_factors,

            # New SHAP explanation
            "explanation":
                explanation,

            "likely_stis":
                likely_stis,

            "recommended_tests":
                recommendations["tests"],

            "recommended_actions":
                recommendations["actions"],

            "model_version":
                self.model_name,

            "model_name":
                self.metadata.get(
                    "model_type",
                    "unknown",
                ),
        }

    def _heuristic_predict(
        self,
        X,
        patient_data,
    ) -> Dict:
        """
        Rule-based fallback when no trained
        ML model is available.
        """

        from patients.models import Patient

        if isinstance(
            patient_data,
            Patient,
        ):
            score = 0.0

            score += min(
                patient_data.number_of_partners_12m
                * 0.05,
                0.3,
            )

            score += (
                0.15
                if patient_data.prior_sti_history
                else 0
            )

            score += (
                0.1
                if patient_data.substance_use
                else 0
            )

            score += (
                0.1
                if patient_data.symptoms_present
                else 0
            )

            score += (
                0.15
                if patient_data.hiv_status
                == "positive"
                else 0
            )

            score += (
                0.05
                if patient_data.hiv_status
                == "unknown"
                else 0
            )

            score += (
                1
                - patient_data.condom_use_frequency
            ) * 0.2

            score += (
                0.05
                if patient_data.gender == "M"
                else 0
            )

        else:
            score = 0.3

        score = min(
            1.0,
            score,
        )

        if score < 0.25:
            risk_level = "low"

        elif score < 0.50:
            risk_level = "moderate"

        elif score < 0.75:
            risk_level = "high"

        else:
            risk_level = "very_high"

        recommendations = (
            self._generate_recommendations(
                score,
                risk_level,
                patient_data,
            )
        )

        return {
            "risk_score": round(
                score,
                4,
            ),

            "risk_level":
                risk_level,

            "confidence_interval_lower":
                round(
                    max(
                        0,
                        score - 0.15,
                    ),
                    4,
                ),

            "confidence_interval_upper":
                round(
                    min(
                        1,
                        score + 0.15,
                    ),
                    4,
                ),

            "top_risk_factors": {},

            "likely_stis": [],

            "recommended_tests":
                recommendations["tests"],

            "recommended_actions":
                recommendations["actions"],

            "model_version":
                "heuristic_v1",

            "model_name":
                "Rule-based Heuristic",
        }

    def _calculate_patient_factors(
        self,
        patient_data,
    ) -> Dict[str, float]:
        """
        Calculate fallback patient-specific
        risk factor attributions.
        """

        from patients.models import Patient

        if isinstance(
            patient_data,
            Patient,
        ):
            age = patient_data.age

            gender = patient_data.gender

            num_partners_12m = (
                patient_data.number_of_partners_12m
            )

            num_partners_lifetime = (
                patient_data.number_of_partners_lifetime
            )

            condom_use_freq = (
                patient_data.condom_use_frequency
            )

            substance_use = (
                1.0
                if patient_data.substance_use
                else 0.0
            )

            prior_sti_history = (
                1.0
                if patient_data.prior_sti_history
                else 0.0
            )

            symptoms_present = (
                1.0
                if patient_data.symptoms_present
                else 0.0
            )

            hiv_status = (
                patient_data.hiv_status
            )

            marital = (
                patient_data.marital_status
            )

        else:
            data = patient_data

            age = data.get(
                "age",
                25,
            )

            gender = data.get(
                "gender",
                "U",
            )

            num_partners_12m = data.get(
                "number_of_partners_12m",
                0,
            )

            num_partners_lifetime = data.get(
                "number_of_partners_lifetime",
                0,
            )

            condom_use_freq = data.get(
                "condom_use_frequency",
                1.0,
            )

            substance_use = (
                1.0
                if data.get(
                    "substance_use"
                )
                else 0.0
            )

            prior_sti_history = (
                1.0
                if data.get(
                    "prior_sti_history"
                )
                else 0.0
            )

            symptoms_present = (
                1.0
                if data.get(
                    "symptoms_present"
                )
                else 0.0
            )

            hiv_status = data.get(
                "hiv_status",
                "unknown",
            )

            marital = data.get(
                "marital_status",
                "single",
            )

        global_importances = {}

        if (
            self.model is not None
            and hasattr(
                self.model,
                "feature_importances_",
            )
        ):
            importances = (
                self.model.feature_importances_
            )

            for index, feature in enumerate(
                self.feature_names
            ):
                global_importances[
                    feature
                ] = float(
                    importances[index]
                )

        elif (
            self.model is not None
            and hasattr(
                self.model,
                "coef_",
            )
        ):
            coefficients = np.abs(
                self.model.coef_[0]
            )

            for index, feature in enumerate(
                self.feature_names
            ):
                global_importances[
                    feature
                ] = float(
                    coefficients[index]
                )

        else:
            global_importances = {
                "age": 0.05,
                "num_partners_12m": 0.25,
                "num_partners_lifetime": 0.10,
                "condom_use_freq": 0.20,
                "substance_use": 0.10,
                "prior_sti_history": 0.15,
                "hiv_positive": 0.10,
                "hiv_unknown": 0.05,
                "symptoms_present": 0.15,
            }

        active_factors = {}

        if num_partners_12m > 0:
            active_factors[
                "num_partners_12m"
            ] = (
                global_importances.get(
                    "num_partners_12m",
                    0,
                )
                * min(
                    num_partners_12m / 5,
                    1.0,
                )
            )

        if num_partners_lifetime > 0:
            active_factors[
                "num_partners_lifetime"
            ] = (
                global_importances.get(
                    "num_partners_lifetime",
                    0,
                )
                * min(
                    num_partners_lifetime / 10,
                    1.0,
                )
            )

        if condom_use_freq < 1:
            active_factors[
                "condom_use_freq"
            ] = (
                global_importances.get(
                    "condom_use_freq",
                    0,
                )
                * (
                    1 - condom_use_freq
                )
            )

        if substance_use:
            active_factors[
                "substance_use"
            ] = global_importances.get(
                "substance_use",
                0,
            )

        if prior_sti_history:
            active_factors[
                "prior_sti_history"
            ] = global_importances.get(
                "prior_sti_history",
                0,
            )

        if symptoms_present:
            active_factors[
                "symptoms_present"
            ] = global_importances.get(
                "symptoms_present",
                0,
            )

        if hiv_status == "positive":
            active_factors[
                "hiv_positive"
            ] = global_importances.get(
                "hiv_positive",
                0,
            )

        if hiv_status == "unknown":
            active_factors[
                "hiv_unknown"
            ] = global_importances.get(
                "hiv_unknown",
                0,
            )

        active_factors = dict(
            sorted(
                active_factors.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        )

        return dict(
            list(
                active_factors.items()
            )[:5]
        )

    def _calculate_likely_stis(
        self,
        patient_data,
    ) -> list:
        """
        Estimate possible STI categories using
        patient characteristics.
        """

        from patients.models import Patient

        if isinstance(
            patient_data,
            Patient,
        ):
            symptoms_present = (
                patient_data.symptoms_present
            )

            prior_sti_history = (
                patient_data.prior_sti_history
            )

            num_partners_12m = (
                patient_data.number_of_partners_12m
            )

            condom_use_freq = (
                patient_data.condom_use_frequency
            )

            hiv_status = (
                patient_data.hiv_status
            )

        else:
            symptoms_present = patient_data.get(
                "symptoms_present",
                False,
            )

            prior_sti_history = patient_data.get(
                "prior_sti_history",
                False,
            )

            num_partners_12m = patient_data.get(
                "number_of_partners_12m",
                0,
            )

            condom_use_freq = patient_data.get(
                "condom_use_frequency",
                1.0,
            )

            hiv_status = patient_data.get(
                "hiv_status",
                "unknown",
            )

        likely_stis = []

        if symptoms_present:
            likely_stis.extend(
                [
                    "Chlamydia",
                    "Gonorrhea",
                ]
            )

        if prior_sti_history:
            likely_stis.append(
                "Syphilis"
            )

        if (
            num_partners_12m > 2
            or condom_use_freq < 0.5
        ):
            likely_stis.extend(
                [
                    "Chlamydia",
                    "Gonorrhea",
                    "Syphilis",
                ]
            )

        if hiv_status == "positive":
            likely_stis.append(
                "Hepatitis B"
            )

        # Remove duplicates
        unique_stis = []

        for sti in likely_stis:
            if sti not in unique_stis:
                unique_stis.append(sti)

        return unique_stis

    def _generate_recommendations(
        self,
        score,
        risk_level,
        patient_data,
    ) -> Dict:
        """
        Generate screening recommendations based
        on the prediction result and patient data.
        """

        from patients.models import Patient

        if isinstance(
            patient_data,
            Patient,
        ):
            symptoms_present = (
                patient_data.symptoms_present
            )

            prior_sti_history = (
                patient_data.prior_sti_history
            )

            condom_use_freq = (
                patient_data.condom_use_frequency
            )

            num_partners_12m = (
                patient_data.number_of_partners_12m
            )

            substance_use = (
                patient_data.substance_use
            )

            hiv_status = (
                patient_data.hiv_status
            )

        else:
            symptoms_present = patient_data.get(
                "symptoms_present",
                False,
            )

            prior_sti_history = patient_data.get(
                "prior_sti_history",
                False,
            )

            condom_use_freq = patient_data.get(
                "condom_use_frequency",
                1.0,
            )

            num_partners_12m = patient_data.get(
                "number_of_partners_12m",
                0,
            )

            substance_use = patient_data.get(
                "substance_use",
                False,
            )

            hiv_status = patient_data.get(
                "hiv_status",
                "unknown",
            )

        tests = [
            "HIV",
            "Syphilis",
        ]

        actions = []

        # Symptom-driven recommendations
        if symptoms_present:

            tests.extend(
                [
                    "Gonorrhea",
                    "Chlamydia",
                ]
            )

            actions.append(
                "Symptom-driven diagnostic screening "
                "recommended."
            )

        # Behavioral factors
        if (
            condom_use_freq < 0.5
            or num_partners_12m > 2
        ):
            if "Gonorrhea" not in tests:
                tests.append(
                    "Gonorrhea"
                )

            if "Chlamydia" not in tests:
                tests.append(
                    "Chlamydia"
                )

            actions.append(
                "Recommend routine screening due to "
                "multiple partners or inconsistent "
                "condom use. Provide risk-reduction "
                "counseling."
            )

        # History and substance use
        if (
            prior_sti_history
            or substance_use
        ):
            tests.append(
                "Hepatitis B"
            )

            actions.append(
                "Recommend Hepatitis B screening and "
                "review vaccination history."
            )

        # High-risk recommendations
        if risk_level in (
            "high",
            "very_high",
        ):
            for test in [
                "Gonorrhea",
                "Chlamydia",
                "Hepatitis B",
                "HPV",
            ]:
                if test not in tests:
                    tests.append(test)

            actions.append(
                "Comprehensive screening is "
                "recommended. Consider prevention "
                "counseling and appropriate follow-up."
            )

        elif risk_level == "moderate":

            actions.append(
                "Follow-up evaluation is recommended."
            )

        else:

            actions.append(
                "Continue routine screening according "
                "to appropriate clinical guidance."
            )

        # Remove duplicates
        unique_tests = []

        for test in tests:
            if test not in unique_tests:
                unique_tests.append(test)

        return {
            "tests": unique_tests,
            "actions": " ".join(actions),
        }


def get_predictor(
    model_name: str = None,
    sti_type: str = "general",
) -> STIPredictor:
    """
    Factory function for creating an STI predictor.
    """

    if model_name is None:
        model_name = "sti_risk_v1"

    return STIPredictor(
        model_name=model_name,
        sti_type=sti_type,
    )