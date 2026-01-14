from celery import Celery
from app.core.config import settings
import worker.tasks  # noqa
import worker.tasks_publish  # noqa

celery = Celery(
    "hub-worker",
    broker=settings.rabbitmq_url,
    backend=settings.redis_url,
    include=["worker.tasks"],
)

celery.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_routes={
        "worker.tasks.process_outbox_event": {"queue": "outbox"},
        "worker.tasks.publish_delivery": {"queue": "publish"},
    },
)
