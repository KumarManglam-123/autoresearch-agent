import json
import re
from typing import Dict, Any, List
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from backend.app.config import GROQ_API_KEY, GROQ_MODEL
from backend.app.state import ResearchState, FindingItem
from backend.app.tools import execute_web_search, execute_document_search

def get_llm():
    if not GROQ_API_KEY:
        return None
    try:
        return ChatGroq(model_name=GROQ_MODEL, groq_api_key=GROQ_API_KEY, temperature=0.2, max_tokens=450)
    except Exception as e:
        print(f"[LLM Warning] ChatGroq init error: {e}")
        return None

def select_tool(llm, sub_question: str, topic: str, has_docs: bool) -> tuple[str, str]:
    """
    Decides which tool to call ('web_search', 'document_search', or 'model_knowledge')
    and returns (tool_name, tool_reason).
    """
    if not llm:
        if has_docs:
            return "document_search", "Uploaded documents are available for inquiry."
        return "web_search", "Retrieving real-time information from web search."

    available_tools = ["web_search", "model_knowledge"]
    if has_docs:
        available_tools.append("document_search")

    system_prompt = (
        f"You are an autonomous research decision agent. Select the single best tool to answer a sub-question.\n"
        f"Available tools: {', '.join(available_tools)}\n"
        "Rules:\n"
        "- Use 'document_search' if uploaded documents are available and relevant.\n"
        "- Use 'web_search' for current facts, statistics, recent news, or technical details.\n"
        "- Use 'model_knowledge' if the query is conceptual or basic knowledge.\n"
        "Respond ONLY with JSON: {\"tool\": \"...\", \"reason\": \"...\"}"
    )
    user_prompt = f"Topic: {topic}\nSub-Question: {sub_question}"

    try:
        resp = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])
        text = resp.content.strip()
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            tool = data.get("tool", "").lower()
            reason = data.get("reason", "Autonomous tool selection based on topic requirements.")
            if tool in available_tools:
                return tool, reason
    except Exception as e:
        print(f"[Researcher Warning] Tool selection parse error ({e}). Defaulting tool.")

    if has_docs:
        return "document_search", "Defaulting to document search for uploaded context."
    return "web_search", "Defaulting to web search for relevant evidence."

def researcher_node(state: ResearchState) -> dict:
    """
    Researcher Node:
    For each sub-question, selects appropriate tool, gathers evidence, and synthesizes findings.
    """
    topic = state.get("original_topic", "Research Topic")
    sub_questions = state.get("sub_questions", [])
    findings = dict(state.get("findings", {}))
    logs = list(state.get("logs", []))
    doc_session_id = state.get("doc_session_id")
    has_docs = bool(doc_session_id)
    critic_feedback = state.get("critic_feedback")

    llm = get_llm()

    logs.append({
        "node": "researcher",
        "status": "in_progress",
        "message": f"Executing research across {len(sub_questions)} sub-questions..."
    })

    for sq in sub_questions:
        if sq in findings and not critic_feedback:
            continue

        tool_name, tool_reason = select_tool(llm, sq, topic, has_docs)

        logs.append({
            "node": "researcher",
            "status": "tool_selected",
            "sub_question": sq,
            "tool_used": tool_name,
            "tool_reason": tool_reason,
            "message": f"Sub-question: '{sq}' -> Tool: {tool_name} ({tool_reason})"
        })

        raw_evidence = ""
        sources = []

        if tool_name == "web_search":
            search_query = f"{topic} {sq}"
            res = execute_web_search(search_query)
            raw_evidence = res.get("content", "")
            sources = res.get("sources", [])

        elif tool_name == "document_search" and doc_session_id:
            res = execute_document_search(sq, doc_session_id)
            raw_evidence = res.get("content", "")
            sources = res.get("sources", [])

        else:
            raw_evidence = f"Using foundational domain knowledge regarding {sq}."
            sources = [{"title": f"Model Knowledge ({GROQ_MODEL})", "url": "#"}]

        if critic_feedback:
            raw_evidence += f"\n\nAdditional Guidance from Critic: {critic_feedback}"

        answer = raw_evidence
        if llm:
            synth_system = (
                "You are an expert academic research analyst. Synthesize the provided tool evidence "
                "into a comprehensive, highly informative response to the sub-question. "
                "Be thorough and cite facts clearly."
            )
            synth_user = (
                f"Sub-Question: {sq}\n\n"
                f"Tool Used: {tool_name}\n"
                f"Raw Tool Evidence:\n{raw_evidence[:2000]}"
            )
            try:
                resp = llm.invoke([
                    SystemMessage(content=synth_system),
                    HumanMessage(content=synth_user)
                ])
                text = resp.content.strip()
                cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
                if cleaned:
                    answer = cleaned
            except Exception as e:
                print(f"[Researcher Warning] Synthesis failed ({e}). Using raw evidence.")

        findings[sq] = FindingItem(
            sub_question=sq,
            answer=answer,
            tool_used=tool_name,
            tool_reason=tool_reason,
            sources=sources
        )

    logs.append({
        "node": "researcher",
        "status": "completed",
        "message": f"Completed research for {len(findings)} sub-questions."
    })

    return {
        "findings": findings,
        "logs": logs
    }
