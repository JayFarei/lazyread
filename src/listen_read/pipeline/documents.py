from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
from typing import Any, Mapping

from .acquisition import AcquiredDocument, SourceProvenance


WORD_PATTERN = re.compile(r"[\w]+(?:[’'\-][\w]+)*", re.UNICODE)
IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
NUMERIC_CITATION_PATTERN = re.compile(r"\[(?:\d+[a-z]?\s*(?:[-,;]\s*\d+[a-z]?\s*)*)\]")
DISPLAY_MATH_PATTERN = re.compile(r"\$\$.*?\$\$|\\\[.*?\\\]", re.DOTALL)
INLINE_MATH_PATTERN = re.compile(r"(?<!\$)\$(?!\$).*?(?<!\$)\$(?!\$)", re.DOTALL)


def _stable_id(prefix: str, *values: str) -> str:
    payload = "\x1f".join(values).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:20]}"


@dataclass(frozen=True, slots=True)
class DisplayWord:
    id: str
    text: str
    ordinal: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class DisplayDocument:
    document_id: str
    markdown: str
    title: str | None
    metadata: Mapping[str, str]
    words: tuple[DisplayWord, ...]


@dataclass(frozen=True, slots=True)
class SpeechWord:
    id: str
    text: str
    ordinal: int
    display_word_id: str | None = None
    sentence_end: bool = False
    sentence_suffix: str = ""


@dataclass(frozen=True, slots=True)
class SpeechChunk:
    id: str
    ordinal: int
    text: str
    words: tuple[SpeechWord, ...]


@dataclass(frozen=True, slots=True)
class SpeechProjection:
    projection_id: str
    text: str
    chunks: tuple[SpeechChunk, ...]
    policy: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    severity: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ScientificPolicy:
    equations: str = "describe"
    citations: str = "omit_numeric"
    algorithms: str = "summarize"
    figures: str = "require_descriptions"
    figure_descriptions: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "equations": self.equations,
            "citations": self.citations,
            "algorithms": self.algorithms,
            "figures": self.figures,
            "figure_descriptions": dict(self.figure_descriptions),
        }


@dataclass(frozen=True, slots=True)
class PreparedDocument:
    display: DisplayDocument
    speech: SpeechProjection
    diagnostics: tuple[Diagnostic, ...]
    provenance: SourceProvenance
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> PreparedDocument:
        display_raw = value["display"]
        speech_raw = value["speech"]
        provenance_raw = value["provenance"]
        display = DisplayDocument(
            document_id=display_raw["document_id"],
            markdown=display_raw["markdown"],
            title=display_raw.get("title"),
            metadata=dict(display_raw.get("metadata", {})),
            words=tuple(DisplayWord(**word) for word in display_raw.get("words", ())),
        )
        speech = SpeechProjection(
            projection_id=speech_raw["projection_id"],
            text=speech_raw["text"],
            chunks=tuple(
                SpeechChunk(
                    id=chunk["id"],
                    ordinal=chunk["ordinal"],
                    text=chunk["text"],
                    words=tuple(SpeechWord(**word) for word in chunk.get("words", ())),
                )
                for chunk in speech_raw.get("chunks", ())
            ),
            policy=dict(speech_raw.get("policy", {})),
        )
        return cls(
            display=display,
            speech=speech,
            diagnostics=tuple(
                Diagnostic(
                    code=item["code"],
                    severity=item["severity"],
                    message=item["message"],
                    details=dict(item.get("details", {})),
                )
                for item in value.get("diagnostics", ())
            ),
            provenance=SourceProvenance(
                adapter=provenance_raw["adapter"],
                version=provenance_raw["version"],
                source_url=provenance_raw.get("source_url"),
                command=tuple(provenance_raw.get("command", ())),
            ),
            schema_version=int(value.get("schema_version", 1)),
        )


