"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/ai/image_payload.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Opus 5.5
Description:    Normalizes the heterogeneous image payloads produced by the
                pipeline stages (base64 dicts, PIL images, raw bytes, mixed
                lists with text labels) into ordered text/image parts with
                downscaled PNG base64 data for local vision backends.
------------------------------------------------------------------------------
"""

import base64
import binascii
import io
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from PIL import Image, UnidentifiedImageError

from core.logger import get_logger

logger = get_logger("ai.images")

DEFAULT_MAX_IMAGE_PX: int = 1600


@dataclass
class PayloadPart:
    """
    One ordered element of a multimodal request.

    Attributes:
        kind: "text" or "image".
        value: Text content, or PNG image data as base64 string.
    """

    kind: str
    value: str


def _fit_image(img: Image.Image, max_px: int) -> Image.Image:
    """
    Downscales an image so that its long side is at most ``max_px``.

    Args:
        img: Source image.
        max_px: Maximum long-side length in pixels (<= 0 disables scaling).

    Returns:
        The (possibly) resized image in a PNG-compatible mode.
    """
    if img.mode not in ("RGB", "L", "RGBA"):
        img = img.convert("RGB")
    long_side = max(img.size)
    if max_px > 0 and long_side > max_px:
        scale = max_px / long_side
        new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    return img


def pil_to_png_base64(img: Image.Image, max_px: int = DEFAULT_MAX_IMAGE_PX) -> str:
    """
    Encodes a PIL image as downscaled PNG base64.

    Args:
        img: Source image.
        max_px: Maximum long-side length in pixels.

    Returns:
        Base64 encoded PNG data (no data-URL prefix).
    """
    buffer = io.BytesIO()
    _fit_image(img, max_px).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _bytes_to_png_base64(data: bytes, max_px: int) -> Optional[str]:
    """Decodes image bytes with PIL and re-encodes them as fitted PNG base64."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            return pil_to_png_base64(img, max_px)
    except (UnidentifiedImageError, OSError, ValueError) as e:
        logger.warning(f"Skipping undecodable image bytes ({len(data)} bytes): {e}")
        return None


def _base64_dict_to_png_base64(b64: str, max_px: int) -> str:
    """
    Ensures a base64 payload respects the size limit. Data that already fits
    (or cannot be decoded) is passed through unchanged.
    """
    try:
        raw = base64.b64decode(b64, validate=False)
        with Image.open(io.BytesIO(raw)) as img:
            if max_px <= 0 or max(img.size) <= max_px:
                return b64
            img.load()
            return pil_to_png_base64(img, max_px)
    except (binascii.Error, UnidentifiedImageError, OSError, ValueError) as e:
        logger.debug(f"Passing base64 image through unchanged (not decodable here): {e}")
        return b64


def normalize_payload(images: Optional[Any], max_px: int = DEFAULT_MAX_IMAGE_PX) -> List[PayloadPart]:
    """
    Converts an arbitrary image payload into ordered parts.

    Accepted items (a single item or a list of items):
        - ``{"base64": str, ...}`` dicts (Stage 2)
        - ``{"image": PIL.Image, "label": str}`` dicts
        - ``PIL.Image.Image`` objects (Stage 1.5)
        - ``bytes`` / ``bytearray`` containing an encoded image
        - ``str`` items, kept as text parts (e.g. image labels)

    Args:
        images: The payload.
        max_px: Maximum long-side length for images in pixels.

    Returns:
        Ordered list of PayloadPart objects.
    """
    if images is None:
        return []
    items = images if isinstance(images, (list, tuple)) else [images]
    parts: List[PayloadPart] = []

    for item in items:
        if item is None:
            continue
        if isinstance(item, str):
            if item.strip():
                parts.append(PayloadPart("text", item))
        elif isinstance(item, Image.Image):
            parts.append(PayloadPart("image", pil_to_png_base64(item, max_px)))
        elif isinstance(item, (bytes, bytearray)):
            encoded = _bytes_to_png_base64(bytes(item), max_px)
            if encoded:
                parts.append(PayloadPart("image", encoded))
        elif isinstance(item, dict) and item.get("base64"):
            parts.append(PayloadPart("image", _base64_dict_to_png_base64(str(item["base64"]), max_px)))
        elif isinstance(item, dict) and isinstance(item.get("image"), Image.Image):
            if item.get("label"):
                parts.append(PayloadPart("text", f"[IMAGE CONTEXT: {item['label']}]"))
            parts.append(PayloadPart("image", pil_to_png_base64(item["image"], max_px)))
        else:
            logger.warning(f"Ignoring unsupported image payload item of type {type(item).__name__}")
    return parts


def split_payload(parts: List[PayloadPart]) -> Tuple[List[str], List[str]]:
    """
    Splits ordered parts into text fragments and image data (for backends
    that cannot interleave text and images, e.g. Ollama).

    Args:
        parts: Ordered parts.

    Returns:
        Tuple (list of text fragments, list of base64 images).
    """
    texts = [p.value for p in parts if p.kind == "text"]
    images = [p.value for p in parts if p.kind == "image"]
    return texts, images
