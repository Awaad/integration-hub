from pydantic import BaseModel


class PartnerCreate(BaseModel):
    tenant_name: str
    partner_name: str


class PartnerBootstrapOut(BaseModel):
    tenant_id: str
    partner_id: str
    partner_admin_api_key: str


class PartnerRotateKeyOut(BaseModel):
    tenant_id: str
    partner_id: str
    partner_admin_api_key: str