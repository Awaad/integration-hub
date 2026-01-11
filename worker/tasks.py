from worker.celery_app import celery

@celery.task(name="worker.tasks.process_outbox_event", bind=True, max_retries=5)
def process_outbox_event(self, outbox_id: str) -> None:
    # Phase 0: just prove the pipeline works.
    # Phase 1+: fetch outbox record, transform, route, publish, reconcile.
    print(f"[outbox] received event id={outbox_id}")
