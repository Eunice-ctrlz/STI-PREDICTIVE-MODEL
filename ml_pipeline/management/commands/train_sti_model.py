
import os
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, accuracy_score, f1_score, precision_score, recall_score

from django.conf import settings
from django.core.management.base import BaseCommand

# Must exactly match prediction_engine/ml_model.py's STIPredictor.FEATURE_ORDER
FEATURE_ORDER = [
    'age', 'gender_male', 'gender_female', 'gender_other',
    'num_partners_12m', 'num_partners_lifetime',
    'condom_use_freq', 'substance_use',
    'prior_sti_history', 'hiv_positive', 'hiv_unknown',
    'symptoms_present', 'marital_single', 'marital_married',
    'marital_divorced', 'marital_cohabiting'
]


def generate_synthetic_data(n_samples: int, seed: int = 42):
    """
    Generate a synthetic dataset with genuine, realistic relationships
    between features and STI risk outcome. Prevalence and effect sizes
    are set to roughly match documented epidemiological patterns
    (younger age, higher partner count, low condom use, prior STI
    history, and HIV status all increasing risk).
    """
    rng = np.random.default_rng(seed)

    age = rng.integers(15, 66, n_samples)
    gender = rng.choice(['M', 'F', 'O'], n_samples, p=[0.48, 0.48, 0.04])
    gender_male = (gender == 'M').astype(int)
    gender_female = (gender == 'F').astype(int)
    gender_other = (gender == 'O').astype(int)

    num_partners_12m = rng.poisson(1.2, n_samples)
    num_partners_lifetime = num_partners_12m + rng.poisson(2.5, n_samples)
    condom_use_freq = np.clip(rng.beta(2, 2, n_samples), 0, 1)
    substance_use = rng.binomial(1, 0.15, n_samples)
    prior_sti_history = rng.binomial(1, 0.12, n_samples)

    hiv_roll = rng.random(n_samples)
    hiv_positive = (hiv_roll < 0.06).astype(int)
    hiv_unknown = ((hiv_roll >= 0.06) & (hiv_roll < 0.20)).astype(int)

    symptoms_present = rng.binomial(1, 0.18, n_samples)

    marital = rng.choice(['single', 'married', 'divorced', 'cohabiting'],
                          n_samples, p=[0.4, 0.4, 0.1, 0.1])
    marital_single = (marital == 'single').astype(int)
    marital_married = (marital == 'married').astype(int)
    marital_divorced = (marital == 'divorced').astype(int)
    marital_cohabiting = (marital == 'cohabiting').astype(int)

    # True risk logit - deliberately encodes real behavioural/clinical
    # risk relationships so the trained model has genuine signal to learn.
    z = (
        -2.5
        - 0.03 * (age - 25)
        + 0.35 * num_partners_12m
        + 0.05 * num_partners_lifetime
        - 2.2 * condom_use_freq
        + 1.0 * substance_use
        + 1.6 * prior_sti_history
        + 1.3 * hiv_positive
        + 0.4 * hiv_unknown
        + 1.9 * symptoms_present
        + 0.3 * marital_single
        + 0.3 * marital_cohabiting
        + 0.15 * marital_divorced
        - 0.3 * marital_married
        + rng.normal(0, 0.5, n_samples)  # unexplained variance / noise
    )
    p = 1 / (1 + np.exp(-z))
    y = rng.binomial(1, p)

    X = pd.DataFrame({
        'age': age,
        'gender_male': gender_male, 'gender_female': gender_female, 'gender_other': gender_other,
        'num_partners_12m': num_partners_12m, 'num_partners_lifetime': num_partners_lifetime,
        'condom_use_freq': condom_use_freq, 'substance_use': substance_use,
        'prior_sti_history': prior_sti_history, 'hiv_positive': hiv_positive, 'hiv_unknown': hiv_unknown,
        'symptoms_present': symptoms_present,
        'marital_single': marital_single, 'marital_married': marital_married,
        'marital_divorced': marital_divorced, 'marital_cohabiting': marital_cohabiting,
    })[FEATURE_ORDER]

    return X, pd.Series(y, name='sti_risk')