class DocumentPipeline:
    """Build the immutable display document and reproducible speech projection."""

    def __init__(self, *, max_chunk_words: int = 120) -> None:
        if max_chunk_words < 1:
            raise ValueError("max_chunk_words must be positive")
        self._max_chunk_words = max_chunk_words

    def prepare(
        self, acquired: AcquiredDocument, policy: ScientificPolicy | None = None
    ) -> PreparedDocument:
        policy = policy or ScientificPolicy()
        markdown = acquired.markdown
        title = acquired.metadata.get("title", "").strip()
        if not title:
            heading = re.search(r"^#\s+(.+?)\s*$", markdown, re.MULTILINE)
            title = heading.group(1).strip() if heading else ""
        document_id = _stable_id("doc", markdown)
        display_words = tuple(
            DisplayWord(
                id=_stable_id("dw", document_id, str(index), match.group(0)),
                text=match.group(0),
                ordinal=index,
                start=match.start(),
                end=match.end(),
            )
            for index, match in enumerate(WORD_PATTERN.finditer(markdown))
        )
        display = DisplayDocument(
            document_id=document_id,
            markdown=markdown,
            title=title or None,
            metadata=dict(acquired.metadata),
            words=display_words,
        )
        diagnostics = self._diagnostics(markdown, policy)
        speech_text = self._speech_text(markdown, policy)
        speech = self._projection(display, speech_text, policy)
        return PreparedDocument(
            display=display,
            speech=speech,
            diagnostics=tuple(diagnostics),
            provenance=acquired.provenance,
        )

    def _diagnostics(
        self, markdown: str, policy: ScientificPolicy
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        references = re.search(r"(?im)^#{1,6}\s+references\s*$", markdown)
        if references and not markdown[references.end() :].strip():
            diagnostics.append(
                Diagnostic(
                    "empty_references",
                    "warning",
                    "The References heading is present but the bibliography is empty.",
                )
            )

        figure_alts = IMAGE_PATTERN.findall(markdown)
        missing = [alt for alt in figure_alts if alt not in policy.figure_descriptions]
        if missing and policy.figures == "require_descriptions":
            diagnostics.append(
                Diagnostic(
                    "figure_description_missing",
                    "warning",
                    "One or more figures need a spoken visual description.",
                    {"figures": missing},
                )
            )
        if DISPLAY_MATH_PATTERN.search(markdown) or INLINE_MATH_PATTERN.search(markdown):
            diagnostics.append(
                Diagnostic(
                    "equations_present",
                    "info",
                    "Equations require an explicit speech policy.",
                    {"policy": policy.equations},
                )
            )
        if NUMERIC_CITATION_PATTERN.search(markdown):
            diagnostics.append(
                Diagnostic(
                    "citations_present",
                    "info",
                    "Numeric citations were found.",
                    {"policy": policy.citations},
                )
            )
        if re.search(r"(?im)^#{1,6}\s+algorithm\b", markdown):
            diagnostics.append(
                Diagnostic(
                    "algorithms_present",
                    "info",
                    "Algorithm content was found.",
                    {"policy": policy.algorithms},
                )
            )
        return diagnostics

    def _speech_text(self, markdown: str, policy: ScientificPolicy) -> str:
        def replace_figure(match: re.Match[str]) -> str:
            alt = match.group(1).strip()
            description = policy.figure_descriptions.get(alt)
            if description:
                return f"{alt}. {description}"
            return alt

        text = IMAGE_PATTERN.sub(replace_figure, markdown)
        if policy.citations == "omit_numeric":
            text = NUMERIC_CITATION_PATTERN.sub("", text)
        if policy.equations == "describe":
            text = DISPLAY_MATH_PATTERN.sub(" equation ", text)
            text = INLINE_MATH_PATTERN.sub(" equation ", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"```[^\n]*\n(.*?)```", r"\1", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
        text = re.sub(r"(?m)^\s*(?:[-*+] |\d+[.)] )", "", text)
        text = text.translate(str.maketrans("", "", "*_`~"))
        return re.sub(r"\s+", " ", text).strip()

    def _projection(
        self,
        display: DisplayDocument,
        text: str,
        policy: ScientificPolicy,
    ) -> SpeechProjection:
        policy_dict = policy.to_dict()
        policy_json = json.dumps(policy_dict, sort_keys=True, separators=(",", ":"))
        projection_id = _stable_id("speech", display.document_id, text, policy_json)
        display_cursor = 0
        matched_words: list[tuple[str, str | None]] = []
        for index, match in enumerate(WORD_PATTERN.finditer(text)):
            spoken = match.group(0)
            display_word_id: str | None = None
            for candidate_index in range(display_cursor, len(display.words)):
                candidate = display.words[candidate_index]
                if candidate.text.casefold() == spoken.casefold():
                    display_word_id = candidate.id
                    display_cursor = candidate_index + 1
                    break
            matched_words.append((spoken, display_word_id))

        display_by_id = {word.id: word for word in display.words}
        speech_words: list[SpeechWord] = []
        for index, (spoken, display_word_id) in enumerate(matched_words):
            current = display_by_id.get(display_word_id or "")
            following = next(
                (
                    display_by_id[candidate_id]
                    for _, candidate_id in matched_words[index + 1 :]
                    if candidate_id in display_by_id
                ),
                None,
            )
            gap = (
                display.markdown[current.end : following.start if following else None]
                if current is not None
                else ""
            )
            punctuation = re.search(r"([.!?]+[\]})\"'’”]*)", gap)
            sentence_end = bool(punctuation or "\n" in gap or index == len(matched_words) - 1)
            suffix = punctuation.group(1) if punctuation else ""
            speech_words.append(
                SpeechWord(
                    id=_stable_id("sw", projection_id, str(index), spoken),
                    text=spoken,
                    ordinal=index,
                    display_word_id=display_word_id,
                    sentence_end=sentence_end,
                    sentence_suffix=suffix,
                )
            )

        chunks: list[SpeechChunk] = []
        for ordinal, offset in enumerate(range(0, len(speech_words), self._max_chunk_words)):
            words = tuple(speech_words[offset : offset + self._max_chunk_words])
            chunk_text = " ".join(
                f"{word.text}{word.sentence_suffix or ('.' if word.sentence_end else '')}"
                for word in words
            )
            chunks.append(
                SpeechChunk(
                    id=_stable_id("chunk", projection_id, str(ordinal), chunk_text),
                    ordinal=ordinal,
                    text=chunk_text,
                    words=words,
                )
            )
        return SpeechProjection(
            projection_id=projection_id,
            text=text,
            chunks=tuple(chunks),
            policy=policy_dict,
        )
