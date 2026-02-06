from __future__ import annotations

import io
from pathlib import Path
from PIL import Image, ImageOps


def generate_variant_bytes(
    *,
    src_bytes: bytes,
    max_dim: int,
    out_format: str = "WEBP",
    quality: int = 82,
) -> tuple[bytes, int, int, str]:
    """
    Returns (bytes, width, height, mime_type).
    """
    out_format = out_format.upper().strip()

    with Image.open(io.BytesIO(src_bytes)) as im:
        # Respect EXIF orientation
        im = ImageOps.exif_transpose(im)

        # Preserve alpha if present
        has_alpha = ("A" in im.getbands())
        if has_alpha:
            im = im.convert("RGBA")
        else:
            im = im.convert("RGB")

        # Resize in-place keeping aspect ratio
        # thumbnail uses high-quality downsampling with a resample filter
        im.thumbnail((max_dim, max_dim), resample=Image.Resampling.LANCZOS)
        w, h = im.size

        out = io.BytesIO()
        if out_format == "WEBP":
            im.save(out, format="WEBP", quality=quality, method=6)
            mime = "image/webp"
        elif out_format in ("JPEG", "JPG"):
            if has_alpha:
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                im = bg
            im.save(out, format="JPEG", quality=quality, optimize=True)
            mime = "image/jpeg"
        else:
            im.save(out, format=out_format)
            mime = "application/octet-stream"

        return out.getvalue(), w, h, mime
    

def _encode_variant(
    *,
    im: Image.Image,
    out_format: str,
    quality: int,
    had_alpha: bool,
) -> tuple[bytes, str]:
    out = io.BytesIO()
    fmt = out_format.upper().strip()

    if fmt == "WEBP":
        im.save(out, format="WEBP", quality=quality, method=6)
        return out.getvalue(), "image/webp"

    if fmt in ("JPEG", "JPG"):
        if had_alpha:
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        im.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue(), "image/jpeg"

    im.save(out, format=fmt)
    return out.getvalue(), "application/octet-stream"


def generate_variant_from_path(
    *,
    src_path: Path,
    max_dim: int,
    out_format: str = "WEBP",
    quality: int = 82,
) -> tuple[bytes, int, int, str]:
    """
    Returns (bytes, width, height, mime_type).
    Avoids reading the full source file into memory first.
    """
    with Image.open(src_path) as im:
        im = ImageOps.exif_transpose(im)

        had_alpha = ("A" in im.getbands())
        im = im.convert("RGBA" if had_alpha else "RGB")

        im.thumbnail((max_dim, max_dim), resample=Image.Resampling.LANCZOS)
        w, h = im.size

        data, mime = _encode_variant(im=im, out_format=out_format, quality=quality, had_alpha=had_alpha)
        return data, w, h, mime
