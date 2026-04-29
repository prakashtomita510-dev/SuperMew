from typing import Literal, TypedDict, List, Optional
import os
import time
import json
import warnings
from dotenv import load_dotenv

# Suppress pymilvus/pkg_resources warning
warnings.filterwarnings("ignore", category=UserWarning, module="pkg_resources")
warnings.filterwarnings("ignore", category=UserWarning, module="pymilvus")
from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from rag_utils import retrieve_documents, batch_retrieve_documents, step_back_expand, generate_hypothetical_document
from tools import emit_rag_step

load_dotenv()

API_KEY = os.getenv("ARK_API_KEY")
MODEL = os.getenv("MODEL")
BASE_URL = os.getenv("BASE_URL")
GRADE_MODEL = os.getenv("GRADE_MODEL", "gpt-4.1")
RAG_REWRITE_MODE = os.getenv("RAG_REWRITE_MODE", "auto").strip().lower()
RAG_HYBRID_WEIGHTS = os.getenv("RAG_HYBRID_WEIGHTS")
if RAG_HYBRID_WEIGHTS:
    try:
        RAG_HYBRID_WEIGHTS = [float(w) for w in RAG_HYBRID_WEIGHTS.split(",")]
    except:
        RAG_HYBRID_WEIGHTS = None
else:
    RAG_HYBRID_WEIGHTS = None

RAG_CANDIDATE_K = os.getenv("RAG_CANDIDATE_K")
if RAG_CANDIDATE_K:
    RAG_CANDIDATE_K = int(RAG_CANDIDATE_K)
else:
    RAG_CANDIDATE_K = None

RAG_RERANK_ENABLED = os.getenv("RAG_RERANK_ENABLED")
if RAG_RERANK_ENABLED is not None:
    RAG_RERANK_ENABLED = RAG_RERANK_ENABLED.lower() == "true"
else:
    RAG_RERANK_ENABLED = None

RAG_STREAM_ENABLED = os.getenv("RAG_STREAM_ENABLED", "false").lower() == "true"

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
    "You are a grader assessing whether the retrieved context is SUFFICIENT to answer the user question. \n"
    "Retrieved Context: \n\n {context} \n\n"
    "User Question: {question} \n"
    "Criteria: \n"
    "1. Does the context contain the specific answer? \n"
    "2. If the question is complex or ambiguous, does the context resolve all parts? \n"
    "Return a JSON object with a 'binary_score' field: 'yes' if the context is sufficient, 'no' if it is missing information."
)

HALLUCINATION_PROMPT = (
    "You are a grader assessing whether an LLM generation is grounded in / supported by a set of retrieved documents. \n"
    "Return a JSON object with a 'binary_score' field: 'yes' if the answer is grounded in / supported by the documents, 'no' otherwise."
)

