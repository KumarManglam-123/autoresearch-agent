from typing import TypedDict, List, Dict, Any, Optional

class FindingItem(TypedDict, total=False):
    sub_question: str
    answer: str
    tool_used: str  # "web_search", "document_search", "model_knowledge"
    tool_reason: str
    sources: List[Dict[str, str]]

class ResearchState(TypedDict, total=False):
    session_id: str
    original_topic: str
    sub_questions: List[str]
    findings: Dict[str, FindingItem]  # Map sub_question -> FindingItem
    critic_feedback: Optional[str]
    is_sufficient: bool
    retry_count: int
    final_report: str
    doc_session_id: Optional[str]  # ID for uploaded FAISS document index if present
    logs: List[Dict[str, Any]]     # Step execution logs emitted during graph run
