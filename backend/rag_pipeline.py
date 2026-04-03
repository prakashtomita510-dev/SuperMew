from typing import Literal, TypedDict, List, Optional
import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from rag_utils import retrieve_documents, step_back_expand, generate_hypothetical_document
from tools import emit_rag_step

load_dotenv()

API_KEY = os.getenv("ARK_API_KEY")
MODEL = os.getenv("MODEL")
BASE_URL = os.getenv("BASE_URL")
GRADE_MODEL = os.getenv("GRADE_MODEL", "gpt-4.1")

_grader_model = None
_router_model = None


def _get_grader_model():
    global _grader_model
    if not API_KEY or not GRADE_MODEL:
        return None
    if _grader_model is None:
        _grader_model = init_chat_model(
            model=GRADE_MODEL,
            model_provider="openai",
            api_key=API_KEY,
            base_url=BASE_URL,
            temperature=0,
            stream_usage=True,
        )
    return _grader_model


def _get_router_model():
    global _router_model
    if not API_KEY or not MODEL:
        return None
    if _router_model is None:
        _router_model = init_chat_model(
            model=MODEL,
            model_provider="openai",
            api_key=API_KEY,
            base_url=BASE_URL,
            temperature=0,
            stream_usage=True,
        )
    return _router_model


GRADE_PROMPT = (
    "You are a grader assessing relevance of a retrieved document to a user question. \n "
    "Here is the retrieved document: \n\n {context} \n\n"
    "Here is the user question: {question} \n"
    "If the document contains keyword(s) or semantic meaning related to the user question, grade it as relevant. \n"
    "Give a binary score 'yes' or 'no' score to indicate whether the document is relevant to the question."
)

HALLUCINATION_PROMPT = (
    "You are a grader assessing whether an LLM generation is grounded in / supported by a set of retrieved documents. \n"
    "Give a binary score 'yes' or 'no'. 'yes' means that the answer is grounded in / supported by the documents."
)

ANSWER_PROMPT = (
    "You are a helpful assistant. "
    "Use the following context to answer the question. \n\n"
    "Context: \n {context} \n\n"
    "Question: {question} \n"
    "Answer (provide citations like [1], [2] if applicable):"
)

ROUTER_PROMPT = (
    "You are an expert router. Classify the user question into one of these categories:\n"
    "1. 'weather': Questions about current weather, temperature, or forecast.\n"
    "2. 'rag': Questions that require searching the knowledge base (documents, facts, technical info).\n"
    "3. 'chitchat': General greetings, small talk, or questions that don't need external data.\n"
    "Return only the category name."
)

MULTI_QUERY_PROMPT = (
    "You are an AI language model assistant. Your task is to generate 3 "
    "different versions of the given user question to retrieve relevant documents from a vector "
    "database. By generating multiple perspectives on the user queston, your goal is to help "
    "the user overcome some of the limitations of the distance-based similarity search. \n"
    "Provide these alternative questions separated by newlines.\n"
    "Original question: {question}"
)


class GradeDocuments(BaseModel):
    """Grade documents using a binary score for relevance check."""

    binary_score: str = Field(
        description="Relevance score: 'yes' if relevant, or 'no' if not relevant"
    )


class GradeHallucination(BaseModel):
    """Grade whether the answer is grounded in the documents."""

    binary_score: str = Field(
        description="Groundedness score: 'yes' if grounded in docs, or 'no' if not"
    )


class RewriteStrategy(BaseModel):
    """Choose a query expansion strategy."""

    strategy: Literal["step_back", "hyde", "complex"]


class QueryRoute(BaseModel):
    """Route user query to the appropriate tool or flow."""
    category: Literal["weather", "rag", "chitchat"]


class MultiQuery(BaseModel):
    """A list of queries generated for better retrieval."""
    queries: List[str] = Field(description="List of 3 search queries")


class RAGState(TypedDict):
    question: str
    query: str
    queries: List[str]
    context: str
    docs: List[dict]
    route: Optional[str]
    intent: Optional[str]
    expansion_type: Optional[str]
    expanded_query: Optional[str]
    step_back_question: Optional[str]
    step_back_answer: Optional[str]
    hypothetical_doc: Optional[str]
    answer: Optional[str]
    hallucination_score: Optional[str]
    retries: int
    rag_trace: Optional[dict]


def _format_docs(docs: List[dict]) -> str:
    if not docs:
        return ""
    chunks = []
    for i, doc in enumerate(docs, 1):
        source = doc.get("filename", "Unknown")
        page = doc.get("page_number", "N/A")
        text = doc.get("text", "")
        # Embed chunk metadata for citation lookup in trace
        chunks.append(f"[{i}] {source} (Page {page}):\n{text}")
    return "\n\n---\n\n".join(chunks)


