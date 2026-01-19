from __future__ import annotations
from pathlib import Path
from urllib.parse import urlparse


class LocalObjectStore:
    def __init__(self, base_dir: str):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, *, key: str, data: bytes) -> str:
        path = self.base / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"file://{path.as_posix()}"
    
    def resolve_path(self, uri: str) -> Path:
        """
        Resolve a storage URI to a local filesystem path.

        Supports:
          - file:///absolute/path
          - absolute filesystem paths
          - relative keys (resolved under self.base)
        """
        parsed = urlparse(uri)

        if parsed.scheme == "file":
            return Path(parsed.path)

        if parsed.scheme == "":
            p = Path(uri)
            if p.is_absolute():
                return p
            return self.base / p

        raise ValueError(f"Unsupported storage scheme: {parsed.scheme}")
