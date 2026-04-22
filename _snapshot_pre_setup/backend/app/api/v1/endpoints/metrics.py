from fastapi import APIRouter

from ....core.metrics import metrics_singleton


router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
def metrics():
    return metrics_singleton.summary()
