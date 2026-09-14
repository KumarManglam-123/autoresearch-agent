import os
import gc
from pathlib import Path
from typing import List, Dict, Any, Optional

# Set CPU single-thread environment variables BEFORE any heavy AI/ML libraries are loaded
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from backend.app.config import EMBEDDING_MODEL_NAME, VECTOR_STORE_DIR

# Global cache for embedding model instance to avoid re-loading on every call
_EMBEDDINGS_CACHE = None

def get_embedding_model():
    """
    Lazy-loads HuggingFace Embeddings model ONLY when document search is explicitly requested.
    Caches model in memory and configures PyTorch for single-threaded CPU execution.
    """
    global _EMBEDDINGS_CACHE
    if _EMBEDDINGS_CACHE is None:
        print(f"[*] Lazy-loading HuggingFace Embedding Model ({EMBEDDING_MODEL_NAME})...")
        try:
            import torch
            torch.set_num_threads(1)
        except ImportError:
            pass

        from langchain_community.embeddings import HuggingFaceEmbeddings

        _EMBEDDINGS_CACHE = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL_NAME,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True}
        )
        gc.collect()
    return _EMBEDDINGS_CACHE

def process_and_index_document(file_path: str, doc_session_id: str) -> Dict[str, Any]:
    """
    Reads PDF or TXT document, splits text into chunks, indexes into FAISS vector store,
    and persists index to disk under doc_session_id directory.
    Lazy-imports document loaders and FAISS to minimize startup memory overhead.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    from langchain_community.document_loaders import PyPDFLoader, TextLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import FAISS

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

    # Free transient chunk objects
    del docs
    del chunks
    gc.collect()

    return {
        "doc_session_id": doc_session_id,
        "filename": file_path.name,
        "total_chunks": len(chunks) if 'chunks' in locals() else 0,
        "total_pages": len(docs) if 'docs' in locals() else 0
    }

def search_documents(query: str, doc_session_id: str, k: int = 4) -> List[Dict[str, Any]]:
    """
    Performs similarity search in FAISS vector store for a given doc_session_id.
    Lazy-imports FAISS to avoid loading vector store modules unless requested.
    """
    save_dir = VECTOR_STORE_DIR / doc_session_id
    if not save_dir.exists():
        print(f"[VectorStore Warning] Index directory for {doc_session_id} does not exist.")
        return []

    try:
        from langchain_community.vectorstores import FAISS
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

        del results
        gc.collect()
        return extracted
    except Exception as e:
        print(f"[VectorStore Error] Document search failed for {doc_session_id}: {e}")
        return []
