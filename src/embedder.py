"""
KURE-v1 임베딩 (1024차원).
sentence-transformers로 로드하며, 첫 실행 시 HuggingFace에서 모델을 다운로드합니다.
"""
from __future__ import annotations

from sentence_transformers import SentenceTransformer

from src.config import EMBEDDING_MODEL, EMBEDDING_DIM
from src.chunker import Chunk

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print(f"  임베딩 모델 로드 중: {EMBEDDING_MODEL}")
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    model = _get_model()
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    assert vectors.shape[1] == EMBEDDING_DIM, (
        f"차원 불일치: 모델={vectors.shape[1]}, 설정={EMBEDDING_DIM}"
    )
    return vectors.tolist()


def embed_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """청크 리스트에 embedding 필드를 채워 반환."""
    texts = [c.text for c in chunks]
    vectors = embed_texts(texts)
    for chunk, vec in zip(chunks, vectors):
        chunk.embedding = vec
    return chunks


def embed_query(query: str) -> list[float]:
    return embed_texts([query])[0]
