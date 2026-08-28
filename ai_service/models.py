from django.db import models

from prediction_engine.models import RiskPrediction


class PredictionExplanation(models.Model):
    """
    An AI-generated explanation of one RiskPrediction.

    Stored rather than regenerated for three reasons: re-opening a result page
    should not re-bill a provider call, the explanation shown to a clinician
    should not silently change between views, and a clinical tool should be
    able to show exactly what AI-generated text was displayed at a given time.

    The relationship is one-to-one and CASCADE: an explanation has no meaning
    without its prediction. The dependency points this way only -- nothing in
    prediction_engine imports this model, so the ML path is unaffected by its
    presence or absence.
    """

    prediction = models.OneToOneField(
        RiskPrediction,
        on_delete=models.CASCADE,
        related_name='ai_explanation',
    )

    # Generated content, mirroring the API response fields.
    summary = models.TextField()
    what_this_means = models.TextField()
    important_considerations = models.JSONField(default=list)
    recommended_next_steps = models.JSONField(default=list)

    # Provenance. Recorded so a stored explanation can always be traced to the
    # provider and model that produced it. Never stores credentials.
    provider = models.CharField(max_length=50)
    model_identifier = models.CharField(max_length=100)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'AI prediction explanation'
        verbose_name_plural = 'AI prediction explanations'

    def __str__(self):
        return f'AI explanation for prediction {self.prediction_id} ({self.provider})'
