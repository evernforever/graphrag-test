"""
인덱싱 파이프라인.
1. txt 파일 → 청킹
2. KURE-v1 임베딩
3. Claude Haiku 4.5로 (엔티티, 관계) 추출
4. Neo4j에 SourceFile / Chunk / Entity / Relation 저장
"""
from __future__ import annotations

from pathlib import Path

from src.chunker import chunk_directory, Chunk
from src.embedder import embed_chunks
from src.extractor import extract_chunks
from src.graph import GraphStore
from src.config import DATA_DIR


def run_indexing(data_dir: Path = DATA_DIR, reset: bool = False):
    print("=" * 60)
    print("GraphRAG 인덱싱 시작")
    print("=" * 60)

    with GraphStore() as store:
        # 스키마 초기화
        print("\n[1/5] 스키마 초기화...")
        store.init_schema()
        if reset:
            print("  기존 데이터 삭제 중...")
            store.clear_all()
            store.init_schema()

        # 청킹
        print(f"\n[2/5] 청킹: {data_dir}")
        chunks: list[Chunk] = chunk_directory(data_dir)
        print(f"  총 {len(chunks)}개 청크 생성")

        # 임베딩
        print("\n[3/5] KURE-v1 임베딩 중...")
        chunks = embed_chunks(chunks)
        print(f"  완료 ({len(chunks)}개)")

        # 엔티티/관계 추출
        print("\n[4/5] Claude Haiku 4.5로 엔티티/관계 추출 중...")
        results = extract_chunks(chunks, verbose=True)

        # Neo4j 저장
        print("\n[5/5] Neo4j 저장 중...")

        # SourceFile 노드
        source_files = {c.source_file for c in chunks}
        for sf in source_files:
            store.upsert_source_file(sf)

        # Chunk + Entity + Relation
        chunk_map = {c.chunk_id: c for c in chunks}
        total_entities = 0
        total_relations = 0

        for result in results:
            chunk = chunk_map[result.chunk_id]

            # Chunk 노드
            store.upsert_chunk(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                source_file=chunk.source_file,
                chunk_index=chunk.chunk_index,
                embedding=chunk.embedding,
            )

            # Entity 노드 + Chunk→Entity 엣지
            for ent in result.entities:
                name = ent.get("name", "").strip()
                etype = ent.get("type", "")
                if not name or not etype:
                    continue
                store.upsert_entity(name, etype)
                store.link_chunk_to_entity(chunk.chunk_id, name, etype)
                total_entities += 1

            # Relation 엣지
            for rel in result.relations:
                src = rel.get("source", "").strip()
                src_type = rel.get("source_type", "")
                rel_type = rel.get("relation", "")
                tgt = rel.get("target", "").strip()
                tgt_type = rel.get("target_type", "")
                evidence = rel.get("evidence_text", "")
                note = rel.get("extraction_note", "")

                if not all([src, src_type, rel_type, tgt, tgt_type]):
                    continue

                # 관계에 등장하는 엔티티도 MERGE 보장
                store.upsert_entity(src, src_type)
                store.upsert_entity(tgt, tgt_type)

                store.upsert_relation(
                    source_name=src, source_type=src_type,
                    relation=rel_type,
                    target_name=tgt, target_type=tgt_type,
                    evidence_text=evidence,
                    source_file=result.source_file,
                    chunk_id=result.chunk_id,
                    extraction_note=note,
                )
                total_relations += 1

        stats = store.stats()
        print("\n인덱싱 완료!")
        print(f"  SourceFile : {len(source_files)}")
        print(f"  Chunk      : {stats.get('c_count', '?')}")
        print(f"  Entity     : {stats.get('e_count', '?')} (추출 {total_entities}건)")
        print(f"  Relation   : {total_relations}건")
        print("=" * 60)
