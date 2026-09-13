import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings

from backend.app.config import EMBEDDING_MODEL_NAME, VECTOR_STORE_DIR

# Global cache for embedding model instance to avoid re-loading on every call
_EMBEDDINGS_CACHE = None

def get_embedding_model():
    """Retrieve or initialize HuggingFace Embeddings model."""
    global _EMBEDDINGS_CACHE
    if _EMBEDDINGS_CACHE is None:
        print(f"[*] Loading HuggingFace Embedding Model ({EMBEDDING_MODEL_NAME})...")
        _EMBEDDINGS_CACHE = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL_NAME,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True}
        )
    return _EMBEDDINGS_CACHE

def process_and_index_document(file_path: str, doc_session_id: str) -> Dict[str, Any]:
    """
    Reads PDF or TXT document, splits text into chunks, indexes into FAISS vector store,
    and persists index to disk under doc_session_id directory.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Load file
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        loader = PyPDFLoader(str(file_path))
        docs = loader.load()
    else:
        loader = TextLoader(str(file_path), encoding="utf-8")
        docs = loader.load()

    if not docs:
        raise ValueError("No text content could be extracted from document.")

    # Split text
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    chunks = text_splitter.split_documents(docs)

    # Embed and index into FAISS
    embeddings = get_embedding_model()
    vectorstore = FAISS.from_documents(chunks, embeddings)

    # Save vector store to disk
    save_dir = VECTOR_STORE_DIR / doc_session_id
    save_dir.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(save_dir))

    return {
        "doc_session_id": doc_session_id,
        "filename": file_path.name,
        "total_chunks": len(chunks),
        "total_pages": len(docs)
    }

def search_documents(query: str, doc_session_id: str, k: int = 4) -> List[Dict[str, Any]]:
    """
    Performs similarity search in FAISS vector store for a given doc_session_id.
    Returns list of dicts with content and metadata (page/source).
    """
    save_dir = VECTOR_STORE_DIR / doc_session_id
    if not save_dir.exists():
        print(f"[VectorStore Warning] Index directory for {doc_session_id} does not exist.")
        return []

    try:
        embeddings = get_embedding_model()
        vectorstore = FAISS.load_local(
            str(save_dir),
            embeddings,
            allow_dangerous_deserialization=True
        )
        results = vectorstore.similarity_search(query, k=k)
        
        extracted = []
        for doc in results:
            page = doc.metadata.get("page", 0)
            source = doc.metadata.get("source", "Uploaded Document")
            extracted.append({
                "content": doc.page_content,
                "page": page + 1 if isinstance(page, int) else page,
                "source": Path(source).name
            })
        return extracted
    except Exception as e:
        print(f"[VectorStore Error] Document search failed for {doc_session_id}: {e}")
        return []