ANSWER_PROMPT = (
    "You are a helpful assistant. Use the provided context to answer the question concisely. \n\n"
    "Context: \n {context} \n\n"
    "Question: {question} \n"
    "Instructions: \n"
    "1. You MUST answer in Chinese (简体中文). \n"
    "2. Provide a direct answer. DO NOT use conversational padding like 'Based on the context' or '综上所述'. Extract the answer as closely to the original text as possible. \n"
    "3. Use citations like [1], [2] for each factual point. \n"
    "4. If the context does not contain the answer, you MUST reply with exactly: '暂无相关信息' and nothing else. \n"
    "Answer:"
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


def _record_stage_timing(rag_trace: Optional[dict], stage_key: str, elapsed_ms: float) -> dict:
    trace = rag_trace or {}
    timings = dict(trace.get("stage_timings_ms") or {})
    timings[stage_key] = round(float(elapsed_ms), 2)
    trace["stage_timings_ms"] = timings
    return trace


def _increment_stage_timing(rag_trace: Optional[dict], stage_key: str, elapsed_ms: float) -> dict:
    trace = rag_trace or {}
    timings = dict(trace.get("stage_timings_ms") or {})
    timings[stage_key] = round(float(timings.get(stage_key, 0.0)) + float(elapsed_ms), 2)
    trace["stage_timings_ms"] = timings
    return trace


def _normalize_binary_score(value: str | None) -> str:
    text = (value or "").strip().lower()
    if text in {"yes", "no"}:
        return text
    if "yes" in text and "no" not in text:
        return "yes"
    if "no" in text and "yes" not in text:
        return "no"
    return "unknown"


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
    started_at = time.perf_counter()
    queries = state.get("queries") or [state["question"]]
    all_results = []
    seen = set()
    retrieval_modes = []
    vector_backends = []
    rerank_applied_any = False
    rerank_enabled_any = False
    rerank_model = None
    rerank_endpoint = None
    rerank_errors = []
    candidate_k = None
    leaf_retrieve_level = None
    auto_merge_enabled = None
    auto_merge_applied = False
    auto_merge_threshold = None
    auto_merge_replaced_chunks = 0
    auto_merge_steps = 0
    
    emit_rag_step("🔍", "并行检索中...", f"执行 {len(queries)} 路查询")
    
    # Batch retrieval to save on embedding API calls and rate-limit waits
    batch_results = batch_retrieve_documents(
        queries, 
        top_k=3, 
        hybrid_weights=RAG_HYBRID_WEIGHTS,
        candidate_k=RAG_CANDIDATE_K,
        rerank_enabled=RAG_RERANK_ENABLED
    )
    
    for i, retrieved in enumerate(batch_results):
        q = queries[i]
        docs = retrieved.get("docs", [])
        meta = retrieved.get("meta", {})
        retrieval_mode = meta.get("retrieval_mode")
        if retrieval_mode:
            retrieval_modes.append(retrieval_mode)
        vector_backend = meta.get("vector_backend")
        if vector_backend:
            vector_backends.append(vector_backend)
        rerank_applied_any = rerank_applied_any or bool(meta.get("rerank_applied"))
        rerank_enabled_any = rerank_enabled_any or bool(meta.get("rerank_enabled"))
        rerank_model = rerank_model or meta.get("rerank_model")
        rerank_endpoint = rerank_endpoint or meta.get("rerank_endpoint")
        if meta.get("rerank_error"):
            rerank_errors.append(f"{q}:{meta.get('rerank_error')}")
        candidate_k = candidate_k or meta.get("candidate_k")
        leaf_retrieve_level = leaf_retrieve_level or meta.get("leaf_retrieve_level")
        auto_merge_enabled = auto_merge_enabled if auto_merge_enabled is not None else meta.get("auto_merge_enabled")
        auto_merge_applied = auto_merge_applied or bool(meta.get("auto_merge_applied"))
        auto_merge_threshold = auto_merge_threshold or meta.get("auto_merge_threshold")
        auto_merge_replaced_chunks += int(meta.get("auto_merge_replaced_chunks") or 0)
        auto_merge_steps += int(meta.get("auto_merge_steps") or 0)
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
    
    rag_trace = state.get("rag_trace", {}) or {}
    rag_trace.update({
        "tool_used": True,
        "tool_name": "search_knowledge_base",
        "query": state["question"],
        "queries": queries,
        "initial_retrieved_chunks": all_results,
        "retrieved_chunks": all_results,
        "retrieval_stage": "initial",
        "retrieval_mode": "+".join(dict.fromkeys(retrieval_modes)) if retrieval_modes else None,
        "vector_backend": "+".join(dict.fromkeys(vector_backends)) if vector_backends else None,
        "rerank_enabled": rerank_enabled_any,
        "rerank_applied": rerank_applied_any,
        "rerank_model": rerank_model,
        "rerank_endpoint": rerank_endpoint,
        "rerank_error": "; ".join(rerank_errors) if rerank_errors else None,
        "candidate_k": candidate_k,
        "leaf_retrieve_level": leaf_retrieve_level,
        "auto_merge_enabled": auto_merge_enabled,
        "auto_merge_applied": auto_merge_applied,
        "auto_merge_threshold": auto_merge_threshold,
        "auto_merge_replaced_chunks": auto_merge_replaced_chunks,
        "auto_merge_steps": auto_merge_steps,
    })
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    rag_trace = _record_stage_timing(rag_trace, "retrieve_initial_ms", elapsed_ms)
    rag_trace = _increment_stage_timing(rag_trace, "retrieve_ms", elapsed_ms)
    return {
        "docs": all_results,
        "context": context,
        "rag_trace": rag_trace,
    }


def grade_documents_node(state: RAGState) -> RAGState:
    grader = _get_grader_model()
    emit_rag_step("📊", "正在评估文档相关性...")
    if RAG_REWRITE_MODE == "off":
        route = "generate_answer"
        grade_update = {
            "grade_score": "skipped",
            "grade_route": route,
            "grade_error": None,
            "rewrite_needed": False,
            "rewrite_mode": "off",
        }
        rag_trace = state.get("rag_trace", {}) or {}
        rag_trace.update(grade_update)
        emit_rag_step("⏭️", "已禁用 rewrite，对照实验直接生成回答")
        return {"route": route, "rag_trace": rag_trace}
    if not grader:
        grade_update = {
            "grade_score": "unknown",
            "grade_route": "rewrite_question",
            "rewrite_needed": True,
            "rewrite_mode": RAG_REWRITE_MODE,
        }
        rag_trace = state.get("rag_trace", {}) or {}
        rag_trace.update(grade_update)
        return {"route": "rewrite_question", "rag_trace": rag_trace}
    if RAG_REWRITE_MODE in {"step_back", "hyde", "complex", "always_step_back", "always_hyde"}:
        route = "rewrite_question"
        grade_update = {
            "grade_score": "forced",
            "grade_route": route,
            "grade_error": None,
            "rewrite_needed": True,
            "rewrite_mode": RAG_REWRITE_MODE,
        }
        rag_trace = state.get("rag_trace", {}) or {}
        rag_trace.update(grade_update)
        emit_rag_step("🧭", "已按评测配置强制启用 rewrite", f"模式: {RAG_REWRITE_MODE}")
        return {"route": route, "rag_trace": rag_trace}
    question = state["question"]
    context = state.get("context", "")
    prompt = GRADE_PROMPT.format(question=question, context=context)
    try:
        response = grader.with_structured_output(GradeDocuments).invoke(
            [{"role": "user", "content": prompt}]
        )
        if hasattr(response, "binary_score"):
            score = _normalize_binary_score(response.binary_score)
        else:
            # If the model returned a dict instead of a pydantic object
            score = _normalize_binary_score(response.get("binary_score", ""))
        grade_error = None
    except Exception as e:
        # Check if the error is just a JSON parsing error of a plain 'yes'/'no' string or markdown block
        err_str = str(e).lower()
        if "yes" in err_str or "no" in err_str:
            score = "yes" if "yes" in err_str else "no"
            grade_error = f"Parsed from error: {err_str}"
        else:
            emit_rag_step("⚠️", "评估过程出错，降级为文本解析", f"错误详情: {str(e)}")
            grade_error = str(e)
            try:
                # Try to invoke and manually parse
                raw_res = grader.invoke([{"role": "user", "content": prompt + "\nReturn ONLY a JSON object. No markdown blocks."}])
                content = getattr(raw_res, "content", "")
                
                # Robust extraction using regex
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group(0))
                        score = _normalize_binary_score(parsed.get("binary_score", ""))
                    except:
                        score = _normalize_binary_score(content)
                else:
                    score = _normalize_binary_score(content)
            except Exception as fallback_exc:
                grade_error = f"{grade_error}; fallback={fallback_exc}"
                score = "unknown"

    if score not in {"yes", "no"}:
        emit_rag_step("⚠️", "文档相关性评估不确定，将进入重写", f"评分: {score}")
        route = "rewrite_question"
        grade_update = {
            "grade_score": score,
            "grade_route": route,
            "grade_error": grade_error,
            "rewrite_needed": True,
            "rewrite_mode": RAG_REWRITE_MODE,
        }
        rag_trace = state.get("rag_trace", {}) or {}
        rag_trace.update(grade_update)
        return {"route": route, "rag_trace": rag_trace}
    route = "generate_answer" if score == "yes" else "rewrite_question"
    if route == "generate_answer":
        emit_rag_step("✅", "文档相关性评估通过", f"评分: {score}")
    else:
        emit_rag_step("⚠️", "文档相关性不足，将重写查询", f"评分: {score}")
    grade_update = {
        "grade_score": score,
        "grade_route": route,
        "grade_error": grade_error,
        "rewrite_needed": route == "rewrite_question",
        "rewrite_mode": RAG_REWRITE_MODE,
    }
    rag_trace = state.get("rag_trace", {}) or {}
    rag_trace.update(grade_update)
    return {"route": route, "rag_trace": rag_trace}


