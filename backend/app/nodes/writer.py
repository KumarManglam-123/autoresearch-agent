import json
import re
from typing import Dict, Any, List
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from backend.app.config import GROQ_API_KEY, GROQ_MODEL
from backend.app.state import ResearchState

def get_llm():
    if not GROQ_API_KEY:
        return None
    try:
        return ChatGroq(model_name=GROQ_MODEL, groq_api_key=GROQ_API_KEY, temperature=0.3, max_tokens=500)
    except Exception as e:
        print(f"[LLM Warning] ChatGroq init error: {e}")
        return None

def writer_node(state: ResearchState) -> dict:
    """
    Writer Node:
    Synthesizes all gathered sub-question findings and sources into a structured final markdown report.
    """
    topic = state.get("original_topic", "Research Topic")
    sub_questions = state.get("sub_questions", [])
    findings = state.get("findings", {})
    logs = list(state.get("logs", []))

    logs.append({
        "node": "writer",
        "status": "in_progress",
        "message": f"Synthesizing final research report for topic: '{topic}'..."
    })

    llm = get_llm()
    final_report = ""

    if llm and findings:
        system_prompt = (
            "You are a world-class research scientist and technical publication author. "
            "Synthesize the provided sub-question findings into a comprehensive, beautifully structured markdown research report.\n\n"
            "Required Markdown Report Structure:\n"
            "# [Comprehensive Report Title]\n"
            "## Executive Summary\n"
            "(A synthesis of the main insights)\n\n"
            "## Key Research Findings\n"
            "(Detailed sections for each sub-question with clear subheadings and empirical details)\n\n"
            "## Strategic Takeaways & Future Outlook\n"
            "(Key conclusions and strategic implications)\n\n"
            "## Sources & References\n"
            "(Bullet point list of all cited sources with titles and clickable Markdown links [Title](URL))\n\n"
            "Do not output commentary or code wrappers—output ONLY the markdown document."
        )

        findings_payload = []
        all_sources = []
        for sq in sub_questions:
            item = findings.get(sq, {})
            ans = item.get("answer", "")
            tool = item.get("tool_used", "N/A")
            srcs = item.get("sources", [])
            all_sources.extend(srcs)
            findings_payload.append(f"### Sub-Question: {sq}\nTool: {tool}\nFindings:\n{ans[:1500]}\n")

        user_prompt = (
            f"Research Topic: {topic}\n\n"
            f"Gathered Research Data:\n" + "\n---\n".join(findings_payload)
        )

        try:
            resp = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            text = resp.content.strip()
            cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
            if cleaned:
                final_report = cleaned
        except Exception as e:
            print(f"[Writer Warning] LLM report generation failed ({e}). Using fallback template.")

    if not final_report:
        report_lines = [
            f"# Autonomous Research Report: {topic}\n",
            "## Executive Summary\n",
            f"This autonomous research report synthesizes key insights regarding **{topic}**.\n",
            "## Detailed Analysis\n"
        ]
        all_sources = []
        for sq, item in findings.items():
            report_lines.append(f"### {sq}\n")
            report_lines.append(f"{item.get('answer', '')}\n")
            report_lines.append(f"*Methodology / Tool: `{item.get('tool_used', 'N/A')}`*\n")
            all_sources.extend(item.get("sources", []))

        report_lines.append("## Sources & References\n")
        dedup_sources = {s.get("url"): s.get("title", "Source") for s in all_sources if s.get("url")}
        if dedup_sources:
            for url, title in dedup_sources.items():
                if url == "#":
                    report_lines.append(f"- {title}")
                else:
                    report_lines.append(f"- [{title}]({url})")
        else:
            report_lines.append("- Internal Model Knowledge / Initial Findings")

        final_report = "\n".join(report_lines)

    logs.append({
        "node": "writer",
        "status": "completed",
        "message": "Final research report successfully generated and formatted."
    })

    return {
        "final_report": final_report,
        "logs": logs
    }