class Command(BaseCommand):
    help = "Train the STI risk classifier and save it for use by prediction_engine.ml_model"

    def add_arguments(self, parser):
        parser.add_argument('--samples', type=int, default=8000,
                             help='Number of synthetic training rows to generate (default: 8000)')
        parser.add_argument('--model-name', type=str, default='sti_risk_v1',
                             help='Model directory name under MEDIA_ROOT/models/ (default: sti_risk_v1)')
        parser.add_argument('--seed', type=int, default=42, help='Random seed for reproducibility')

    def handle(self, *args, **options):
        n_samples = options['samples']
        model_name = options['model_name']
        seed = options['seed']

        if not getattr(settings, 'MEDIA_ROOT', None):
            self.stderr.write(self.style.ERROR(
                "settings.MEDIA_ROOT is not set. Add MEDIA_ROOT = BASE_DIR / 'media' "
                "to settings.py before running this command."
            ))
            return

        self.stdout.write(f"Generating {n_samples} synthetic training rows...")
        X, y = generate_synthetic_data(n_samples, seed=seed)
        self.stdout.write(f"Class balance (positive rate): {y.mean():.3f}")

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=seed, stratify=y
        )

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        self.stdout.write("Training RandomForestClassifier...")
        clf = RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            class_weight='balanced',
            random_state=seed,
        )
        clf.fit(X_train_scaled, y_train)

        proba = clf.predict_proba(X_test_scaled)[:, 1]
        pred = clf.predict(X_test_scaled)

        metrics = {
            'auc_roc': round(float(roc_auc_score(y_test, proba)), 4),
            'accuracy': round(float(accuracy_score(y_test, pred)), 4),
            'f1_score': round(float(f1_score(y_test, pred)), 4),
            'precision': round(float(precision_score(y_test, pred)), 4),
            'recall': round(float(recall_score(y_test, pred)), 4),
        }
        self.stdout.write(self.style.SUCCESS(f"Test metrics: {metrics}"))

        # Sanity check: confirm the model actually discriminates between
        # a clearly low-risk and clearly high-risk profile before saving.
        low_risk = pd.DataFrame([{
            'age': 45, 'gender_male': 1, 'gender_female': 0, 'gender_other': 0,
            'num_partners_12m': 0, 'num_partners_lifetime': 1,
            'condom_use_freq': 1.0, 'substance_use': 0,
            'prior_sti_history': 0, 'hiv_positive': 0, 'hiv_unknown': 0,
            'symptoms_present': 0, 'marital_single': 0, 'marital_married': 1,
            'marital_divorced': 0, 'marital_cohabiting': 0,
        }])[FEATURE_ORDER]

        high_risk = pd.DataFrame([{
            'age': 19, 'gender_male': 0, 'gender_female': 1, 'gender_other': 0,
            'num_partners_12m': 10, 'num_partners_lifetime': 20,
            'condom_use_freq': 0.0, 'substance_use': 1,
            'prior_sti_history': 1, 'hiv_positive': 1, 'hiv_unknown': 0,
            'symptoms_present': 1, 'marital_single': 1, 'marital_married': 0,
            'marital_divorced': 0, 'marital_cohabiting': 0,
        }])[FEATURE_ORDER]

        low_proba = clf.predict_proba(scaler.transform(low_risk))[0][1]
        high_proba = clf.predict_proba(scaler.transform(high_risk))[0][1]
        self.stdout.write(f"Sanity check — low-risk profile proba: {low_proba:.4f}")
        self.stdout.write(f"Sanity check — high-risk profile proba: {high_proba:.4f}")

        if high_proba - low_proba < 0.15:
            self.stdout.write(self.style.WARNING(
                "Warning: the gap between low- and high-risk predictions is small. "
                "The model may not be discriminating well. Review before deploying."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                "Model discriminates correctly between contrasting risk profiles."
            ))

        # Save artifacts to MEDIA_ROOT/models/<model_name>/ — this is exactly
        # where prediction_engine/ml_model.py's STIPredictor looks for them.
        model_dir = os.path.join(settings.MEDIA_ROOT, 'models', model_name)
        os.makedirs(model_dir, exist_ok=True)

        joblib.dump(clf, os.path.join(model_dir, 'model.joblib'))
        joblib.dump(scaler, os.path.join(model_dir, 'scaler.joblib'))

        metadata = {
            'model_type': 'Random Forest Classifier',
            'feature_names': FEATURE_ORDER,
            'trained_at': datetime.now(timezone.utc).isoformat(),
            'training_samples': n_samples,
            'data_source': 'synthetic (placeholder — replace with KDHS Individual Recode once approved)',
            'test_metrics': metrics,
        }
        with open(os.path.join(model_dir, 'metadata.json'), 'w') as f:
            json.dump(metadata, f, indent=2)

        # Record the run in the MLModel registry so the ML Models page shows
        # these artifacts and their real metrics, not a stale hand-written row.
        from ml_pipeline.registry import register_model
        registered, created = register_model(model_name)
        self.stdout.write(self.style.SUCCESS(
            f"{'Registered' if created else 'Updated'} registry entry: "
            f"{registered.name} v{registered.version}"
        ))

        self.stdout.write(self.style.SUCCESS(
            f"\nModel saved to: {model_dir}\n"
            f"  - model.joblib\n"
            f"  - scaler.joblib\n"
            f"  - metadata.json\n\n"
            f"Restart the Django dev server, then retry a prediction — "
            f"scores should now vary meaningfully by patient."
        ))