def rewrite_question_node(state: RAGState) -> RAGState:
    started_at = time.perf_counter()
    question = state["question"]
    emit_rag_step("✏️", "正在重写查询...")
    if RAG_REWRITE_MODE == "off":
        rag_trace = state.get("rag_trace", {}) or {}
        rag_trace.update({
            "rewrite_strategy": "disabled",
            "rewrite_query": question,
            "rewrite_mode": "off",
        })
        rag_trace = _record_stage_timing(rag_trace, "rewrite_ms", 0.0)
        return {
            "expansion_type": "disabled",
            "expanded_query": question,
            "step_back_question": "",
            "step_back_answer": "",
            "hypothetical_doc": "",
            "rag_trace": rag_trace,
        }
    router = _get_router_model()
    strategy = "step_back"
    forced_strategy = {
        "step_back": "step_back",
        "always_step_back": "step_back",
        "hyde": "hyde",
        "always_hyde": "hyde",
        "complex": "complex",
    }.get(RAG_REWRITE_MODE)
    if forced_strategy:
        strategy = forced_strategy
    elif router:
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
        "rewrite_mode": RAG_REWRITE_MODE,
    })
    rag_trace = _record_stage_timing(rag_trace, "rewrite_ms", (time.perf_counter() - started_at) * 1000)

    return {
        "expansion_type": strategy,
        "expanded_query": expanded_query,
        "step_back_question": step_back_question,
        "step_back_answer": step_back_answer,
        "hypothetical_doc": hypothetical_doc,
        "rag_trace": rag_trace,
    }