def route_query_node(state: RAGState) -> RAGState:
    question = state["question"]
    emit_rag_step("🚦", "正在分析意图...")
    router = _get_router_model()
    
    if not router:
        return {"intent": "rag", "route": "rag"}

    intent = "rag"
    try:
        # Try structured output first
        response = router.with_structured_output(QueryRoute).invoke(
            [{"role": "user", "content": ROUTER_PROMPT + f"\n\nQuestion: {question}"}]
        )
        intent = response.category
    except Exception:
        # Fallback to manual parsing
        try:
            raw_res = router.invoke([{"role": "user", "content": ROUTER_PROMPT + f"\n\nReturn ONLY the category name. Question: {question}"}])
            text = raw_res.content.strip().lower()
            if "weather" in text: intent = "weather"
            elif "chitchat" in text: intent = "chitchat"
            else: intent = "rag"
        except:
            intent = "rag"

    if intent == "chitchat":
        emit_rag_step("💬", "闲聊模式", "直接生成回答")
        response = router.invoke([{"role": "user", "content": f"You are a helpful assistant. Respond to: {question}"}])
        return {"intent": "chitchat", "answer": response.content, "route": "chitchat"}
    
    if intent == "weather":
        emit_rag_step("🌤️", "天气查询", "分发至天气工具")
        return {"intent": "weather", "route": "weather"}

    emit_rag_step("📚", "知识库查询", "进入 RAG 流程")
    return {"intent": "rag", "route": "rag"}


def decompose_query_node(state: RAGState) -> RAGState:
    question = state["question"]
    emit_rag_step("🔭", "多查询分解...")
    model = _get_router_model()
    
    if not model:
        return {"queries": [question]}

    queries = [question]
    try:
        response = model.with_structured_output(MultiQuery).invoke(
            [{"role": "user", "content": MULTI_QUERY_PROMPT.format(question=question)}]
        )
        if response.queries:
            queries = response.queries
    except Exception:
        try:
            raw_res = model.invoke([{"role": "user", "content": MULTI_QUERY_PROMPT.format(question=question)}])
            # Simple line-based split
            lines = [l.strip() for l in raw_res.content.split('\n') if l.strip()]
            if len(lines) >= 1:
                queries = lines[:3]
        except:
            queries = [question]
    
    emit_rag_step("💡", f"已生成 {len(queries)} 个子查询", ", ".join(queries[:2]) + "...")
    return {"queries": queries}


def retrieve_initial(state: RAGState) -> RAGState:
    queries = state.get("queries") or [state["question"]]
    all_results = []
    seen = set()
    
    emit_rag_step("🔍", "并行检索中...", f"执行 {len(queries)} 路查询")
    
    # Simple aggregation for now (sequential for reliability, concurrent and deduped)
    for q in queries:
        retrieved = retrieve_documents(q, top_k=3)
        docs = retrieved.get("docs", [])
        for d in docs:
            # Dedup by content
            key = (d.get("filename"), d.get("text")[:100])
            if key not in seen:
                seen.add(key)
                all_results.append(d)
    
    # Sort by score or rank if available (mock uses Numpy scores)
    all_results = sorted(all_results, key=lambda x: x.get("score", 0), reverse=True)[:5]
    
    context = _format_docs(all_results)
    emit_rag_step("✅", f"检索完成，合并 {len(all_results)} 个片段")
    
    rag_trace = {
        "tool_used": True,
        "queries": queries,
        "retrieved_chunks": all_results,
        "retrieval_stage": "initial",
    }
    return {
        "docs": all_results,
        "context": context,
        "rag_trace": rag_trace,
    }


