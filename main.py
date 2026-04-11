"""
GraphRAG PoC 진입점.

사용법:
  # 대화형 모드 (기본)
  python main.py

  # 인덱싱 (최초 1회 또는 --reset)
  python main.py index
  python main.py index --reset

  # 단일 질의
  python main.py query "SK텔레콤이 투자한 AI 기업은?"
"""
import argparse
import sys


def cmd_index(args):
    from src.indexer import run_indexing
    run_indexing(reset=args.reset)


def cmd_query(args):
    from src.query import run_query
    run_query(
        question=args.question,
        top_k=args.top_k,
        hops=args.hops,
    )


def cmd_repl(args):
    from src.query import run_query
    from src.embedder import _get_model
    print("GraphRAG REPL (종료: exit)")
    print("-" * 50)
    print("임베딩 모델 로딩 중... (최초 1회)")
    _get_model()
    print("준비 완료. 질문을 입력하세요.\n")
    while True:
        try:
            question = input("\n질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break
        if question.lower() in ("exit",):
            print("종료합니다.")
            break
        if not question:
            continue
        run_query(question, top_k=args.top_k, hops=args.hops)


def main():
    parser = argparse.ArgumentParser(description="GraphRAG PoC")
    sub = parser.add_subparsers(dest="command")

    # index
    p_index = sub.add_parser("index", help="문서 인덱싱")
    p_index.add_argument("--reset", action="store_true", help="기존 그래프 삭제 후 재인덱싱")
    p_index.set_defaults(func=cmd_index)

    # query
    p_query = sub.add_parser("query", help="단일 질의")
    p_query.add_argument("question", help="질문 문자열")
    p_query.add_argument("--top-k", type=int, default=5, help="벡터 검색 결과 수 (기본: 5)")
    p_query.add_argument("--hops", type=int, default=2, help="그래프 탐색 홉 수 (기본: 2)")
    p_query.set_defaults(func=cmd_query)

    # repl
    p_repl = sub.add_parser("repl", help="대화형 질의")
    p_repl.add_argument("--top-k", type=int, default=5)
    p_repl.add_argument("--hops", type=int, default=2)
    p_repl.set_defaults(func=cmd_repl)

    args = parser.parse_args()
    if args.command is None:
        # 서브커맨드 없이 실행 → 대화형 모드
        args.top_k = 5
        args.hops = 2
        cmd_repl(args)
    else:
        args.func(args)


if __name__ == "__main__":
    main()