def retrieve_expanded(state: RAGState) -> RAGState:
    started_at = time.perf_counter()
    strategy = state.get("expansion_type") or "step_back"
    emit_rag_step("🔄", "使用扩展查询重新检索...", f"策略: {strategy}")
    results: List[dict] = []
    rerank_applied_any = False
    rerank_enabled_any = False
    rerank_model = None
    rerank_endpoint = None
    rerank_errors = []
    retrieval_mode = None
    vector_backend = None
    candidate_k = None
    leaf_retrieve_level = None
    auto_merge_enabled = None
    auto_merge_applied = False
    auto_merge_threshold = None
    auto_merge_replaced_chunks = 0
    auto_merge_steps = 0

    if strategy in ("hyde", "complex"):
        hypothetical_doc = state.get("hypothetical_doc") or generate_hypothetical_document(state["question"])
        # Single query HyDE - batching doesn't help much here but we keep it consistent
        retrieved_hyde = batch_retrieve_documents(
            [hypothetical_doc], 
            top_k=5, 
            hybrid_weights=RAG_HYBRID_WEIGHTS,
            candidate_k=RAG_CANDIDATE_K,
            rerank_enabled=RAG_RERANK_ENABLED
        )[0]
        results.extend(retrieved_hyde.get("docs", []))
        hyde_meta = retrieved_hyde.get("meta", {})
        emit_rag_step("🧪", "HyDE 检索完成", f"召回 {len(retrieved_hyde.get('docs', []))} 个片段")
        rerank_applied_any = rerank_applied_any or bool(hyde_meta.get("rerank_applied"))
        rerank_enabled_any = rerank_enabled_any or bool(hyde_meta.get("rerank_enabled"))
        rerank_model = rerank_model or hyde_meta.get("rerank_model")
        rerank_endpoint = rerank_endpoint or hyde_meta.get("rerank_endpoint")
        if hyde_meta.get("rerank_error"):
            rerank_errors.append(f"hyde:{hyde_meta.get('rerank_error')}")
        retrieval_mode = retrieval_mode or hyde_meta.get("retrieval_mode")
        vector_backend = vector_backend or hyde_meta.get("vector_backend")
        candidate_k = candidate_k or hyde_meta.get("candidate_k")
        leaf_retrieve_level = leaf_retrieve_level or hyde_meta.get("leaf_retrieve_level")
        auto_merge_enabled = auto_merge_enabled if auto_merge_enabled is not None else hyde_meta.get("auto_merge_enabled")
        auto_merge_applied = auto_merge_applied or bool(hyde_meta.get("auto_merge_applied"))
        auto_merge_threshold = auto_merge_threshold or hyde_meta.get("auto_merge_threshold")
        auto_merge_replaced_chunks += int(hyde_meta.get("auto_merge_replaced_chunks") or 0)
        auto_merge_steps += int(hyde_meta.get("auto_merge_steps") or 0)

    if strategy in ("step_back", "complex"):
        expanded_query = state.get("expanded_query") or state["question"]
        retrieved_stepback = batch_retrieve_documents(
            [expanded_query], 
            top_k=5, 
            hybrid_weights=RAG_HYBRID_WEIGHTS,
            candidate_k=RAG_CANDIDATE_K,
            rerank_enabled=RAG_RERANK_ENABLED
        )[0]
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
        vector_backend = vector_backend or step_meta.get("vector_backend")
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
        "vector_backend": vector_backend,
        "candidate_k": candidate_k,
        "leaf_retrieve_level": leaf_retrieve_level,
        "auto_merge_enabled": auto_merge_enabled,
        "auto_merge_applied": auto_merge_applied,
        "auto_merge_threshold": auto_merge_threshold,
        "auto_merge_replaced_chunks": auto_merge_replaced_chunks,
        "auto_merge_steps": auto_merge_steps,
    })
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    rag_trace = _record_stage_timing(rag_trace, "retrieve_expanded_ms", elapsed_ms)
    rag_trace = _increment_stage_timing(rag_trace, "retrieve_ms", elapsed_ms)
    return {"docs": deduped, "context": context, "rag_trace": rag_trace}