def grade_documents_node(state: RAGState) -> RAGState:
    grader = _get_grader_model()
    emit_rag_step("📊", "正在评估文档相关性...")
    if not grader:
        grade_update = {
            "grade_score": "unknown",
            "grade_route": "rewrite_question",
            "rewrite_needed": True,
        }
        rag_trace = state.get("rag_trace", {}) or {}
        rag_trace.update(grade_update)
        return {"route": "rewrite_question", "rag_trace": rag_trace}
    question = state["question"]
    context = state.get("context", "")
    prompt = GRADE_PROMPT.format(question=question, context=context)
    try:
        response = grader.with_structured_output(GradeDocuments).invoke(
            [{"role": "user", "content": prompt}]
        )
    except Exception as e:
        # Fallback to 'yes' if grading fails to avoid breaking the UI for now, but label it
        emit_rag_step("⚠️", "评估过程出错 (JSON 解析失败)", f"错误详情: {str(e)}")
        score = "yes" # Default to yes for testing
        route = "generate_answer"
        grade_update = {
            "grade_score": score,
            "grade_route": route,
            "grade_error": str(e),
            "rewrite_needed": False,
        }
        rag_trace = state.get("rag_trace", {}) or {}
        rag_trace.update(grade_update)
        return {"route": route, "rag_trace": rag_trace}

    score = (response.binary_score or "").strip().lower()
    route = "generate_answer" if score == "yes" else "rewrite_question"
    if route == "generate_answer":
        emit_rag_step("✅", "文档相关性评估通过", f"评分: {score}")
    else:
        emit_rag_step("⚠️", "文档相关性不足，将重写查询", f"评分: {score}")
    grade_update = {
        "grade_score": score,
        "grade_route": route,
        "rewrite_needed": route == "rewrite_question",
    }
    rag_trace = state.get("rag_trace", {}) or {}
    rag_trace.update(grade_update)
    return {"route": route, "rag_trace": rag_trace}


def rewrite_question_node(state: RAGState) -> RAGState:
    question = state["question"]
    emit_rag_step("✏️", "正在重写查询...")
    router = _get_router_model()
    strategy = "step_back"
    if router:
        prompt = (
            "请根据用户问题选择最合适的查询扩展策略，仅输出策略名。\n"
            "- step_back：包含具体名称、日期、代码等细节，需要先理解通用概念的问题。\n"
            "- hyde：模糊、概念性、需要解释或定义的问题。\n"
            "- complex：多步骤、需要分解或综合多种信息的复杂问题。\n"
            f"用户问题：{question}"
        )
        try:
            decision = router.with_structured_output(RewriteStrategy).invoke(
                [{"role": "user", "content": prompt}]
            )
            strategy = decision.strategy
        except Exception:
            strategy = "step_back"

    expanded_query = question
    step_back_question = ""
    step_back_answer = ""
    hypothetical_doc = ""

    if strategy in ("step_back", "complex"):
        emit_rag_step("🧠", f"使用策略: {strategy}", "生成退步问题")
        step_back = step_back_expand(question)
        step_back_question = step_back.get("step_back_question", "")
        step_back_answer = step_back.get("step_back_answer", "")
        expanded_query = step_back.get("expanded_query", question)

    if strategy in ("hyde", "complex"):
        emit_rag_step("📝", "HyDE 假设性文档生成中...")
        hypothetical_doc = generate_hypothetical_document(question)

    rag_trace = state.get("rag_trace", {}) or {}
    rag_trace.update({
        "rewrite_strategy": strategy,
        "rewrite_query": expanded_query,
    })

    return {
        "expansion_type": strategy,
        "expanded_query": expanded_query,
        "step_back_question": step_back_question,
        "step_back_answer": step_back_answer,
        "hypothetical_doc": hypothetical_doc,
        "rag_trace": rag_trace,
    }


