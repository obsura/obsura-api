"""OCR provider contracts and backend builders."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import TYPE_CHECKING, Protocol

from obsura_api.domain.common import BoundingBox

if TYPE_CHECKING:
    from obsura_api.core.settings import Settings


@dataclass(slots=True)
class OCRToken:
    """One OCR token with its own bounding box."""

    text: str
    region: BoundingBox
    confidence: float


@dataclass(slots=True)
class OCRBlock:
    """Text extracted from an image by an OCR engine."""

    text: str
    region: BoundingBox
    confidence: float
    tokens: list[OCRToken] = field(default_factory=list)


class OCRProvider(Protocol):
    """Protocol for OCR providers used by image workflows."""

    name: str
    supported: bool

    def extract_text(self, image_bytes: bytes) -> list[OCRBlock]:
        """Return OCR text blocks from an image."""


class NoOpOCRProvider:
    """Default OCR provider that makes lack of OCR support explicit."""

    name = "noop-ocr"
    supported = False

    def extract_text(self, image_bytes: bytes) -> list[OCRBlock]:
        return []


class TesseractOCRProvider:
    """Tesseract-backed OCR provider that returns line-level blocks."""

    name = "tesseract-ocr"
    supported = True

    def __init__(self, *, language: str = "eng") -> None:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError(
                "Tesseract OCR requires the `pytesseract` package.",
            ) from exc

        self.pytesseract = pytesseract
        self.image_class = Image
        self.language = language

    def extract_text(self, image_bytes: bytes) -> list[OCRBlock]:
        image = self.image_class.open(BytesIO(image_bytes)).convert("RGB")
        data = self.pytesseract.image_to_data(
            image,
            lang=self.language,
            output_type=self.pytesseract.Output.DICT,
        )

        grouped_tokens: dict[tuple[int, int, int, int], list[OCRToken]] = {}
        item_count = len(data.get("text", []))
        for index in range(item_count):
            text = (data["text"][index] or "").strip()
            if not text:
                continue

            confidence = self._normalize_confidence(data["conf"][index])
            token = OCRToken(
                text=text,
                region=BoundingBox(
                    x=int(data["left"][index]),
                    y=int(data["top"][index]),
                    width=int(data["width"][index]),
                    height=int(data["height"][index]),
                ),
                confidence=confidence,
            )
            key = (
                int(data["page_num"][index]),
                int(data["block_num"][index]),
                int(data["par_num"][index]),
                int(data["line_num"][index]),
            )
            grouped_tokens.setdefault(key, []).append(token)

        blocks: list[OCRBlock] = []
        for key in sorted(grouped_tokens):
            tokens = sorted(grouped_tokens[key], key=lambda item: item.region.x)
            block_text = " ".join(token.text for token in tokens).strip()
            if not block_text:
                continue
            block_region = _combine_regions(token.region for token in tokens)
            average_confidence = sum(token.confidence for token in tokens) / len(tokens)
            blocks.append(
                OCRBlock(
                    text=block_text,
                    region=block_region,
                    confidence=average_confidence,
                    tokens=tokens,
                ),
            )
        return blocks

    def _normalize_confidence(self, raw_value: object) -> float:
        try:
            numeric = float(raw_value)
        except (TypeError, ValueError):
            return 0.0
        if numeric < 0:
            return 0.0
        return min(1.0, numeric / 100.0)


def _combine_regions(regions: object) -> BoundingBox:
    items = list(regions)
    if not items:
        return BoundingBox(x=0, y=0, width=0, height=0)

    left = min(item.x for item in items)
    top = min(item.y for item in items)
    right = max(item.x + item.width for item in items)
    bottom = max(item.y + item.height for item in items)
    return BoundingBox(
        x=left,
        y=top,
        width=right - left,
        height=bottom - top,
    )


def build_ocr_provider(settings: Settings) -> OCRProvider:
    """Build the configured OCR provider backend."""

    backend = settings.ocr_backend.strip().lower()
    if backend in {"", "noop", "none", "disabled"}:
        return NoOpOCRProvider()
    if backend in {"tesseract", "pytesseract"}:
        return TesseractOCRProvider(language=settings.ocr_language)
    raise RuntimeError(f"Unsupported OCR backend `{settings.ocr_backend}`.")
