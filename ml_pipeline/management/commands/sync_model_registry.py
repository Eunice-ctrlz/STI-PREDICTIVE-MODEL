"""
Register every trained model already sitting in MEDIA_ROOT/models/ into the
MLModel table, so the ML Models page and /api/ml/models reflect reality.

Safe to re-run: existing rows are updated in place.
"""
from django.core.management.base import BaseCommand

from ml_pipeline.registry import discover_model_dirs, register_model


class Command(BaseCommand):
    help = "Sync on-disk model artifacts into the MLModel registry"

    def add_arguments(self, parser):
        parser.add_argument(
            '--model-name', type=str, default=None,
            help='Register only this model directory (default: all discovered)',
        )

    def handle(self, *args, **options):
        names = [options['model_name']] if options['model_name'] else discover_model_dirs()

        if not names:
            self.stdout.write(self.style.WARNING(
                'No model artifacts found under MEDIA_ROOT/models/. '
                'Run "manage.py train_sti_model" first.'
            ))
            return

        for name in names:
            try:
                instance, created = register_model(name)
            except FileNotFoundError as exc:
                self.stderr.write(self.style.ERROR(str(exc)))
                continue

            verb = 'Registered' if created else 'Updated'
            default_note = ' [default]' if instance.is_default else ''
            self.stdout.write(self.style.SUCCESS(
                f'{verb} {instance.name} v{instance.version}{default_note} — '
                f'AUC {instance.test_auc_roc}, F1 {instance.test_f1}'
            ))
