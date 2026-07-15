"""Document acquisition and preparation public interface."""

from .acquisition import (
    AcquiredDocument,
    DefuddleAdapter,
    MissingDefuddleError,
    SourceAcquisitionError,
    SourceProvenance,
    acquire_markdown,
)
from .documents import (
    Diagnostic,
    DisplayDocument,
    DisplayWord,
    DocumentPipeline,
    PreparedDocument,
    ScientificPolicy,
    SpeechChunk,
    SpeechProjection,
    SpeechWord,
)
from .processor import ArticleProcessingError, ArticleProcessingResult, ArticleProcessor

__all__ = [
    "AcquiredDocument",
    "DefuddleAdapter",
    "MissingDefuddleError",
    "SourceAcquisitionError",
    "SourceProvenance",
    "acquire_markdown",
    "Diagnostic",
    "DisplayDocument",
    "DisplayWord",
    "DocumentPipeline",
    "PreparedDocument",
    "ScientificPolicy",
    "SpeechChunk",
    "SpeechProjection",
    "SpeechWord",
    "ArticleProcessingError",
    "ArticleProcessingResult",
    "ArticleProcessor",
]
