"""
Keeps the MLModel table in sync with the model artifacts on disk.

prediction_engine.ml_model loads models straight from
MEDIA_ROOT/models/<name>/, so without this the registry stays empty and
/api/ml/models returns nothing even though a trained model is serving
live predictions.
"""
import json
import os

from django.conf import settings
from django.utils import timezone

from .models import MLModel

MODELS_SUBDIR = 'models'

# metadata.json records a human label; MLModel.model_type wants a choice key.
MODEL_TYPE_MAP = {
    'random forest classifier': 'random_forest',
    'random forest': 'random_forest',
    'logistic regression': 'logistic_regression',
    'xgboost': 'xgboost',
    'lightgbm': 'lightgbm',
    'neural network': 'neural_network',
    'support vector machine': 'svm',
}

DEFAULT_VERSION = '1.0.0'


def _model_type_key(label):
    return MODEL_TYPE_MAP.get((label or '').strip().lower(), 'random_forest')


def _relative(model_name, filename):
    """Path relative to MEDIA_ROOT, which is what a FileField stores."""
    return f'{MODELS_SUBDIR}/{model_name}/{filename}'


def model_dir(model_name):
    return os.path.join(settings.MEDIA_ROOT, MODELS_SUBDIR, model_name)


def discover_model_dirs():
    """Every directory under MEDIA_ROOT/models/ that holds a model.joblib."""
    root = os.path.join(settings.MEDIA_ROOT, MODELS_SUBDIR)
    if not os.path.isdir(root):
        return []
    return sorted(
        name for name in os.listdir(root)
        if os.path.isfile(os.path.join(root, name, 'model.joblib'))
    )


def register_model(model_name, make_default=None):
    """
    Create or update the MLModel row describing the artifacts in
    MEDIA_ROOT/models/<model_name>/. Returns (instance, created).

    Metrics come from metadata.json, so the registry always reports what the
    model actually scored rather than a figure typed in by hand.
    """
    directory = model_dir(model_name)
    model_path = os.path.join(directory, 'model.joblib')
    if not os.path.isfile(model_path):
        raise FileNotFoundError(f'No model.joblib in {directory}')

    metadata = {}
    metadata_path = os.path.join(directory, 'metadata.json')
    if os.path.isfile(metadata_path):
        with open(metadata_path) as fh:
            metadata = json.load(fh)

    metrics = metadata.get('test_metrics', {})
    version = str(metadata.get('version') or DEFAULT_VERSION)

    trained_at = None
    if metadata.get('trained_at'):
        trained_at = timezone.datetime.fromisoformat(metadata['trained_at'])
        if timezone.is_naive(trained_at):
            trained_at = timezone.make_aware(trained_at)

    has_scaler = os.path.isfile(os.path.join(directory, 'scaler.joblib'))

    defaults = {
        'model_type': _model_type_key(metadata.get('model_type')),
        'description': metadata.get('data_source', ''),
        'model_file': _relative(model_name, 'model.joblib'),
        'scaler_file': _relative(model_name, 'scaler.joblib') if has_scaler else None,
        'metadata_file': _relative(model_name, 'metadata.json') if metadata else None,
        'test_auc_roc': metrics.get('auc_roc'),
        'test_f1': metrics.get('f1_score'),
        'validation_accuracy': metrics.get('accuracy'),
        'training_data_size': metadata.get('training_samples'),
        'training_completed_at': trained_at,
        'hyperparameters': metadata.get('hyperparameters', {}),
        'status': 'deployed',
        'created_by': 'train_sti_model',
    }

    instance, created = MLModel.objects.update_or_create(
        name=model_name, version=version, defaults=defaults,
    )

    # First model registered becomes the default unless told otherwise.
    if make_default is None:
        make_default = not MLModel.objects.filter(is_default=True).exclude(pk=instance.pk).exists()
    if make_default and not instance.is_default:
        MLModel.objects.exclude(pk=instance.pk).update(is_default=False)
        instance.is_default = True
        instance.save(update_fields=['is_default'])

    return instance, created
