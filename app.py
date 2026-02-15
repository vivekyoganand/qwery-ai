# app.py - Qwery AI RAG Service
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
import requests
import os
from typing import List, Optional
import logging

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Qwery AI RAG Service",
    description="Vector similarity search and RAG service",
    version="1.0.0"
)

# Database configuration
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "postgresql-pgvector"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "database": os.getenv("POSTGRES_DB", "vectordb"),
    "user": os.getenv("POSTGRES_USER", "qweryai"),
    "password": os.getenv("POSTGRES_PASSWORD")
}

# Embedding configuration
EMBEDDING_MODEL_URL = os.getenv("EMBEDDING_MODEL_URL", "http://ollama:11434")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "llama2")

class Document(BaseModel):
    content: str
    metadata: Optional[dict] = {}

class SearchQuery(BaseModel):
    query: str
    limit: int = 5
    threshold: float = 0.7

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(**DB_CONFIG)

def generate_embedding(text: str) -> List[float]:
    """Generate embedding using Ollama"""
    try:
        response = requests.post(
            f"{EMBEDDING_MODEL_URL}/api/embeddings",
            json={"model": EMBEDDING_MODEL_NAME, "prompt": text},
            timeout=30
        )
        response.raise_for_status()
        return response.json()["embedding"]
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        raise HTTPException(status_code=500, detail=f"Embedding generation failed: {str(e)}")

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "qwery-ai"}

@app.get("/ready")
def readiness_check():
    """Readiness check endpoint"""
    try:
        conn = get_db_connection()
        conn.close()
        return {"status": "ready"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/api/documents")
def add_document(doc: Document):
    """Add a document with vector embedding"""
    try:
        logger.info(f"Adding document: {doc.content[:50]}...")
        embedding = generate_embedding(doc.content)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO documents (content, embedding, metadata) VALUES (%s, %s, %s) RETURNING id",
            (doc.content, embedding, doc.metadata)
        )
        doc_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        logger.info(f"Document added with ID: {doc_id}")
        return {"id": doc_id, "status": "success"}
    except Exception as e:
        logger.error(f"Error adding document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search")
def search_documents(query: SearchQuery):
    """Search documents using vector similarity"""
    try:
        logger.info(f"Searching for: {query.query}")
        query_embedding = generate_embedding(query.query)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, content, metadata, 
                   1 - (embedding <=> %s) as similarity
            FROM documents
            WHERE 1 - (embedding <=> %s) > %s
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (query_embedding, query_embedding, query.threshold, query_embedding, query.limit)
        )
        results = cur.fetchall()
        cur.close()
        conn.close()

        logger.info(f"Found {len(results)} results")
        return {
            "results": [
                {
                    "id": r[0],
                    "content": r[1],
                    "metadata": r[2],
                    "similarity": float(r[3])
                }
                for r in results
            ]
        }
    except Exception as e:
        logger.error(f"Error searching documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/documents")
def list_documents(limit: int = 10, offset: int = 0):
    """List all documents"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, content, metadata, created_at FROM documents ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (limit, offset)
        )
        results = cur.fetchall()
        cur.close()
        conn.close()

        return {
            "documents": [
                {
                    "id": r[0],
                    "content": r[1],
                    "metadata": r[2],
                    "created_at": r[3].isoformat() if r[3] else None
                }
                for r in results
            ]
        }
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
