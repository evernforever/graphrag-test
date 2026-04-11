"""
Claude Haiku 4.5를 사용해 청크에서 (엔티티, 관계, 근거문장)을 JSON으로 추출.
- JSON 파싱 실패 시 최대 2회 재시도
- extraction_note: LLM이 관계를 추론한 이유 한 줄
"""
from __future__ import annotations
import json
import re
import time
from dataclasses import dataclass

import anthropic

from src.config import ANTHROPIC_API_KEY, EXTRACTION_MODEL, ENTITY_TYPES, RELATION_TYPES
from src.chunker import Chunk

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = f"""당신은 한국어 텍스트에서 엔티티와 관계를 추출하는 전문가입니다.
반드시 아래 JSON 형식만 출력하세요. 다른 텍스트는 절대 포함하지 마세요.

허용 엔티티 타입: {ENTITY_TYPES}
허용 관계 타입: {RELATION_TYPES}

출력 형식:
{{
  "entities": [
    {{"name": "엔티티명", "type": "허용된_타입"}}
  ],
  "relations": [
    {{
      "source": "출발_엔티티명",
      "source_type": "허용된_타입",
      "relation": "허용된_관계_타입",
      "target": "도착_엔티티명",
      "target_type": "허용된_타입",
      "evidence_text": "관계가 명시된 원문 문장",
      "extraction_note": "이 관계를 추출한 이유 한 줄"
    }}
  ]
}}

규칙:
1. 텍스트에 명시적으로 나타난 관계만 추출 (추론 금지)
2. 엔티티명은 원문 그대로 사용
3. evidence_text는 원문에서 직접 인용
4. 관계가 없으면 relations를 빈 배열로 반환
"""


def _parse_json(text: str) -> dict:
    """LLM 응답에서 JSON 블록 추출 후 파싱."""
    # ```json ... ``` 블록 우선 시도
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # 중괄호 전체 추출
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"JSON을 찾을 수 없음: {text[:200]}")


@dataclass
class ExtractionResult:
    chunk_id: str
    source_file: str
    entities: list[dict]
    relations: list[dict]


def extract_chunk(chunk: Chunk, max_retries: int = 2) -> ExtractionResult:
    user_prompt = f"다음 텍스트에서 엔티티와 관계를 추출하세요:\n\n{chunk.text}"

    for attempt in range(max_retries + 1):
        try:
            response = _client.messages.create(
                model=EXTRACTION_MODEL,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = response.content[0].text
            data = _parse_json(raw)

            # 스키마 보정: 필수 키 누락 시 빈 배열로 대체
            entities = data.get("entities", [])
            relations = data.get("relations", [])

            # source_file, chunk_id를 각 relation에 주입
            for rel in relations:
                rel["source_file"] = chunk.source_file
                rel["chunk_id"] = chunk.chunk_id

            return ExtractionResult(
                chunk_id=chunk.chunk_id,
                source_file=chunk.source_file,
                entities=entities,
                relations=relations,
            )

        except (json.JSONDecodeError, ValueError) as e:
            if attempt < max_retries:
                time.sleep(1)
                continue
            print(f"  [경고] 청크 {chunk.chunk_id[:8]} 추출 실패: {e}")
            return ExtractionResult(
                chunk_id=chunk.chunk_id,
                source_file=chunk.source_file,
                entities=[],
                relations=[],
            )


def extract_chunks(chunks: list[Chunk], verbose: bool = True) -> list[ExtractionResult]:
    results = []
    for i, chunk in enumerate(chunks):
        if verbose:
            print(f"  [{i+1}/{len(chunks)}] 추출 중: {chunk.source_file} chunk#{chunk.chunk_index}")
        result = extract_chunk(chunk)
        results.append(result)
    return results