def retrieve_expanded(state: RAGState) -> RAGState:
    strategy = state.get("expansion_type") or "step_back"
    emit_rag_step("🔄", "使用扩展查询重新检索...", f"策略: {strategy}")
    results: List[dict] = []
    rerank_applied_any = False
    rerank_enabled_any = False
    rerank_model = None
    rerank_endpoint = None
    rerank_errors = []
    retrieval_mode = None
    candidate_k = None
    leaf_retrieve_level = None
    auto_merge_enabled = None
    auto_merge_applied = False
    auto_merge_threshold = None
    auto_merge_replaced_chunks = 0
    auto_merge_steps = 0

    if strategy in ("hyde", "complex"):
        hypothetical_doc = state.get("hypothetical_doc") or generate_hypothetical_document(state["question"])
        retrieved_hyde = retrieve_documents(hypothetical_doc, top_k=5)
        results.extend(retrieved_hyde.get("docs", []))
        hyde_meta = retrieved_hyde.get("meta", {})
        emit_rag_step(
            "🧱",
            "HyDE 三级检索",
            (
                f"L{hyde_meta.get('leaf_retrieve_level', 3)} 召回，"
                f"候选 {hyde_meta.get('candidate_k', 0)}，"
                f"合并替换 {hyde_meta.get('auto_merge_replaced_chunks', 0)}"
            ),
        )
        rerank_applied_any = rerank_applied_any or bool(hyde_meta.get("rerank_applied"))
        rerank_enabled_any = rerank_enabled_any or bool(hyde_meta.get("rerank_enabled"))
        rerank_model = rerank_model or hyde_meta.get("rerank_model")
        rerank_endpoint = rerank_endpoint or hyde_meta.get("rerank_endpoint")
        if hyde_meta.get("rerank_error"):
            rerank_errors.append(f"hyde:{hyde_meta.get('rerank_error')}")
        retrieval_mode = retrieval_mode or hyde_meta.get("retrieval_mode")
        candidate_k = candidate_k or hyde_meta.get("candidate_k")
        leaf_retrieve_level = leaf_retrieve_level or hyde_meta.get("leaf_retrieve_level")
        auto_merge_enabled = auto_merge_enabled if auto_merge_enabled is not None else hyde_meta.get("auto_merge_enabled")
        auto_merge_applied = auto_merge_applied or bool(hyde_meta.get("auto_merge_applied"))
        auto_merge_threshold = auto_merge_threshold or hyde_meta.get("auto_merge_threshold")
        auto_merge_replaced_chunks += int(hyde_meta.get("auto_merge_replaced_chunks") or 0)
        auto_merge_steps += int(hyde_meta.get("auto_merge_steps") or 0)

    if strategy in ("step_back", "complex"):
        expanded_query = state.get("expanded_query") or state["question"]
        retrieved_stepback = retrieve_documents(expanded_query, top_k=5)
        results.extend(retrieved_stepback.get("docs", []))
        step_meta = retrieved_stepback.get("meta", {})
        emit_rag_step(
            "🧱",
            "Step-back 三级检索",
            (
                f"L{step_meta.get('leaf_retrieve_level', 3)} 召回，"
                f"候选 {step_meta.get('candidate_k', 0)}，"
                f"合并替换 {step_meta.get('auto_merge_replaced_chunks', 0)}"
            ),
        )
        rerank_applied_any = rerank_applied_any or bool(step_meta.get("rerank_applied"))
        rerank_enabled_any = rerank_enabled_any or bool(step_meta.get("rerank_enabled"))
        rerank_model = rerank_model or step_meta.get("rerank_model")
        rerank_endpoint = rerank_endpoint or step_meta.get("rerank_endpoint")
        if step_meta.get("rerank_error"):
            rerank_errors.append(f"step_back:{step_meta.get('rerank_error')}")
        retrieval_mode = retrieval_mode or step_meta.get("retrieval_mode")
        candidate_k = candidate_k or step_meta.get("candidate_k")
        leaf_retrieve_level = leaf_retrieve_level or step_meta.get("leaf_retrieve_level")
        auto_merge_enabled = auto_merge_enabled if auto_merge_enabled is not None else step_meta.get("auto_merge_enabled")
        auto_merge_applied = auto_merge_applied or bool(step_meta.get("auto_merge_applied"))
        auto_merge_threshold = auto_merge_threshold or step_meta.get("auto_merge_threshold")
        auto_merge_replaced_chunks += int(step_meta.get("auto_merge_replaced_chunks") or 0)
        auto_merge_steps += int(step_meta.get("auto_merge_steps") or 0)

    deduped = []
    seen = set()
    for item in results:
        key = (item.get("filename"), item.get("page_number"), item.get("text"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    # 扩展阶段可能合并了多路召回（如 hyde + step_back），
    # 这里统一重排展示名次，避免出现 1,2,3,4,5,4,5 这类重复名次。
    for idx, item in enumerate(deduped, 1):
        item["rrf_rank"] = idx

    context = _format_docs(deduped)
    emit_rag_step("✅", f"扩展检索完成，共 {len(deduped)} 个片段")
    rag_trace = state.get("rag_trace", {}) or {}
    rag_trace.update({
        "expanded_query": state.get("expanded_query") or state["question"],
        "step_back_question": state.get("step_back_question", ""),
        "step_back_answer": state.get("step_back_answer", ""),
        "hypothetical_doc": state.get("hypothetical_doc", ""),
        "expansion_type": strategy,
        "retrieved_chunks": deduped,
        "expanded_retrieved_chunks": deduped,
        "retrieval_stage": "expanded",
        "rerank_enabled": rerank_enabled_any,
        "rerank_applied": rerank_applied_any,
        "rerank_model": rerank_model,
        "rerank_endpoint": rerank_endpoint,
        "rerank_error": "; ".join(rerank_errors) if rerank_errors else None,
        "retrieval_mode": retrieval_mode,
        "candidate_k": candidate_k,
        "leaf_retrieve_level": leaf_retrieve_level,
        "auto_merge_enabled": auto_merge_enabled,
        "auto_merge_applied": auto_merge_applied,
        "auto_merge_threshold": auto_merge_threshold,
        "auto_merge_replaced_chunks": auto_merge_replaced_chunks,
        "auto_merge_steps": auto_merge_steps,
    })
    return {"docs": deduped, "context": context, "rag_trace": rag_trace}


def generate_answer_node(state: RAGState) -> RAGState:
    """Generate an answer based on the context."""
    question = state["question"]
    context = state["context"]
    emit_rag_step("✍️", "正在生成回答...")
    
    model = _get_router_model()
    prompt = ANSWER_PROMPT.format(question=question, context=context)
    
    response = model.invoke([{"role": "user", "content": prompt}])
    answer = response.content
    
    rag_trace = state.get("rag_trace", {}) or {}
    rag_trace.update({"generated_answer": answer})
    
    return {"answer": answer, "rag_trace": rag_trace}


def grade_hallucination_node(state: RAGState) -> RAGState:
    """Grade the generated answer for hallucinations."""
    context = state["context"]
    answer = state["answer"]
    retries = state.get("retries", 0)
    
    emit_rag_step("🕵️", "正在检测幻觉 (Groundedness)...")
    
    grader = _get_grader_model()
    if not grader:
        return {"hallucination_score": "yes", "route": "finalize"}

    prompt = HALLUCINATION_PROMPT + f"\n\nContext: {context} \n\nGeneration: {answer}"
    
    try:
        response = grader.with_structured_output(GradeHallucination).invoke(
            [{"role": "user", "content": prompt}]
        )
        score = (response.binary_score or "yes").strip().lower()
    except Exception:
        score = "yes"  # Fallback to yes
        
    if score == "yes":
        emit_rag_step("🛡️", "已通过幻觉检测", "回答基于检索文档")
        route = "finalize"
    else:
        if retries < 2:
            emit_rag_step("🚨", "发现疑似幻觉，正在重试生成...", f"重试次数: {retries + 1}")
            route = "retry"
        else:
            emit_rag_step("⚠️", "多次尝试后仍存在幻觉，将标注输出")
            route = "finalize"
            
    rag_trace = state.get("rag_trace", {}) or {}
    rag_trace.update({
        "hallucination_score": score,
        "hallucination_retries": retries,
        "hallucination_route": route
    })
    
    return {"hallucination_score": score, "route": route, "retries": retries + 1, "rag_trace": rag_trace}


def build_rag_graph():
    graph = StateGraph(RAGState)
    graph.add_node("route_query", route_query_node)
    graph.add_node("decompose_query", decompose_query_node)
    graph.add_node("retrieve_initial", retrieve_initial)
    graph.add_node("grade_documents", grade_documents_node)
    graph.add_node("rewrite_question", rewrite_question_node)
    graph.add_node("retrieve_expanded", retrieve_expanded)
    graph.add_node("generate_answer", generate_answer_node)
    graph.add_node("grade_hallucination", grade_hallucination_node)

    graph.set_entry_point("route_query")
    
    graph.add_conditional_edges(
        "route_query",
        lambda state: state.get("route"),
        {
            "rag": "decompose_query",
            "weather": END, # Will be handled by tool in next turn
            "chitchat": END,
        },
    )
    
    graph.add_edge("decompose_query", "retrieve_initial")
    graph.add_edge("retrieve_initial", "grade_documents")
    
    graph.add_conditional_edges(
        "grade_documents",
        lambda state: state.get("route"),
        {
            "generate_answer": "generate_answer",
            "rewrite_question": "rewrite_question",
        },
    )
    
    graph.add_edge("rewrite_question", "retrieve_expanded")
    graph.add_edge("retrieve_expanded", "generate_answer")
    
    graph.add_edge("generate_answer", "grade_hallucination")
    
    graph.add_conditional_edges(
        "grade_hallucination",
        lambda state: state.get("route"),
        {
            "finalize": END,
            "retry": "generate_answer",
        },
    )
    
    return graph.compile()


rag_graph = build_rag_graph()


def run_rag_graph(question: str) -> dict:
    return rag_graph.invoke({
        "question": question,
        "query": question,
        "queries": [],
        "context": "",
        "docs": [],
        "answer": None,
        "hallucination_score": None,
        "retries": 0,
        "route": None,
        "expansion_type": None,
        "expanded_query": None,
        "step_back_question": None,
        "step_back_answer": None,
        "hypothetical_doc": None,
        "rag_trace": None,
    })
