from pydantic import BaseModel

class IngestReplayResponse(BaseModel):
    ok: bool
    ingest_run_id: str
    replay_ingest_run_id: str | None = None
    adapter_version: str
    normalized: dict | None = None
    content_hash: str | None = None
    errors: list[dict] = []
