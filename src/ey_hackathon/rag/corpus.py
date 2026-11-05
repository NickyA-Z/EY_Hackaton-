"""Parse the markdown corpus into documents and section-level chunks.

Chunking is by ``##`` section, not by token window: every section in this corpus is a self-contained
rule block (Start, Upwind, Plan B, ...), so splitting there keeps rules intact. Headings are NOT the
same across all documents (TS-10 / TS-11 differ), so we split on whatever ``##`` headings exist.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

INDEX_DOC_TYPE = "index"
_SYNTHETIC_LINE = re.compile(r"^>\s*SYNTHETIC DATA.*$", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    title: str
    doc_type: str
    condition: str
    section: str
    safety_critical: bool
    body: str

    @property
    def embed_text(self) -> str:
        """Header + body: short sections lose their document context without the header."""
        return f"{self.doc_id} {self.title} - {self.section}\n{self.body}"

    def content_hash(self, model: str) -> str:
        return hashlib.sha256(f"{model}\n{self.embed_text}".encode()).hexdigest()


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    doc_type: str
    condition: str
    triggers: str
    safety_critical: bool
    path: Path
    sections: tuple[tuple[str, str], ...]  # (heading, body), in file order

    def text(self) -> str:
        """Full document as prompt text (title + sections; the repeated SYNTHETIC banner is dropped)."""
        parts = [f"### {self.doc_id} - {self.title}"]
        parts += [f"## {heading}\n{body}" for heading, body in self.sections]
        return "\n\n".join(parts)

    def section(self, prefix: str) -> str | None:
        return next((body for heading, body in self.sections if heading.startswith(prefix)), None)

    def chunks(self) -> list[Chunk]:
        seen: dict[str, int] = {}
        out: list[Chunk] = []
        for heading, body in self.sections:
            slug = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-") or "section"
            seen[slug] = seen.get(slug, 0) + 1
            suffix = "" if seen[slug] == 1 else f"-{seen[slug]}"
            out.append(
                Chunk(
                    id=f"{self.doc_id}:{slug}{suffix}",
                    doc_id=self.doc_id,
                    title=self.title,
                    doc_type=self.doc_type,
                    condition=self.condition,
                    section=heading,
                    safety_critical=self.safety_critical,
                    body=body,
                )
            )
        return out


def _split_front_matter(raw: str, path: Path) -> tuple[dict[str, str], str]:
    if not raw.startswith("---\n"):
        raise ValueError(f"{path.name}: missing front-matter")
    end = raw.find("\n---\n", 4)
    if end == -1:
        raise ValueError(f"{path.name}: unterminated front-matter")
    meta: dict[str, str] = {}
    for line in raw[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return meta, raw[end + 5 :]


def _split_sections(body: str) -> tuple[tuple[str, str], ...]:
    sections: list[tuple[str, list[str]]] = []
    for line in _SYNTHETIC_LINE.sub("", body).splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections:  # everything before the first ## (title line, banner) is dropped
            sections[-1][1].append(line)
    return tuple((heading, "\n".join(lines).strip()) for heading, lines in sections if "".join(lines).strip())


def parse_document(path: Path) -> Document:
    meta, body = _split_front_matter(path.read_text(encoding="utf-8"), path)
    for required in ("doc_id", "title", "doc_type"):
        if required not in meta:
            raise ValueError(f"{path.name}: front-matter lacks '{required}'")
    return Document(
        doc_id=meta["doc_id"],
        title=meta["title"],
        doc_type=meta["doc_type"],
        condition=meta.get("condition", ""),
        triggers=meta.get("triggers", ""),
        safety_critical=meta.get("safety_critical", "false").lower() == "true",
        path=path,
        sections=_split_sections(body),
    )


def load_documents(corpus_dir: Path) -> dict[str, Document]:
    """All documents keyed by doc_id, including the index document."""
    docs: dict[str, Document] = {}
    for path in sorted(corpus_dir.glob("*.md")):
        doc = parse_document(path)
        if doc.doc_id in docs:
            raise ValueError(f"duplicate doc_id {doc.doc_id} ({path.name})")
        docs[doc.doc_id] = doc
    if not docs:
        raise FileNotFoundError(f"no markdown files in {corpus_dir}")
    return docs


def indexable_chunks(docs: dict[str, Document]) -> list[Chunk]:
    """Chunks that go into the vector store. The index/guide document is excluded: its tables would
    pollute search results, and its priority rules are applied in code and in the prompt instead."""
    return [c for d in docs.values() if d.doc_type != INDEX_DOC_TYPE for c in d.chunks()]
