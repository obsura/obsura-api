"""PII detection provider contracts and backend builders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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
    supported_languages: tuple[str, ...]
    custom_recognizers_configured: bool

    def detect_entities(
        self,
        text: str,
        *,
        language: str | None = None,
        entity_allow_list: list[str] | None = None,
        context_words: list[str] | None = None,
    ) -> list[DetectedPIIEntity]:
        """Return detected PII entities in the provided text."""


class NoOpPIIDetector:
    """Default PII detector that keeps NLP detection optional."""

    name = "noop-pii-detector"
    supported = False
    supported_languages: tuple[str, ...] = ()
    custom_recognizers_configured = False

    def detect_entities(
        self,
        text: str,
        *,
        language: str | None = None,
        entity_allow_list: list[str] | None = None,
        context_words: list[str] | None = None,
    ) -> list[DetectedPIIEntity]:
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
        supported_languages: tuple[str, ...] | None = None,
        model_map: dict[str, str] | None = None,
        recognizers_path: Path | None = None,
    ) -> None:
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider
            from presidio_analyzer.recognizer_registry import RecognizerRegistry
        except ImportError as exc:
            raise RuntimeError(
                "Presidio PII detection requires the `presidio-analyzer` package.",
            ) from exc

        resolved_languages = tuple(supported_languages or (language,))
        resolved_model_map = dict(model_map or {})
        if language not in resolved_model_map:
            resolved_model_map[language] = model_name

        nlp_configuration = {
            "nlp_engine_name": "spacy",
            "models": [
                {
                    "lang_code": current_language,
                    "model_name": resolved_model_map[current_language],
                }
                for current_language in resolved_languages
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
        self.supported_languages = resolved_languages
        self.custom_recognizers_configured = recognizers_path is not None
        registry = RecognizerRegistry(supported_languages=list(resolved_languages))
        registry.load_predefined_recognizers(
            languages=list(resolved_languages),
            nlp_engine=nlp_engine,
        )
        if recognizers_path is not None:
            resolved_path = recognizers_path.expanduser()
            if not resolved_path.is_absolute():
                resolved_path = (Path.cwd() / resolved_path).resolve()
            if not resolved_path.is_file():
                raise RuntimeError(
                    f"Presidio recognizer registry file was not found at `{resolved_path}`.",
                )
            registry.add_recognizers_from_yaml(str(resolved_path))
        self.analyzer = AnalyzerEngine(
            registry=registry,
            nlp_engine=nlp_engine,
            supported_languages=list(resolved_languages),
        )

    def detect_entities(
        self,
        text: str,
        *,
        language: str | None = None,
        entity_allow_list: list[str] | None = None,
        context_words: list[str] | None = None,
    ) -> list[DetectedPIIEntity]:
        if not text.strip():
            return []

        active_language = (language or self.language).strip().lower()
        if active_language not in self.supported_languages:
            supported = ", ".join(self.supported_languages)
            raise ValueError(
                f"Unsupported PII language `{active_language}`. Supported languages: {supported}",
            )

        results = self.analyzer.analyze(
            text=text,
            language=active_language,
            entities=entity_allow_list or None,
            context=context_words or None,
            score_threshold=self.score_threshold,
            return_decision_process=False,
        )
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
            supported_languages=settings.presidio_supported_languages,
            model_map=settings.presidio_model_map,
            recognizers_path=settings.presidio_recognizers_path,
        )
    raise RuntimeError(f"Unsupported PII detector backend `{settings.pii_backend}`.")
