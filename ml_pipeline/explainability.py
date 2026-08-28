from typing import Any, Dict, List

import numpy as np
import shap


class ModelExplainer:
    def __init__(self, model, feature_names: List[str]):
        self.model = model
        self.feature_names = feature_names
        self.explainer = shap.TreeExplainer(model)

    def explain(self, X) -> Dict[str, Any]:
        try:
            shap_values = self.explainer.shap_values(X)

            values = self._get_positive_class_values(shap_values)
            values = np.asarray(values)

            # Ensure we have one patient's feature contributions.
            if values.ndim == 2:
                values = values[0]

            contributions = []

            for feature, value in zip(self.feature_names, values):
                value = float(value)

                contributions.append({
                    "feature": feature,
                    "contribution": round(value, 6),
                    "absolute_contribution": round(abs(value), 6),
                })

            positive = [
                item for item in contributions
                if item["contribution"] > 0
            ]

            negative = [
                item for item in contributions
                if item["contribution"] < 0
            ]

            positive.sort(
                key=lambda item: item["contribution"],
                reverse=True
            )

            negative.sort(
                key=lambda item: abs(item["contribution"]),
                reverse=True
            )

            return {
                "positive_contributors": positive[:5],
                "negative_contributors": negative[:5],
                "method": "SHAP",
            }

        except Exception as error:
            return {
                "positive_contributors": [],
                "negative_contributors": [],
                "method": "SHAP_FAILED",
                "error": str(error),
            }

    @staticmethod
    def _get_positive_class_values(shap_values):
        if isinstance(shap_values, list):
            # Older SHAP versions.
            return shap_values[1] if len(shap_values) > 1 else shap_values[0]

        shap_values = np.asarray(shap_values)

        # Newer SHAP versions may return:
        # (samples, features, classes)
        if shap_values.ndim == 3:
            return shap_values[:, :, 1]

        return shap_values