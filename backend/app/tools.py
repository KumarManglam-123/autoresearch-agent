import os
from typing import List, Dict, Any, Optional
from tavily import TavilyClient

from backend.app.config import TAVILY_API_KEY
from backend.app.vector_store import search_documents

# Tavily Client initialization
def get_tavily_client() -> Optional[TavilyClient]:
    if not TAVILY_API_KEY:
        return None
    try:
        return TavilyClient(api_key=TAVILY_API_KEY)
    except Exception as e:
        print(f"[Tools Warning] Tavily client error: {e}")
        return None

def execute_web_search(query: str) -> Dict[str, Any]:
    """
    Executes a web search query using Tavily API free tier.
    Returns results summary and list of sources.
    """
    client = get_tavily_client()
    if not client:
        return {
            "content": f"[Tavily API Key Not Configured] Web search simulation for query: '{query}'.",
            "sources": [{"title": "Web Search (Simulated)", "url": "https://tavily.com"}]
        }

    try:
        response = client.search(query=query, search_depth="basic", max_results=5)
        results = response.get("results", [])
        
        snippets = []
        sources = []
        for item in results:
            title = item.get("title", "Web Source")
            url = item.get("url", "#")
            content = item.get("content", "")
            snippets.append(f"Title: {title}\nURL: {url}\nContent: {content}\n")
            sources.append({"title": title, "url": url})

        combined_content = "\n---\n".join(snippets) if snippets else "No web results returned."
        return {
            "content": combined_content,
            "sources": sources
        }
    except Exception as e:
        print(f"[Tools Error] Tavily Search failed: {e}")
        return {
            "content": f"Web search failed due to error: {str(e)}",
            "sources": []
        }

def execute_document_search(query: str, doc_session_id: str) -> Dict[str, Any]:
    """
    Executes document similarity search in FAISS for doc_session_id.
    """
    doc_results = search_documents(query=query, doc_session_id=doc_session_id, k=4)
    if not doc_results:
        return {
            "content": f"No relevant document sections found for query: '{query}'.",
            "sources": []
        }

    snippets = []
    sources = []
    for res in doc_results:
        source_name = res.get("source", "Uploaded Document")
        page = res.get("page", 1)
        content = res.get("content", "")
        snippets.append(f"Document ({source_name}, Page {page}):\n{content}\n")
        sources.append({"title": f"{source_name} (p. {page})", "url": "#"})

    return {
        "content": "\n---\n".join(snippets),
        "sources": sources
    }
