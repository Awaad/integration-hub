from __future__ import annotations
from dataclasses import dataclass
from zipfile import Path

@dataclass(frozen=True)
class StoredObject:
    backend: str
    key: str
    byte_size: int

class MediaStorage:
    async def put_bytes(
        self,
        *,
        tenant_id: str,
        partner_id: str,
        agent_id: str,
        content_hash: str,
        data: bytes,
        ext: str,
    ) -> StoredObject:
        raise NotImplementedError
    
    async def put_file(
            self,
            *, 
            tenant_id: str, 
            partner_id: str,
            agent_id: str,
            content_hash: str, 
            file_path: Path,
            ext: str,
            byte_size: int,
            ) -> StoredObject:
        raise NotImplementedError

    async def exists(self, *, backend: str, key: str) -> bool:
        raise NotImplementedError
