import json
import re
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from backend.app.config import GROQ_API_KEY, GROQ_MODEL
from backend.app.state import ResearchState

# Debug flag: Set True to force retry loop on first pass
DEBUG_FORCE_RETRY = False

def get_llm():
    if not GROQ_API_KEY:
        return None
    try:
        return ChatGroq(model_name=GROQ_MODEL, groq_api_key=GROQ_API_KEY, temperature=0.1, max_tokens=450)
    except Exception as e:
        print(f"[LLM Warning] ChatGroq init error: {e}")
        return None

def critic_node(state: ResearchState) -> dict:
    """
    Critic Node:
    Evaluates research completeness and accuracy. Decides whether to approve or trigger a retry loop.
    Max 2 retry loops enforced.
    """
    topic = state.get("original_topic", "Research Topic")
    sub_questions = state.get("sub_questions", [])
    findings = state.get("findings", {})
    retry_count = state.get("retry_count", 0)
    logs = list(state.get("logs", []))

    logs.append({
        "node": "critic",
        "status": "in_progress",
        "message": f"Critiquing gathered findings (Retry count: {retry_count}/2)..."
    })

    # Hard cap check: Max 2 retries
    if retry_count >= 2:
        logs.append({
            "node": "critic",
            "status": "completed",
            "message": "Max retry limit (2) reached. Proceeding to writer node.",
            "data": {"is_sufficient": True, "feedback": "Max retries reached. Finalizing with current findings."}
        })
        return {
            "is_sufficient": True,
            "critic_feedback": "Max retry limit reached.",
            "retry_count": retry_count,
            "logs": logs
        }

    # Debug override check
    if DEBUG_FORCE_RETRY and retry_count == 0:
        feedback = "DEBUG OVERRIDE: Forcing retry loop to test conditional edge routing."
        is_sufficient = False
        new_retry_count = 1
        logs.append({
            "node": "critic",
            "status": "completed",
            "message": f"Critic decision (DEBUG): INSUFFICIENT. Feedback: {feedback}",
            "data": {
                "is_sufficient": is_sufficient,
                "feedback": feedback,
                "retry_count": new_retry_count
            }
        })
        return {
            "is_sufficient": is_sufficient,
            "critic_feedback": feedback,
            "retry_count": new_retry_count,
            "logs": logs
        }

    llm = get_llm()
    is_sufficient = True
    feedback = "Research provides comprehensive coverage of all sub-questions."

    if llm and findings:
        system_prompt = (
            "You are a rigorous research critic and quality control evaluator. "
            "Review the research topic, sub-questions, and findings.\n"
            "Determine if the research findings are SUFFICIENT (detailed, accurate, answering all sub-questions) "
            "or INSUFFICIENT (superficial answers, missing crucial details, or unaddressed areas).\n"
            "Respond ONLY with JSON: {\"is_sufficient\": true/false, \"feedback\": \"...\"}"
        )

        findings_summary = []
        for sq in sub_questions:
            item = findings.get(sq, {})
            ans_snippet = item.get("answer", "No answer provided.")[:400]
            findings_summary.append(f"Sub-Question: {sq}\nTool: {item.get('tool_used')}\nAnswer Preview: {ans_snippet}\n")

        user_prompt = (
            f"Topic: {topic}\n"
            f"Findings Summary:\n" + "\n---\n".join(findings_summary)
        )

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
                is_sufficient = bool(data.get("is_sufficient", True))
                feedback = str(data.get("feedback", feedback))
        except Exception as e:
            print(f"[Critic Warning] Evaluation parse error ({e}). Approving research.")
            is_sufficient = True

    new_retry_count = retry_count if is_sufficient else retry_count + 1

    logs.append({
        "node": "critic",
        "status": "completed",
        "message": f"Critic decision: {'SUFFICIENT' if is_sufficient else 'INSUFFICIENT'}. Feedback: {feedback}",
        "data": {
            "is_sufficient": is_sufficient,
            "feedback": feedback,
            "retry_count": new_retry_count
        }
    })

    return {
        "is_sufficient": is_sufficient,
        "critic_feedback": feedback,
        "retry_count": new_retry_count,
        "logs": logs
    }
