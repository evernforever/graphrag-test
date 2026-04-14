"""
GraphRAG 쿼리 파이프라인.
1. 질문 → KURE-v1 임베딩
2. Neo4j 벡터 검색 → top-k Chunk
3. Chunk에서 Entity 확장
4. Entity에서 그래프 관계 수집 (2홉)
5. 수집된 컨텍스트 + 근거 → Claude Sonnet 4.6 → 최종 답변
"""
from __future__ import annotations
from dataclasses import dataclass

import anthropic

from src.config import ANTHROPIC_API_KEY, EXTRACTION_MODEL, QUERY_MODEL
from src.embedder import embed_query
from src.graph import GraphStore

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


@dataclass
class QueryResult:
    question: str
    answer: str
    chunks: list[dict]
    entities: list[dict]
    relations: list[dict]


def _build_context(
    chunks: list[dict],
    entities: list[dict],
    relations: list[dict],
) -> str:
    lines = []

    lines.append("## 관련 문서 청크")
    for i, c in enumerate(chunks, 1):
        lines.append(f"\n[출처{i}] ({c['source_file']}, 유사도: {c['score']:.3f})")
        lines.append(c["text"])

    if entities:
        lines.append("\n## 관련 엔티티")
        for e in entities:
            lines.append(f"- {e['name']} ({e['type']})")

    if relations:
        lines.append("\n## 그래프 관계 및 근거")
        for r in relations:
            lines.append(
                f"- {r['source']}({r['source_type']}) "
                f"--[{r['relation']}]--> "
                f"{r['target']}({r['target_type']})"
            )
            if r.get("evidence_text"):
                lines.append(f"  근거: \"{r['evidence_text']}\"")
            if r.get("extraction_note"):
                lines.append(f"  추출 이유: {r['extraction_note']}")

    return "\n".join(lines)


QUERY_SYSTEM = """당신은 한국 테크 기업 생태계 전문 AI입니다.
제공된 문서 청크, 엔티티, 그래프 관계를 바탕으로 질문에 답하세요.

규칙:
1. 제공된 컨텍스트에 근거한 내용만 답변하세요.
2. 각 항목을 서술한 다음 줄에 반드시 `> 📎 출처1 | INVESTED_IN` 형식으로 해당 청크 번호와 관계 타입을 별도 줄로 표기하세요. (마크다운 인용 블록 > 사용)
3. 답변 마지막에 사용한 근거(출처 파일명, 관계 타입, 증거 문장)를 정리해서 명시하세요.
4. 컨텍스트에 없는 내용은 "제공된 문서에서 확인되지 않습니다"라고 하세요.
5. 답변은 한국어로 작성하세요.
"""


def search_context(
    question: str,
    top_k: int = 5,
    hops: int = 2,
    graph_search: bool = True,
) -> tuple[list[dict], list[dict], list[dict]]:
    """벡터 검색 → (선택적) 엔티티 확장 → 그래프 관계 수집 후 (chunks, entities, relations) 반환."""
    q_vec = embed_query(question)
    with GraphStore() as store:
        chunks = store.vector_search(q_vec, top_k=top_k)
        if not graph_search:
            return chunks, [], []
        chunk_ids = [c["chunk_id"] for c in chunks]
        entities = store.get_entities_from_chunks(chunk_ids)
        entity_names = [e["name"] for e in entities]
        relations = store.get_relations_from_entities(entity_names, hops=hops)
    return chunks, entities, relations


def stream_answer(
    question: str,
    chunks: list[dict],
    entities: list[dict],
    relations: list[dict],
    timeout: float | None = None,
):
    """Claude Sonnet 4.6으로 스트리밍 답변 생성. 텍스트 청크를 yield."""
    context = _build_context(chunks, entities, relations)
    user_prompt = f"{context}\n\n## 질문\n{question}"

    with _client.messages.stream(
        model=QUERY_MODEL,
        max_tokens=2048,
        system=QUERY_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
        timeout=timeout,
    ) as stream:
        for text in stream.text_stream:
            yield text


def run_query(
    question: str,
    top_k: int = 5,
    hops: int = 2,
    verbose: bool = True,
) -> QueryResult:
    if verbose:
        print(f"\n질문: {question}")
        print("-" * 50)

    with GraphStore() as store:
        # 1. 벡터 검색
        if verbose:
            print("[1] 벡터 검색 중...")
        q_vec = embed_query(question)
        chunks = store.vector_search(q_vec, top_k=top_k)
        if verbose:
            print(f"  → {len(chunks)}개 청크 검색됨")

        # 2. 엔티티 확장
        if verbose:
            print("[2] 엔티티 확장 중...")
        chunk_ids = [c["chunk_id"] for c in chunks]
        entities = store.get_entities_from_chunks(chunk_ids)
        if verbose:
            print(f"  → {len(entities)}개 엔티티")

        # 3. 그래프 관계 수집
        if verbose:
            print(f"[3] 그래프 관계 수집 중 ({hops}홉)...")
        entity_names = [e["name"] for e in entities]
        relations = store.get_relations_from_entities(entity_names, hops=hops)
        if verbose:
            print(f"  → {len(relations)}개 관계")

    # 4. Claude Sonnet 4.6으로 답변 생성
    if verbose:
        print("[4] Claude Sonnet 4.6 답변 생성 중...")

    context = _build_context(chunks, entities, relations)
    user_prompt = f"{context}\n\n## 질문\n{question}"

    response = _client.messages.create(
        model=QUERY_MODEL,
        max_tokens=2048,
        system=QUERY_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )
    answer = response.content[0].text

    if verbose:
        print("\n" + "=" * 50)
        print("답변:")
        print(answer)
        print("=" * 50)

    return QueryResult(
        question=question,
        answer=answer,
        chunks=chunks,
        entities=entities,
        relations=relations,
    )
