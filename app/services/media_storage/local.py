from __future__ import annotations

import errno
import os
import re
from pathlib import Path
import shutil
import uuid
import anyio

from app.services.media_storage.base import MediaStorage, StoredObject


_SAFE_EXT_RE = re.compile(r"^[a-z0-9]{1,8}$")


def _safe_join(base: Path, key: str) -> Path:
    b = base.resolve()
    p = (b / key).resolve()
    try:
        if not p.is_relative_to(b):
            raise ValueError("invalid key/path traversal")
    except AttributeError:
        # fallback for older versions
        if not str(p).startswith(str(b) + os.sep):
            raise ValueError("invalid key/path traversal")
    return p

def _normalize_ext(ext: str) -> str:
    e = (ext or "").lower().strip()
    if e.startswith("."):
        e = e[1:]
    if not _SAFE_EXT_RE.match(e):
        raise ValueError(f"invalid ext: {ext!r}")
    return e


class LocalMediaStorage(MediaStorage):
    def __init__(self, base_dir: str = "var/media"):
        self.base_dir = Path(base_dir)


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
        ext_norm = _normalize_ext(ext)

        key = f"{tenant_id}/{partner_id}/{agent_id}/{content_hash}.{ext_norm}"
        dest = _safe_join(self.base_dir, key)

        def _move_or_copy_if_missing() -> int:
            dest.parent.mkdir(parents=True, exist_ok=True)

            if dest.exists():
                # file already present (dedupe)
                try:
                    file_path.unlink()
                except FileNotFoundError:
                    pass
                return dest.stat().st_size

            # Try atomic move 
            try:
                os.replace(str(file_path), str(dest))
                return dest.stat().st_size
            except OSError as e:
                if e.errno != errno.EXDEV:
                    raise

            # Cross-device: copy into temp file in destination dir, then atomic replace
            tmp = dest.with_name(dest.name + f".{uuid.uuid4().hex}.tmp")
            try:
                with open(file_path, "rb") as src, open(tmp, "wb") as out:
                    shutil.copyfileobj(src, out, length=1024 * 1024)
                    out.flush()
                    os.fsync(out.fileno())

                os.replace(str(tmp), str(dest))
            finally:
                try:
                    if tmp.exists():
                        tmp.unlink()
                except Exception:
                    pass
                try:
                    if file_path.exists():
                        file_path.unlink()
                except Exception:
                    pass

            return dest.stat().st_size

        written = await anyio.to_thread.run_sync(_move_or_copy_if_missing)
        return StoredObject(backend="local", key=key, byte_size=int(written))


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
        ext_norm = _normalize_ext(ext)

        # Key format stays stable and portable.
        key = f"{tenant_id}/{partner_id}/{agent_id}/{content_hash}.{ext_norm}"
        path = _safe_join(self.base_dir, key)

        def _write_if_missing() -> int:
            path.parent.mkdir(parents=True, exist_ok=True)

            if path.exists():
                return path.stat().st_size

            tmp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
            with open(tmp, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())

            # Atomic replace (safe even if another worker wrote first)
            try:
                os.replace(tmp, path)
            finally:
                # Cleanup if replace failed for some reason
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except Exception:
                        pass

            return path.stat().st_size

        byte_size = await anyio.to_thread.run_sync(_write_if_missing)
        return StoredObject(backend="local", key=key, byte_size=int(byte_size))

    async def exists(self, *, backend: str, key: str) -> bool:
        if backend != "local":
            return False

        path = _safe_join(self.base_dir, key)

        def _exists() -> bool:
            return path.exists()

        return await anyio.to_thread.run_sync(_exists)
