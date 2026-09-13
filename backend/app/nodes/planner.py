import json
import re
from typing import List, Dict, Any
from langchain_groq import ChatGroq

from backend.app.config import GROQ_API_KEY, GROQ_MODEL
from backend.app.state import ResearchState

def get_llm():
    if not GROQ_API_KEY:
        return None
    try:
        return ChatGroq(model_name=GROQ_MODEL, groq_api_key=GROQ_API_KEY, temperature=0.2, max_tokens=450)
    except Exception as e:
        print(f"[LLM Warning] ChatGroq init error: {e}")
        return None

def planner_node(state: ResearchState) -> dict:
    """
    Planner Node:
    Analyzes the research topic and decomposes it into 3-5 custom, topic-specific sub-questions.
    """
    topic = state.get("original_topic", "").strip()
    if not topic:
        topic = "General Research Topic"

    logs = list(state.get("logs", []))
    logs.append({
        "node": "planner",
        "status": "in_progress",
        "message": f"Planning customized research breakdown for topic: '{topic}'..."
    })

    llm = get_llm()
    sub_questions = []

    if llm:
        prompt = (
            f"You are an expert research strategist. Decompose the following research topic into 3 to 5 concrete, highly tailored sub-questions:\n\n"
            f"Research Topic: {topic}\n\n"
            "Requirements:\n"
            "- Ask specific technical, practical, historical, or domain-specific questions tailored to this topic.\n"
            "- Do NOT use generic boilerplate questions.\n"
            "- Output ONLY a valid raw JSON array of strings, e.g. [\"question 1\", \"question 2\", \"question 3\"]"
        )

        try:
            response = llm.invoke(prompt)
            text = response.content.strip()
            cleaned_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
            
            parsed = None
            try:
                parsed = json.loads(cleaned_text)
            except Exception:
                start_idx = cleaned_text.find("[")
                end_idx = cleaned_text.rfind("]")
                if start_idx != -1 and end_idx > start_idx:
                    try:
                        parsed = json.loads(cleaned_text[start_idx:end_idx+1])
                    except Exception:
                        pass

            if isinstance(parsed, list) and len(parsed) >= 2:
                sub_questions = [str(q).strip() for q in parsed if str(q).strip()]
            elif isinstance(parsed, dict) and "sub_questions" in parsed:
                sub_questions = [str(q).strip() for q in parsed["sub_questions"] if str(q).strip()]
        except Exception as e:
            print(f"[Planner Warning] Groq sub-question breakdown parsing failed ({e}).")

    # Fallback if LLM unavailable or JSON parse failed
    if not sub_questions:
        sub_questions = [
            f"What are the foundational principles, core mechanisms, and current state of {topic}?",
            f"What are the primary applications, technological methods, and practical implementations of {topic}?",
            f"What are the main challenges, limitations, and future outlook surrounding {topic}?"
        ]

    logs.append({
        "node": "planner",
        "status": "completed",
        "message": f"Decomposed topic into {len(sub_questions)} custom sub-questions.",
        "data": {"sub_questions": sub_questions}
    })

    return {
        "sub_questions": sub_questions,
        "logs": logs
    }