def generate_answer_node(state: RAGState) -> RAGState:
    """Generate an answer based on the context."""
    started_at = time.perf_counter()
    question = state["question"]
    context = state["context"]
    emit_rag_step("✍️", "正在生成回答...")
    
    model = _get_router_model()
    prompt = ANSWER_PROMPT.format(question=question, context=context)
    
    ttft_ms = None
    if RAG_STREAM_ENABLED:
        full_content = []
        for chunk in model.stream([{"role": "user", "content": prompt}]):
            if ttft_ms is None:
                ttft_ms = (time.perf_counter() - started_at) * 1000
            if hasattr(chunk, "content"):
                full_content.append(chunk.content)
            else:
                full_content.append(str(chunk))
        answer = "".join(full_content)
    else:
        response = model.invoke([{"role": "user", "content": prompt}])
        answer = response.content
        ttft_ms = (time.perf_counter() - started_at) * 1000 # For sync, TTFT is essentially the same as total generate time or at least we mark it when we get the object
    
    rag_trace = state.get("rag_trace", {}) or {}
    rag_trace.update({"generated_answer": answer})
    if ttft_ms is not None:
        rag_trace = _record_stage_timing(rag_trace, "ttft_ms", ttft_ms)
    rag_trace = _record_stage_timing(rag_trace, "generate_ms", (time.perf_counter() - started_at) * 1000)
    
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
        score = _normalize_binary_score(response.binary_score)
    except Exception:
        try:
            raw_res = grader.invoke([{"role": "user", "content": prompt + "\nReturn only yes or no."}])
            score = _normalize_binary_score(getattr(raw_res, "content", ""))
        except Exception:
            score = "unknown"
        
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
