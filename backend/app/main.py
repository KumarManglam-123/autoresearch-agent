import asyncio
import json
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend.app.config import HOST, PORT, LOCAL_STORAGE_DIR
from backend.app.graph import research_graph
from backend.app.storage import (
    save_session,
    get_session,
    list_sessions,
    delete_session,
    generate_report_download_url
)

app = FastAPI(
    title="AutoResearch Agent API",
    description="Multi-Agent Autonomous Research Agent using LangGraph, Groq (Llama 3.3 70B), Tavily, FAISS, and AWS",
    version="1.0.0"
)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount frontend static directory if exists
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

class ResearchRequest(BaseModel):
    topic: str = Field(..., description="Research topic to investigate")
    doc_session_id: Optional[str] = Field(None, description="Optional vector store session ID for uploaded documents")

@app.get("/")
def read_root():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"status": "ok", "message": "AutoResearch Agent Backend API operational"}

@app.post("/api/upload-document")
async def upload_document(file: UploadFile = File(...)):
    """
    Upload PDF or TXT document, extract text chunks, and index into FAISS vector store.
    Lazy-imports process_and_index_document to conserve memory until a user uploads a file.
    """
    ext = Path(file.filename).suffix.lower()
    if ext not in [".pdf", ".txt", ".md"]:
        raise HTTPException(status_code=400, detail="Only PDF, TXT, and MD files are supported.")

    doc_session_id = f"doc_{uuid.uuid4().hex[:10]}"
    temp_dir = LOCAL_STORAGE_DIR / "uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{doc_session_id}_{file.filename}"

    try:
        content = await file.read()
        with open(temp_path, "wb") as f:
            f.write(content)

        from backend.app.vector_store import process_and_index_document
        result = process_and_index_document(str(temp_path), doc_session_id)
        return {
            "status": "success",
            "message": f"Document '{file.filename}' processed and indexed successfully!",
            "doc_session_id": doc_session_id,
            "details": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass

@app.post("/api/research/stream")
async def stream_research(request: ResearchRequest):
    """
    Initiates autonomous research pipeline and streams step-by-step reasoning via Server-Sent Events (SSE).
    """
    topic = request.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Research topic cannot be empty.")

    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    doc_session_id = request.doc_session_id

    async def event_generator():
        initial_state = {
            "session_id": session_id,
            "original_topic": topic,
            "sub_questions": [],
            "findings": {},
            "critic_feedback": None,
            "is_sufficient": False,
            "retry_count": 0,
            "final_report": "",
            "doc_session_id": doc_session_id,
            "logs": []
        }

        current_state = dict(initial_state)

        # Stream node status updates
        yield {
            "event": "node_start",
            "data": json.dumps({
                "node": "planner",
                "session_id": session_id,
                "message": f"Initiating research planner for topic: '{topic}'..."
            })
        }
        await asyncio.sleep(0.2)

        try:
            # Execute LangGraph nodes in stream mode
            for output in research_graph.stream(initial_state):
                for node_name, node_state in output.items():
                    current_state.update(node_state)
                    logs = node_state.get("logs", [])
                    latest_log = logs[-1] if logs else {}

                    if node_name == "planner":
                        sub_qs = node_state.get("sub_questions", [])
                        yield {
                            "event": "sub_questions_planned",
                            "data": json.dumps({
                                "node": "planner",
                                "sub_questions": sub_qs,
                                "message": f"Planned {len(sub_qs)} sub-questions."
                            })
                        }

                    elif node_name == "researcher":
                        findings = node_state.get("findings", {})
                        for sq, item in findings.items():
                            yield {
                                "event": "tool_activity",
                                "data": json.dumps({
                                    "node": "researcher",
                                    "sub_question": sq,
                                    "tool_used": item.get("tool_used"),
                                    "tool_reason": item.get("tool_reason"),
                                    "sources": item.get("sources", [])
                                })
                            }

                    elif node_name == "critic":
                        yield {
                            "event": "critic_review",
                            "data": json.dumps({
                                "node": "critic",
                                "is_sufficient": node_state.get("is_sufficient"),
                                "feedback": node_state.get("critic_feedback"),
                                "retry_count": node_state.get("retry_count"),
                                "message": latest_log.get("message", "Critic evaluation completed.")
                            })
                        }

                    elif node_name == "writer":
                        report = node_state.get("final_report", "")
                        # Chunk report for streaming simulation
                        chunk_size = 300
                        for i in range(0, len(report), chunk_size):
                            chunk = report[i:i + chunk_size]
                            yield {
                                "event": "report_chunk",
                                "data": json.dumps({"chunk": chunk})
                            }
                            await asyncio.sleep(0.05)

                await asyncio.sleep(0.1)

            # Save session to DynamoDB / Local Storage and upload report to S3
            save_session({
                "session_id": session_id,
                "original_topic": topic,
                "sub_questions": current_state.get("sub_questions", []),
                "final_report": current_state.get("final_report", ""),
                "retry_count": current_state.get("retry_count", 0),
                "doc_session_id": doc_session_id
            })

            # Emit completion event
            yield {
                "event": "complete",
                "data": json.dumps({
                    "session_id": session_id,
                    "topic": topic,
                    "final_report": current_state.get("final_report", ""),
                    "message": "Research complete! Report saved."
                })
            }

        except Exception as e:
            print(f"[SSE Error] Pipeline execution failed: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"message": f"Execution error: {str(e)}"})
            }

    return EventSourceResponse(event_generator())

@app.get("/api/sessions")
def get_all_sessions():
    """List all research sessions."""
    try:
        sessions = list_sessions()
        return {"status": "success", "count": len(sessions), "sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {str(e)}")

@app.get("/api/sessions/{session_id}")
def get_single_session(session_id: str):
    """Retrieve details of a single research session."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return {"status": "success", "session": session}

@app.delete("/api/sessions/{session_id}")
def remove_session(session_id: str):
    """Delete a research session from DynamoDB and S3."""
    success = delete_session(session_id)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to delete session '{session_id}'.")
    return {"status": "success", "message": f"Session '{session_id}' deleted successfully."}

@app.get("/api/reports/{session_id}/download")
def download_report(session_id: str):
    """
    Get pre-signed AWS S3 URL for downloading report .md file.
    Falls back to direct file download if S3 is unconfigured.
    """
    presigned_url = generate_report_download_url(session_id)
    if presigned_url:
        return {"status": "success", "download_type": "presigned_s3", "download_url": presigned_url}

    # Fallback to local report file download
    local_report = LOCAL_STORAGE_DIR / f"{session_id}.md"
    if local_report.exists():
        return FileResponse(
            path=str(local_report),
            filename=f"report-{session_id}.md",
            media_type="text/markdown"
        )

    raise HTTPException(status_code=404, detail=f"Report file for session '{session_id}' not found.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=HOST, port=PORT, reload=True)
