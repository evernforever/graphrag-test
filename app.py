"""
GraphRAG Streamlit UI.

실행:
  streamlit run app.py
"""
import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config

# ── 엔티티 타입별 색상 ─────────────────────────────────────
ENTITY_COLORS = {
    "Company":    "#5A9EC9",
    "Person":     "#5DB88A",
    "Product":    "#E8943A",
    "Technology": "#9575CD",
    "Event":      "#E8708A",
    "Document":   "#78909C",
}
DEFAULT_COLOR = "#BDC3C7"


def entity_color(etype: str) -> str:
    return ENTITY_COLORS.get(etype, DEFAULT_COLOR)


# ── 그래프 렌더링 ──────────────────────────────────────────

def render_graph(entities: list[dict], relations: list[dict]):
    if not entities and not relations:
        st.info("표시할 그래프 데이터가 없습니다.")
        return

    seen_nodes: set[str] = set()
    nodes: list[Node] = []
    edges: list[Edge] = []

    def add_node(name: str, etype: str):
        if name not in seen_nodes:
            seen_nodes.add(name)
            nodes.append(
                Node(
                    id=name,
                    label=name,
                    size=20,
                    color=entity_color(etype),
                    font={"size": 12},
                )
            )

    hl = st.session_state.highlighted_relation
    highlighted_nodes: set[str] = set()

    for r in relations:
        if hl and r["relation"] == hl:
            highlighted_nodes.add(r["source"])
            highlighted_nodes.add(r["target"])

    for e in entities:
        add_node(e["name"], e["type"])

    for r in relations:
        add_node(r["source"], r.get("source_type", ""))
        add_node(r["target"], r.get("target_type", ""))
        is_hl = hl and r["relation"] == hl
        edges.append(
            Edge(
                source=r["source"],
                target=r["target"],
                label=r["relation"],
                color={"color": "#E53935", "opacity": 1.0} if is_hl else {"color": "#AAAAAA", "opacity": 0.6},
                width=3 if is_hl else 1,
                font={"size": 10, "align": "middle", "color": "#E53935" if is_hl else "#555555"},
            )
        )

    # 하이라이트된 노드 색상 강조
    if highlighted_nodes:
        for node in nodes:
            if node.id in highlighted_nodes:
                node.size = 28
                node.borderWidth = 3

    config = Config(
        width="100%",
        height=280,
        directed=True,
        physics=True,
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#F0E130",
        collapsible=False,
        node={"labelProperty": "label"},
        link={"labelProperty": "label", "renderLabel": True},
    )

    agraph(nodes=nodes, edges=edges, config=config)


# ── 출처 청크 카드 ────────────────────────────────────────

def render_source_chunks(chunks: list[dict]):
    if not chunks:
        return
    st.markdown("**📄 출처**")
    for i, c in enumerate(chunks, 1):
        with st.expander(f"[출처{i}] {c['source_file']}  (유사도: {c['score']:.3f})"):
            st.markdown(c["text"])


# ── 관계 타입 버튼 ────────────────────────────────────────

def render_relation_buttons(relations: list[dict], msg_idx: int):
    if not relations:
        return
    rel_types = sorted({r["relation"] for r in relations})
    st.markdown("**🔗 관계 타입** (클릭하면 그래프에서 강조)")
    per_row = 3
    for row_start in range(0, len(rel_types), per_row):
        row_rels = rel_types[row_start:row_start + per_row]
        cols = st.columns(per_row)
        for col, rel in zip(cols, row_rels):
            is_active = st.session_state.highlighted_relation == rel
            if col.button(
                rel,
                key=f"rel_{msg_idx}_{rel}",
                type="primary" if is_active else "secondary",
                use_container_width=True,
            ):
                st.session_state.highlighted_relation = None if is_active else rel
                st.rerun()


# ── 범례 ──────────────────────────────────────────────────

def render_legend():
    items = list(ENTITY_COLORS.items())
    rows = [items[:3], items[3:]]
    html = "<div style='line-height:1.4'>"
    for row in rows:
        html += "<div style='margin-bottom:2px'>"
        for etype, color in row:
            html += (
                f"<span style='background:{color};border-radius:4px;"
                f"padding:1px 6px;color:white;font-size:11px;"
                f"margin-right:4px'>{etype}</span>"
            )
        html += "</div>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


# ── 세션 상태 초기화 ───────────────────────────────────────

def init_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_graph" not in st.session_state:
        st.session_state.last_graph = {"entities": [], "relations": []}
    if "model_ready" not in st.session_state:
        st.session_state.model_ready = False
    if "highlighted_relation" not in st.session_state:
        st.session_state.highlighted_relation = None


