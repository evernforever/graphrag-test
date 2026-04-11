"""
Neo4j 연결, 스키마 초기화, 노드/엣지 저장, 벡터 검색, 그래프 탐색.

스키마:
  (:SourceFile {id, filename})
  (:Chunk {id, text, source_file, chunk_index, embedding})
  (:Entity {name, type})
  (:SourceFile)-[:HAS_CHUNK]->(:Chunk)
  (:Chunk)-[:CONTAINS_ENTITY]->(:Entity)
  (:Entity)-[:WORKS_AT|LAUNCHED|PARTNERED_WITH|INVESTED_IN|RELATED_TO {
      evidence_text, source_file, chunk_id, extraction_note
  }]->(:Entity)
"""
from __future__ import annotations

from neo4j import GraphDatabase

from src.config import (
    NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD,
    EMBEDDING_DIM, RELATION_TYPES,
)


class GraphStore:
    def __init__(self):
        self._driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
        )

    def close(self):
        self._driver.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ------------------------------------------------------------------
    # 스키마 초기화
    # ------------------------------------------------------------------

    def init_schema(self):
        """인덱스 및 제약 조건 생성 (멱등성 보장)."""
        with self._driver.session() as session:
            # 유니크 제약: SourceFile.filename
            session.run("""
                CREATE CONSTRAINT sf_filename IF NOT EXISTS
                FOR (n:SourceFile) REQUIRE n.filename IS UNIQUE
            """)
            # 유니크 제약: Chunk.id
            session.run("""
                CREATE CONSTRAINT chunk_id IF NOT EXISTS
                FOR (n:Chunk) REQUIRE n.id IS UNIQUE
            """)
            # Entity.name 인덱스 (Community Edition 호환)
            session.run("""
                CREATE INDEX entity_name IF NOT EXISTS
                FOR (n:Entity) ON (n.name)
            """)
            # 벡터 인덱스: Chunk.embedding
            session.run(f"""
                CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
                FOR (n:Chunk) ON (n.embedding)
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: {EMBEDDING_DIM},
                        `vector.similarity_function`: 'cosine'
                    }}
                }}
            """)

    def clear_all(self):
        """전체 그래프 삭제 (재인덱싱용)."""
        with self._driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    # ------------------------------------------------------------------
    # 노드 저장
    # ------------------------------------------------------------------

    def upsert_source_file(self, filename: str):
        with self._driver.session() as session:
            session.run("""
                MERGE (sf:SourceFile {filename: $filename})
                ON CREATE SET sf.id = $filename
            """, filename=filename)

    def upsert_chunk(self, chunk_id: str, text: str, source_file: str,
                     chunk_index: int, embedding: list[float]):
        with self._driver.session() as session:
            session.run("""
                MERGE (c:Chunk {id: $chunk_id})
                SET c.text = $text,
                    c.source_file = $source_file,
                    c.chunk_index = $chunk_index,
                    c.embedding = $embedding
                WITH c
                MATCH (sf:SourceFile {filename: $source_file})
                MERGE (sf)-[:HAS_CHUNK]->(c)
            """, chunk_id=chunk_id, text=text, source_file=source_file,
                chunk_index=chunk_index, embedding=embedding)

    def upsert_entity(self, name: str, entity_type: str):
        with self._driver.session() as session:
            session.run("""
                MERGE (e:Entity {name: $name, type: $type})
            """, name=name, type=entity_type)

    def link_chunk_to_entity(self, chunk_id: str, entity_name: str, entity_type: str):
        with self._driver.session() as session:
            session.run("""
                MATCH (c:Chunk {id: $chunk_id})
                MATCH (e:Entity {name: $entity_name, type: $entity_type})
                MERGE (c)-[:CONTAINS_ENTITY]->(e)
            """, chunk_id=chunk_id, entity_name=entity_name, entity_type=entity_type)

    def upsert_relation(
        self,
        source_name: str, source_type: str,
        relation: str,
        target_name: str, target_type: str,
        evidence_text: str, source_file: str,
        chunk_id: str, extraction_note: str,
    ):
        if relation not in RELATION_TYPES:
            return  # 허용되지 않는 관계 타입 무시

        query = f"""
            MATCH (s:Entity {{name: $source_name, type: $source_type}})
            MATCH (t:Entity {{name: $target_name, type: $target_type}})
            MERGE (s)-[r:{relation} {{chunk_id: $chunk_id}}]->(t)
            SET r.evidence_text = $evidence_text,
                r.source_file = $source_file,
                r.extraction_note = $extraction_note
        """
        with self._driver.session() as session:
            session.run(
                query,
                source_name=source_name, source_type=source_type,
                target_name=target_name, target_type=target_type,
                evidence_text=evidence_text, source_file=source_file,
                chunk_id=chunk_id, extraction_note=extraction_note,
            )

    # ------------------------------------------------------------------
    # 벡터 검색
    # ------------------------------------------------------------------

    def vector_search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        """코사인 유사도 기준 상위 k개 Chunk 반환."""
        with self._driver.session() as session:
            result = session.run("""
                CALL db.index.vector.queryNodes('chunk_embedding', $top_k, $embedding)
                YIELD node, score
                RETURN node.id AS chunk_id,
                       node.text AS text,
                       node.source_file AS source_file,
                       score
                ORDER BY score DESC
            """, top_k=top_k, embedding=query_embedding)
            return [dict(r) for r in result]

    # ------------------------------------------------------------------
    # 그래프 탐색
    # ------------------------------------------------------------------

    def get_entities_from_chunks(self, chunk_ids: list[str]) -> list[dict]:
        """청크에서 CONTAINS_ENTITY로 연결된 엔티티 목록."""
        with self._driver.session() as session:
            result = session.run("""
                MATCH (c:Chunk)-[:CONTAINS_ENTITY]->(e:Entity)
                WHERE c.id IN $chunk_ids
                RETURN DISTINCT e.name AS name, e.type AS type
            """, chunk_ids=chunk_ids)
            return [dict(r) for r in result]

    def get_relations_from_entities(
        self, entity_names: list[str], hops: int = 2
    ) -> list[dict]:
        """엔티티에서 출발하는 관계 수집 (최대 hops홉)."""
        with self._driver.session() as session:
            result = session.run(f"""
                MATCH (s:Entity)-[r*1..{hops}]->(t:Entity)
                WHERE s.name IN $names
                UNWIND r AS rel
                WITH startNode(rel) AS src, rel, endNode(rel) AS tgt
                RETURN src.name AS source,
                       src.type AS source_type,
                       type(rel) AS relation,
                       tgt.name AS target,
                       tgt.type AS target_type,
                       rel.evidence_text AS evidence_text,
                       rel.source_file AS source_file,
                       rel.extraction_note AS extraction_note
                LIMIT 50
            """, names=entity_names)
            return [dict(r) for r in result]

    def get_chunks_by_file(self, filename: str) -> list[dict]:
        """특정 파일의 청크 목록 (chunk_index 순)."""
        with self._driver.session() as session:
            result = session.run("""
                MATCH (c:Chunk {source_file: $filename})
                RETURN c.chunk_index AS idx, c.text AS text
                ORDER BY c.chunk_index
            """, filename=filename)
            return [dict(r) for r in result]

    # ------------------------------------------------------------------
    # 통계
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        with self._driver.session() as session:
            counts = session.run("""
                MATCH (sf:SourceFile) WITH count(sf) AS sf_count
                MATCH (c:Chunk)      WITH sf_count, count(c) AS c_count
                MATCH (e:Entity)     WITH sf_count, c_count, count(e) AS e_count
                MATCH ()-[r]->()     RETURN sf_count, c_count, e_count, count(r) AS r_count
            """).single()
            return dict(counts) if counts else {}
