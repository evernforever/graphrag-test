"""
문단 기준 청킹.
- 빈 줄(\n\n)을 기준으로 문단 분리
- MAX_CHUNK_CHARS를 초과하는 문단은 문장 단위로 추가 분할
"""
from __future__ import annotations
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from src.config import MAX_CHUNK_CHARS, CHUNK_OVERLAP_CHARS


@dataclass
class Chunk:
    chunk_id: str
    source_file: str
    chunk_index: int
    text: str
    embedding: list[float] = field(default_factory=list)


def _split_long_paragraph(paragraph: str, max_chars: int, overlap: int) -> list[str]:
    """문장 단위로 분할 후 슬라이딩 윈도우 적용."""
    sentences = re.split(r"(?<=[.!?。])\s+", paragraph.strip())
    chunks: list[str] = []
    current = ""

    for sent in sentences:
        if len(current) + len(sent) + 1 <= max_chars:
            current = (current + " " + sent).strip() if current else sent
        else:
            if current:
                chunks.append(current)
            # 오버랩: 이전 청크 끝부분 가져오기
            if chunks and overlap > 0:
                tail = chunks[-1][-overlap:]
                current = tail + " " + sent
            else:
                current = sent

    if current:
        chunks.append(current)

    return chunks if chunks else [paragraph]


def chunk_file(file_path: Path) -> list[Chunk]:
    text = file_path.read_text(encoding="utf-8")
    source = file_path.name

    # 빈 줄 기준 문단 분리
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    chunks: list[Chunk] = []
    for para in paragraphs:
        if len(para) <= MAX_CHUNK_CHARS:
            sub_texts = [para]
        else:
            sub_texts = _split_long_paragraph(para, MAX_CHUNK_CHARS, CHUNK_OVERLAP_CHARS)

        for sub in sub_texts:
            chunks.append(
                Chunk(
                    chunk_id=str(uuid.uuid4()),
                    source_file=source,
                    chunk_index=len(chunks),
                    text=sub,
                )
            )

    return chunks


def chunk_directory(data_dir: Path) -> list[Chunk]:
    all_chunks: list[Chunk] = []
    for txt_file in sorted(data_dir.glob("*.txt")):
        all_chunks.extend(chunk_file(txt_file))
    return all_chunks
