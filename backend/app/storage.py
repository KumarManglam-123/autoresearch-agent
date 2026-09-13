import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from backend.app.config import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    DYNAMODB_TABLE_NAME,
    S3_BUCKET_NAME,
    LOCAL_STORAGE_DIR
)

# File path for local fallback storage when AWS is unconfigured
LOCAL_SESSIONS_FILE = LOCAL_STORAGE_DIR / "sessions_fallback.json"

def _get_boto3_session():
    """Create a boto3 session if credentials exist."""
    kwargs = {"region_name": AWS_REGION}
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = AWS_SECRET_ACCESS_KEY
    return boto3.Session(**kwargs)

def _get_dynamodb_table():
    """Get DynamoDB table resource."""
    try:
        session = _get_boto3_session()
        dynamodb = session.resource("dynamodb")
        table = dynamodb.Table(DYNAMODB_TABLE_NAME)
        # Quick load check
        _ = table.table_status
        return table
    except Exception as e:
        print(f"[Storage Warning] DynamoDB connection issue ({e}). Using local fallback.")
        return None

def _get_s3_client():
    """Get S3 client configured with regional endpoint for valid presigned URLs."""
    try:
        session = _get_boto3_session()
        endpoint_url = f"https://s3.{AWS_REGION}.amazonaws.com"
        config = Config(
            region_name=AWS_REGION,
            signature_version="s3v4"
        )
        client = session.client("s3", endpoint_url=endpoint_url, config=config)
        return client
    except Exception as e:
        print(f"[Storage Warning] S3 connection issue ({e}). Using local fallback.")
        return None

# --- Local Fallback Helpers ---
def _load_local_sessions() -> Dict[str, Dict[str, Any]]:
    if not LOCAL_SESSIONS_FILE.exists():
        return {}
    try:
        with open(LOCAL_SESSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_local_sessions(sessions: Dict[str, Dict[str, Any]]) -> None:
    with open(LOCAL_SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f, indent=2, ensure_ascii=False)

# --- Public API (Preserving Signatures) ---

def save_session(session_data: Dict[str, Any]) -> None:
    """
    Saves or updates research session in DynamoDB and uploads report to S3.
    Fallback to local storage if AWS is unreachable.
    """
    session_id = session_data.get("session_id")
    if not session_id:
        raise ValueError("session_id is required to save session")

    created_at = session_data.get("created_at") or datetime.utcnow().isoformat()
    item = {
        "session_id": str(session_id),
        "original_topic": str(session_data.get("original_topic", "")),
        "sub_questions": session_data.get("sub_questions", []),
        "final_report": str(session_data.get("final_report", "")),
        "created_at": str(created_at),
        "retry_count": int(session_data.get("retry_count", 0)),
        "doc_session_id": str(session_data.get("doc_session_id", "")) if session_data.get("doc_session_id") else ""
    }

    # 1. Save Session Meta to DynamoDB
    table = _get_dynamodb_table()
    dynamo_success = False
    if table:
        try:
            table.put_item(Item=item)
            dynamo_success = True
        except (BotoCoreError, ClientError) as e:
            print(f"[DynamoDB Error] Failed to save session {session_id}: {e}")

    # Fallback to local storage if DynamoDB failed
    if not dynamo_success:
        local_db = _load_local_sessions()
        local_db[session_id] = item
        _save_local_sessions(local_db)

    # 2. Upload final report markdown file to S3 if final_report exists
    final_report = session_data.get("final_report")
    if final_report:
        s3 = _get_s3_client()
        s3_success = False
        if s3:
            try:
                s3.put_object(
                    Bucket=S3_BUCKET_NAME,
                    Key=f"reports/{session_id}.md",
                    Body=final_report.encode("utf-8"),
                    ContentType="text/markdown"
                )
                s3_success = True
            except (BotoCoreError, ClientError) as e:
                print(f"[S3 Error] Failed to upload report for {session_id}: {e}")

        # Save local backup copy as well
        local_report_path = LOCAL_STORAGE_DIR / f"{session_id}.md"
        with open(local_report_path, "w", encoding="utf-8") as f:
            f.write(final_report)

def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve session by session_id."""
    table = _get_dynamodb_table()
    if table:
        try:
            resp = table.get_item(Key={"session_id": session_id})
            if "Item" in resp:
                item = resp["Item"]
                if "retry_count" in item:
                    item["retry_count"] = int(item["retry_count"])
                return item
        except (BotoCoreError, ClientError) as e:
            print(f"[DynamoDB Error] Failed to fetch session {session_id}: {e}")

    # Fallback
    local_db = _load_local_sessions()
    return local_db.get(session_id)

def list_sessions() -> List[Dict[str, Any]]:
    """List all research sessions ordered by created_at descending."""
    table = _get_dynamodb_table()
    sessions = []
    if table:
        try:
            resp = table.scan()
            sessions = resp.get("Items", [])
            for s in sessions:
                if "retry_count" in s:
                    s["retry_count"] = int(s["retry_count"])
        except (BotoCoreError, ClientError) as e:
            print(f"[DynamoDB Error] Failed to scan sessions: {e}")

    if not sessions:
        local_db = _load_local_sessions()
        sessions = list(local_db.values())

    # Sort descending by created_at
    sessions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return sessions

def delete_session(session_id: str) -> bool:
    """Delete a research session from DynamoDB and S3."""
    table = _get_dynamodb_table()
    if table:
        try:
            table.delete_item(Key={"session_id": session_id})
        except Exception as e:
            print(f"[DynamoDB Warning] Failed to delete item {session_id}: {e}")

    s3 = _get_s3_client()
    if s3:
        try:
            s3.delete_object(Bucket=S3_BUCKET_NAME, Key=f"reports/{session_id}.md")
        except Exception as e:
            print(f"[S3 Warning] Failed to delete report {session_id}: {e}")

    # Delete local fallback
    local_db = _load_local_sessions()
    if session_id in local_db:
        del local_db[session_id]
        _save_local_sessions(local_db)

    local_report_path = LOCAL_STORAGE_DIR / f"{session_id}.md"
    if local_report_path.exists():
        try:
            local_report_path.unlink()
        except Exception:
            pass

    return True

def generate_report_download_url(session_id: str) -> Optional[str]:
    """
    Generates a pre-signed S3 download URL for the report.
    Returns None if S3 is unreachable or report does not exist.
    """
    s3 = _get_s3_client()
    if s3:
        try:
            url = s3.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": S3_BUCKET_NAME,
                    "Key": f"reports/{session_id}.md",
                    "ResponseContentDisposition": f'attachment; filename="report-{session_id}.md"'
                },
                ExpiresIn=3600  # 1 hour expiration
            )
            return url
        except (BotoCoreError, ClientError) as e:
            print(f"[S3 Error] Presigned URL generation failed: {e}")

    return None
