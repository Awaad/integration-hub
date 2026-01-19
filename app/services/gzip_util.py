from __future__ import annotations
import gzip
from io import BytesIO

def gzip_bytes(data: bytes, *, compresslevel: int = 6) -> bytes:
    buf = BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=compresslevel) as f:
        f.write(data)
    return buf.getvalue()
