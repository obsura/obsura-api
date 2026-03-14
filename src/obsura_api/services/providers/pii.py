"""PII detection provider contracts and backend builders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from obsura_api.core.settings import Settings


@dataclass(slots=True)
class DetectedPIIEntity:
    """One PII entity span returned by a detector backend."""

    entity_type: str
    start_index: int
    end_index: int
    confidence: float


class PIIDetector(Protocol):
    """Protocol for text PII detection backends."""

    name: str
    supported: bool

    def detect_entities(self, text: str) -> list[DetectedPIIEntity]:
        """Return detected PII entities in the provided text."""


class NoOpPIIDetector:
    """Default PII detector that keeps NLP detection optional."""

    name = "noop-pii-detector"
    supported = False

    def detect_entities(self, text: str) -> list[DetectedPIIEntity]:
        return []


class PresidioPIIDetector:
    """Presidio-backed PII detector using a configured spaCy language model."""

    name = "presidio-pii-detector"
    supported = True

    def __init__(
        self,
        *,
        language: str = "en",
        model_name: str = "en_core_web_sm",
        score_threshold: float = 0.35,
    ) -> None:
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider
        except ImportError as exc:
            raise RuntimeError(
                "Presidio PII detection requires the `presidio-analyzer` package.",
            ) from exc

        nlp_configuration = {
            "nlp_engine_name": "spacy",
            "models": [
                {
                    "lang_code": language,
                    "model_name": model_name,
                }
            ],
        }
        try:
            nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()
        except Exception as exc:  # pragma: no cover - exact exception types depend on optional deps
            raise RuntimeError(
                "Presidio PII detection requires a compatible spaCy model. "
                f"Failed to load `{model_name}` for language `{language}`.",
            ) from exc

        self.language = language
        self.score_threshold = score_threshold
        self.analyzer = AnalyzerEngine(
            nlp_engine=nlp_engine,
            supported_languages=[language],
        )

    def detect_entities(self, text: str) -> list[DetectedPIIEntity]:
        if not text.strip():
            return []

        results = self.analyzer.analyze(text=text, language=self.language)
        entities: list[DetectedPIIEntity] = []
        for result in results:
            score = float(getattr(result, "score", 0.0) or 0.0)
            if score < self.score_threshold:
                continue
            entities.append(
                DetectedPIIEntity(
                    entity_type=str(result.entity_type),
                    start_index=int(result.start),
                    end_index=int(result.end),
                    confidence=score,
                ),
            )
        return entities


def build_pii_detector(settings: Settings) -> PIIDetector:
    """Build the configured PII detector backend."""

    backend = settings.pii_backend.strip().lower()
    if backend in {"", "noop", "none", "disabled"}:
        return NoOpPIIDetector()
    if backend in {"presidio", "presidio_analyzer"}:
        return PresidioPIIDetector(
            language=settings.pii_language,
            model_name=settings.presidio_model,
            score_threshold=settings.presidio_score_threshold,
        )
    raise RuntimeError(f"Unsupported PII detector backend `{settings.pii_backend}`.")