# ── 메인 ──────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="GraphRAG Demo",
        page_icon="🔗",
        layout="wide",
    )
    init_state()

    st.markdown("""
        <style>
            [data-testid="stSidebar"] { min-width: 350px; }
            [data-testid="stSidebarContent"] { padding-top: 0; }
        </style>
    """, unsafe_allow_html=True)

    st.title("🔗 GraphRAG Demo")
    st.caption("한국 테크 기업 생태계 — 벡터 검색 + 그래프 탐색")

    # 사이드바: 설정 + 관계 그래프 + 샘플 파일
    with st.sidebar:
        # 설정
        st.subheader("설정")
        graph_search = st.toggle("그래프 탐색", value=True, help="OFF: 벡터 검색만 사용")

        col_tk, col_hp = st.columns(2)
        top_k = col_tk.slider("top-k", 1, 10, 5)
        hops  = col_hp.slider("홉 수", 1, 3, 2, disabled=not graph_search)

        with st.expander("📋 예제 질문"):
            st.caption("우측 아이콘을 클릭하면 복사됩니다")
            st.code(
                "SK텔레콤이 자체 출시한 AI 서비스와 투자한 글로벌 AI 기업을 모두 찾고, "
                "해당 투자 기업이 또 어떤 거대 클라우드 기업들과 파트너십을 맺고 있는지 "
                "연결해서 설명해 줘",
                language=None,
                wrap_lines=True,
            )

        if st.button("대화 초기화", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_graph = {"entities": [], "relations": []}
            st.rerun()

        # 관계 그래프
        st.subheader("관계 그래프")
        with st.container(border=True):
            render_legend()
            render_graph(
                st.session_state.last_graph["entities"],
                st.session_state.last_graph["relations"],
            )

        # 관계 온톨로지
        st.divider()
        st.subheader("관계 온톨로지")
        from src.config import RELATION_TYPES
        RELATION_DESC = {
            "WORKS_AT":        "소속 / 재직",
            "LAUNCHED":        "출시 / 런칭",
            "PARTNERED_WITH":  "파트너십 체결",
            "INVESTED_IN":     "투자",
            "RELATED_TO":      "연관",
            "MERGED_WITH":     "합병",
            "ACQUIRED_BY":     "인수됨",
        }
        for rel in RELATION_TYPES:
            desc = RELATION_DESC.get(rel, "")
            st.markdown(f"- **{rel}** — {desc}")

        # 샘플 데이터 파일 목록
        st.divider()
        st.subheader("샘플 데이터")
        from src.config import DATA_DIR
        from src.graph import GraphStore
        txt_files = sorted(DATA_DIR.glob("*.txt"))
        for f in txt_files:
            with st.expander(f.name):
                tab_raw, tab_chunks = st.tabs(["원문", "청크"])
                with tab_raw:
                    st.markdown(f.read_text(encoding="utf-8"))
                with tab_chunks:
                    try:
                        with GraphStore() as gs:
                            chunks = gs.get_chunks_by_file(f.name)
                        if chunks:
                            for c in chunks:
                                st.markdown(
                                    f"**[청크 {c['idx']}]**\n\n{c['text']}",
                                    help=f"chunk_index: {c['idx']}",
                                )
                                st.divider()
                        else:
                            st.info("인덱싱 후 청크가 표시됩니다.")
                    except Exception:
                        st.warning("Neo4j 연결 불가")

    st.subheader("대화")

    # 모델 워밍업 (최초 1회)
    if not st.session_state.model_ready:
        with st.spinner("임베딩 모델 로딩 중... (최초 1회)"):
            from src.embedder import _get_model
            _get_model()
            st.session_state.model_ready = True

    # 이전 대화 출력
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                if msg.get("chunks"):
                    render_source_chunks(msg["chunks"])
                if msg.get("relations"):
                    render_relation_buttons(msg["relations"], idx)

    # 사용자 입력
    if question := st.chat_input("질문을 입력하세요..."):
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            # 그래프 탐색
            with st.spinner("그래프 탐색 중..."):
                from src.query import search_context, stream_answer
                chunks, entities, relations = search_context(
                    question, top_k=top_k, hops=hops, graph_search=graph_search
                )
                st.session_state.last_graph = {
                    "entities": entities,
                    "relations": relations,
                }
                st.session_state.highlighted_relation = None

            # 스트리밍 답변
            TIMEOUT = 10.0  # 초
            try:
                answer = st.write_stream(
                    stream_answer(question, chunks, entities, relations, timeout=TIMEOUT)
                )
            except Exception as e:
                import anthropic as _anthropic
                if isinstance(e, _anthropic.APITimeoutError):
                    st.error("⏱️ API 응답 시간이 초과되었습니다 (10초). 다시 시도해 주세요.")
                else:
                    st.error(f"오류가 발생했습니다: {e}")
                answer = ""

            render_source_chunks(chunks)
            render_relation_buttons(relations, len(st.session_state.messages))

        st.session_state.messages.append({
            "role": "assistant",
            "content": answer,
            "chunks": chunks,
            "relations": relations,
        })

        # 그래프 업데이트를 위해 rerun
        st.rerun()


if __name__ == "__main__":
    main()
