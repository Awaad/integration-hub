import uuid

def gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
