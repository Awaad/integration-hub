from pydantic import BaseModel, Field


class IdResponse(BaseModel):
    id: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: list[dict] = Field(default_factory=list)
