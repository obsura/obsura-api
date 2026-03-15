"""Document extraction provider contracts and backend builders."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from obsura_api.core.settings import Settings

from obsura_api.domain.errors import (
    BadRequestError,
    PayloadTooLargeError,
    UnprocessableContentError,
)


@dataclass(slots=True)
class ExtractedDocumentPage:
    """One extracted PDF page."""

    page_number: int
    text: str


@dataclass(slots=True)
class ExtractedDocument:
    """Text extracted from a PDF document."""

    pages: list[ExtractedDocumentPage]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def extracted_character_count(self) -> int:
        return sum(len(page.text) for page in self.pages)


class DocumentExtractor(Protocol):
    """Protocol for document extraction backends."""

    name: str
    supported: bool

    def extract_pdf(self, pdf_bytes: bytes) -> ExtractedDocument:
        """Extract text from a PDF document."""


class NoOpDocumentExtractor:
    """Default document extractor that makes lack of PDF support explicit."""

    name = "noop-document-extractor"
    supported = False

    def extract_pdf(self, pdf_bytes: bytes) -> ExtractedDocument:
        _ = pdf_bytes
        return ExtractedDocument(pages=[])


class PypdfDocumentExtractor:
    """`pypdf`-backed PDF text extractor."""

    name = "pypdf-document-extractor"
    supported = True

    def __init__(
        self,
        *,
        max_pages: int,
        max_extracted_characters: int,
    ) -> None:
        try:
            from pypdf import PdfReader
            from pypdf.errors import PdfReadError
        except ImportError as exc:
            raise RuntimeError(
                "PDF document workflows require the `pypdf` package.",
            ) from exc

        self.pdf_reader_class = PdfReader
        self.pdf_read_error = PdfReadError
        self.max_pages = max_pages
        self.max_extracted_characters = max_extracted_characters

    def extract_pdf(self, pdf_bytes: bytes) -> ExtractedDocument:
        if not pdf_bytes.startswith(b"%PDF-"):
            raise BadRequestError("Uploaded file is not a valid PDF document")

        try:
            reader = self.pdf_reader_class(BytesIO(pdf_bytes), strict=True)
        except self.pdf_read_error as exc:
            raise BadRequestError("Uploaded PDF could not be parsed safely") from exc

        if reader.is_encrypted:
            raise BadRequestError("Encrypted PDF documents are not supported")

        page_count = len(reader.pages)
        if page_count > self.max_pages:
            raise PayloadTooLargeError(
                f"PDF exceeds the configured maximum page count of {self.max_pages}",
            )

        pages: list[ExtractedDocumentPage] = []
        total_characters = 0
        for index, page in enumerate(reader.pages, start=1):
            extracted_text = page.extract_text() or ""
            normalized_text = self._normalize_text(extracted_text)
            total_characters += len(normalized_text)
            if total_characters > self.max_extracted_characters:
                raise PayloadTooLargeError(
                    "Extracted PDF text exceeds the configured maximum of "
                    f"{self.max_extracted_characters} characters",
                )
            pages.append(
                ExtractedDocumentPage(
                    page_number=index,
                    text=normalized_text,
                ),
            )

        if not any(page.text.strip() for page in pages):
            raise UnprocessableContentError(
                "PDF did not contain extractable text. Scanned or image-only PDFs "
                "are not supported yet",
            )

        return ExtractedDocument(pages=pages)

    def _normalize_text(self, value: str) -> str:
        return value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")


def build_document_extractor(settings: Settings) -> DocumentExtractor:
    """Build the configured PDF document extractor."""

    backend = settings.document_extractor_backend.strip().lower()
    if backend in {"", "noop", "none", "disabled"}:
        return NoOpDocumentExtractor()
    if backend in {"auto"}:
        try:
            return PypdfDocumentExtractor(
                max_pages=settings.max_document_pages,
                max_extracted_characters=settings.max_document_extracted_characters,
            )
        except RuntimeError:
            return NoOpDocumentExtractor()
    if backend in {"pypdf", "pdf"}:
        return PypdfDocumentExtractor(
            max_pages=settings.max_document_pages,
            max_extracted_characters=settings.max_document_extracted_characters,
        )
    raise RuntimeError(
        f"Unsupported document extractor backend `{settings.document_extractor_backend}`.",
    )
