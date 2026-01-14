from pydantic import BaseModel

class DeliveryOut(BaseModel):
    id: str
    listing_id: str
    agent_id: str
    destination: str
    status: str
    attempts: int
    last_error: str | None
    status_detail: str | None
    dead_lettered_at: str | None

class DeliveryAttemptOut(BaseModel):
    id: str
    delivery_id: str
    status: str
    error_code: str | None
    error_message: str | None
    request: dict
    response: dict
    created_at: str
