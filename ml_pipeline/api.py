from ninja import Router
from django.http import Http404
from django.shortcuts import get_object_or_404
from typing import List
from .models import MLModel, TrainingJob

router = Router(tags=["ML Pipeline"])


def _values_or_404(qs, **lookup):
    """Return a single row as a plain dict, or raise 404.

    The detail routes have no response schema, so returning a model instance
    makes django-ninja's JSON renderer fail with "Object of type X is not JSON
    serializable". Using .values() keeps them on the same dict shape the
    matching list route already returns.
    """
    row = qs.filter(**lookup).values().first()
    if row is None:
        raise Http404("Not found")
    return row


@router.get("/models")
def list_models(request, status: str = None):
    qs = MLModel.objects.all()
    if status:
        qs = qs.filter(status=status)
    return list(qs.values().order_by('-created_at'))


@router.get("/models/{model_id}")
def get_model(request, model_id: int):
    return _values_or_404(MLModel.objects.all(), id=model_id)


@router.post("/models/{model_id}/deploy")
def deploy_model(request, model_id: int):
    model = get_object_or_404(MLModel, id=model_id, status='ready')
    # Undeploy current default
    MLModel.objects.filter(name=model.name, is_default=True).update(is_default=False, status='deprecated')
    model.is_default = True
    model.status = 'deployed'
    model.save()
    return {"success": True, "message": f"Model {model.name} v{model.version} deployed"}


@router.get("/jobs")
def list_training_jobs(request, status: str = None):
    qs = TrainingJob.objects.all()
    if status:
        qs = qs.filter(status=status)
    return list(qs.values().order_by('-created_at')[:20])


@router.get("/jobs/{job_id}")
def get_training_job(request, job_id: int):
    return _values_or_404(TrainingJob.objects.all(), id=job_id)