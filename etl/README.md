# ETL Pipeline for pgvector

This directory contains ETL scripts for loading documents into PostgreSQL with pgvector.

## Overview

The ETL pipeline:
1. **Extracts** documents from a source directory
2. **Transforms** text into vector embeddings using sentence transformers
3. **Loads** documents and embeddings into PostgreSQL pgvector

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Environment Variables

```bash
export POSTGRES_HOST=postgresql-pgvector
export POSTGRES_PORT=5432
export POSTGRES_DB=vectordb
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=your-password
export DOCUMENTS_PATH=./documents
export EMBEDDING_MODEL=all-MiniLM-L6-v2
```

### Run ETL Pipeline

```bash
python etl_load_pgvector.py
```

### In OpenShift

Create a Job to run the ETL:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: pgvector-etl-job
spec:
  template:
    spec:
      containers:
      - name: etl
        image: python:3.11-slim
        command: ["python", "/app/etl_load_pgvector.py"]
        env:
        - name: POSTGRES_HOST
          value: "postgresql-pgvector"
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgresql-secret
              key: password
        volumeMounts:
        - name: etl-scripts
          mountPath: /app
        - name: documents
          mountPath: /documents
      volumes:
      - name: etl-scripts
        configMap:
          name: etl-scripts
      - name: documents
        persistentVolumeClaim:
          claimName: documents-pvc
      restartPolicy: OnFailure
```

## Features

- ✅ Automatic pgvector extension setup
- ✅ Vector similarity search index creation
- ✅ Batch processing of documents
- ✅ Metadata storage (JSON)
- ✅ Error handling and logging
- ✅ Support for multiple document formats

## Supported Models

- `all-MiniLM-L6-v2` (default, 384 dimensions)
- `all-mpnet-base-v2` (768 dimensions)
- Any HuggingFace sentence-transformer model

## Database Schema

```sql
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    metadata JSONB,
    embedding vector(384),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Query Examples

### Similarity Search

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')
query = "What is machine learning?"
query_embedding = model.encode(query).tolist()

# Find similar documents
cur.execute("""
    SELECT content, metadata, 
           1 - (embedding <=> %s::vector) as similarity
    FROM documents
    ORDER BY embedding <=> %s::vector
    LIMIT 5
""", (query_embedding, query_embedding))
```
