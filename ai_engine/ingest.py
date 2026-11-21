"""Turn an uploaded file (or plain text) into searchable DocumentChunks.

    index_source(obj, path=..., text=...)  -> number of chunks written

``obj`` is any model instance (Suhaib's Resource, an Article...). The engine
reads ``obj.title`` for citations when it exists.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from .models import DocumentChunk

log = logging.getLogger("ai_engine")

CHUNK_WORDS = 120
OVERLAP_WORDS = 30
SUPPORTED = {".pdf", ".pptx", ".txt", ".md"}


class UnsupportedFile(ValueError):
    pass


# ---------------------------------------------------------------------------
# Extraction: file -> [(locator, text)]
# ---------------------------------------------------------------------------
def extract_pages(path: str | Path) -> list[tuple[str, str]]:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return [(f"p. {i}", page.extract_text() or "") for i, page in enumerate(reader.pages, start=1)]
    if ext == ".pptx":
        from pptx import Presentation

        pages = []
        for i, slide in enumerate(Presentation(str(path)).slides, start=1):
            parts = [shape.text_frame.text for shape in slide.shapes if shape.has_text_frame]
            pages.append((f"slide {i}", "\n".join(parts)))
        return pages
    if ext in {".txt", ".md"}:
        return split_text_into_pages(path.read_text(encoding="utf-8", errors="ignore"))
    raise UnsupportedFile(f"Cannot read {ext or 'this'} files yet. Use PDF, PPTX, TXT or MD.")


def split_text_into_pages(text: str) -> list[tuple[str, str]]:
    """Plain text has no pages: number its paragraphs as sections instead."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return [(f"§ {i}", p) for i, p in enumerate(paras, start=1)] or [("§ 1", text.strip())]


# ---------------------------------------------------------------------------
# Chunking: overlapping word windows that never cross a page
# ---------------------------------------------------------------------------
def chunk_pages(pages: list[tuple[str, str]]) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    buffer: list[str] = []
    buffer_locator = ""
    for locator, text in pages:
        words = " ".join(text.split()).split(" ")
        words = [w for w in words if w]
        if not words:
            continue
        # Short pages are merged with the next one so tiny fragments are not indexed alone.
        if len(words) < CHUNK_WORDS // 3:
            buffer_locator = buffer_locator or locator
            buffer.extend(words)
            if len(buffer) < CHUNK_WORDS // 3:
                continue
            words, locator, buffer, buffer_locator = buffer, buffer_locator, [], ""
        elif buffer:
            chunks.append((buffer_locator, " ".join(buffer)))
            buffer, buffer_locator = [], ""
        step = CHUNK_WORDS - OVERLAP_WORDS
        for start in range(0, len(words), step):
            window = words[start : start + CHUNK_WORDS]
            chunks.append((locator, " ".join(window)))
            if start + CHUNK_WORDS >= len(words):
                break
    if buffer:
        chunks.append((buffer_locator, " ".join(buffer)))
    return chunks


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------
@transaction.atomic
def index_source(obj, path: str | Path | None = None, text: str | None = None) -> int:
    """(Re)build the chunks for one source. Returns how many chunks were written."""
    if path is None and text is None:
        raise ValueError("Give a file path or the text to index.")
    pages = extract_pages(path) if path is not None else split_text_into_pages(text or "")
    chunks = chunk_pages(pages)

    ct = ContentType.objects.get_for_model(obj)
    DocumentChunk.objects.filter(content_type=ct, object_id=obj.pk).delete()
    DocumentChunk.objects.bulk_create(
        DocumentChunk(content_type=ct, object_id=obj.pk, chunk_index=i, text=body, locator=loc)
        for i, (loc, body) in enumerate(chunks)
    )
    from .retrieval import index  # avoid an import cycle

    index.invalidate()
    log.info("indexed %s #%s: %s chunks", ct.model, obj.pk, len(chunks))
    return len(chunks)


def remove_source(obj) -> None:
    ct = ContentType.objects.get_for_model(obj)
    DocumentChunk.objects.filter(content_type=ct, object_id=obj.pk).delete()
    from .retrieval import index

    index.invalidate()
