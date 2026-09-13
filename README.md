# 🤖 AutoResearch — Full-Stack Autonomous Multi-Agent System

**AutoResearch** is an autonomous multi-agent research assistant that decomposes complex topics, executes web and document searches, critiques research thoroughness through self-correction, and synthesizes comprehensive, well-cited markdown reports streamed in real time.

---

## 🏗 System Architecture & Multi-Agent Loop

AutoResearch is orchestrated as a state machine using **LangGraph**. The workflow cycles through four specialized agent nodes with a strict self-critique retry loop capped at 2 iterations to avoid infinite loops:

```
                          ┌───────────────────────────┐
                          │   User Research Request   │
                          └─────────────┬─────────────┘
                                        │
                                        ▼
                          ┌───────────────────────────┐
                          │       Planner Node        │
                          │   (Groq Llama 3.3 70B)    │
                          └─────────────┬─────────────┘
                                        │ (3-5 Sub-Questions)
                                        ▼
    ┌───────────────────────────────────────────────────────────────────────┐
    │                         Researcher Node                               │
    │  Autonomously selects tool per sub-question & synthesizes findings:   │
    │   • Web Search: Tavily API                                            │
    │   • Document Search: FAISS + HuggingFace (all-MiniLM-L6-v2)           │
    │   • Model Knowledge: Direct domain inference                          │
    └───────────────────────────────────┬───────────────────────────────────┘
                                        │
                                        ▼
                          ┌───────────────────────────┐
                          │        Critic Node        │ ──┐
                          │  (Reviews Completeness)   │   │
                          └─────────────┬─────────────┘   │ Retry Loop (Insufficient)
                                        │                 │ Max 2 Retries
                                        ├─────────────────┘
                                        │ (Sufficient or Max Retries)
                                        ▼
                          ┌───────────────────────────┐
                          │        Writer Node        │
                          │  (Formats Final Markdown) │
                          └─────────────┬─────────────┘
                                        │
                                        ▼
                   ┌─────────────────────────────────────────┐
                   │               AWS Storage               │
                   │ • Session Metadata ──> AWS DynamoDB     │
                   │ • Report Files     ──> AWS S3           │
                   └─────────────────────────────────────────┘
```

---

## 🛠 Tech Stack

- **Backend Framework:** FastAPI (Python 3.12)
- **Agent Orchestration:** LangGraph (`StateGraph`, conditional edges)
- **LLM Engine:** Groq API (`llama-3.3-70b-versatile` via `langchain-groq`)
- **Web Search Tool:** Tavily API
- **Document Vector Store:** FAISS + HuggingFace Embeddings (`sentence-transformers/all-MiniLM-L6-v2`) + PyPDF
- **Cloud Infrastructure (AWS):**
  - **Amazon DynamoDB:** Persistent session history table (`autoresearch-sessions`)
  - **Amazon S3:** Markdown report file storage (`autoresearch-reports`) with pre-signed download URLs
- **Real-Time Streaming:** Server-Sent Events (SSE via `sse-starlette`)
- **Frontend:** Vanilla HTML5, CSS3, JavaScript (ES6+), FontAwesome, and `marked.js`
- **Containerization:** Docker & Docker Compose

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+ installed
- Groq API Key ([Get Groq Key](https://console.groq.com/))
- Tavily API Key ([Get Tavily Key](https://tavily.com/))
- AWS Account & Credentials (optional for cloud persistence; fallback storage included for local testing)

### 2. Environment Configuration
Copy the `.env.example` file to `.env` in the root directory:

```bash
cp .env.example .env
```

Update your credentials in `.env`:
```env
GROQ_API_KEY=gsk_your_groq_api_key
TAVILY_API_KEY=tvly-your_tavily_api_key
GROQ_MODEL=llama-3.3-70b-versatile

AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_REGION=ap-south-1
DYNAMODB_TABLE_NAME=autoresearch-sessions
S3_BUCKET_NAME=autoresearch-reports
```

### 3. Local Installation & Setup

1. Install Python dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```

2. Provision AWS Infrastructure (DynamoDB & S3):
   ```bash
   python scripts/setup_aws.py
   ```

3. Launch the FastAPI server:
   ```bash
   uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. Open your browser and navigate to:
   ```
   http://localhost:8000
   ```

---

## 🔒 AWS Security & Least-Privilege IAM Policy

When configuring an IAM User/Role for AutoResearch, attach a restricted inline policy with least-privilege permissions for DynamoDB and S3:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DynamoDBSessionAccess",
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:Scan",
        "dynamodb:DeleteItem"
      ],
      "Resource": "arn:aws:dynamodb:*:*:table/autoresearch-sessions"
    },
    {
      "Sid": "S3ReportAccess",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::autoresearch-reports/*"
    }
  ]
}
```

---

## 🐳 Docker Deployment

Run the complete stack using Docker Compose:

```bash
docker-compose up --build
```

Access the application at `http://localhost:8000`.

---

## 📡 API Endpoints & SSE Events

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/upload-document` | Upload PDF/TXT file into FAISS vector store |
| `POST` | `/api/research/stream` | Stream real-time agent reasoning steps & report chunks (SSE) |
| `GET` | `/api/sessions` | List all past research sessions from DynamoDB |
| `GET` | `/api/sessions/{session_id}` | Retrieve details of a single research session |
| `DELETE` | `/api/sessions/{session_id}` | Delete research session record & S3 report |
| `GET` | `/api/reports/{session_id}/download` | Generate pre-signed AWS S3 URL for downloading report |

---

## 📄 License
MIT License
