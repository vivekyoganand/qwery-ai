#!/usr/bin/env python3
"""
ETL Script to Load Documents into PostgreSQL pgvector
Extracts text from documents, generates embeddings, and loads into pgvector
"""

import os
import sys
import psycopg2
from psycopg2.extras import execute_values
import numpy as np
from sentence_transformers import SentenceTransformer
import logging
from pathlib import Path
import json
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PgVectorETL:
    """ETL pipeline for loading documents into PostgreSQL with pgvector"""

    def __init__(self, db_config):
        """
        Initialize ETL pipeline

        Args:
            db_config (dict): Database configuration
                - host: PostgreSQL host
                - port: PostgreSQL port
                - database: Database name
                - user: Database user
                - password: Database password
        """
        self.db_config = db_config
        self.conn = None
        self.model = None
        self.embedding_dim = 384  # Default for all-MiniLM-L6-v2

    def connect_db(self):
        """Establish database connection"""
        try:
            self.conn = psycopg2.connect(**self.db_config)
            logger.info("✅ Connected to PostgreSQL database")
            return True
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            return False

    def initialize_pgvector(self):
        """Initialize pgvector extension and create tables"""
        try:
            with self.conn.cursor() as cur:
                # Enable pgvector extension
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

                # Create documents table with vector column
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS documents (
                        id SERIAL PRIMARY KEY,
                        content TEXT NOT NULL,
                        metadata JSONB,
                        embedding vector({self.embedding_dim}),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)

                # Create index for vector similarity search
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS documents_embedding_idx 
                    ON documents USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100);
                """)

                self.conn.commit()
                logger.info("✅ pgvector initialized and tables created")
                return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize pgvector: {e}")
            self.conn.rollback()
            return False

    def load_embedding_model(self, model_name='all-MiniLM-L6-v2'):
        """
        Load sentence transformer model for embeddings

        Args:
            model_name (str): HuggingFace model name
        """
        try:
            logger.info(f"Loading embedding model: {model_name}")
            self.model = SentenceTransformer(model_name)
            self.embedding_dim = self.model.get_sentence_embedding_dimension()
            logger.info(f"✅ Model loaded. Embedding dimension: {self.embedding_dim}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to load model: {e}")
            return False

    def extract_documents(self, source_path):
        """
        Extract documents from source directory

        Args:
            source_path (str): Path to documents directory

        Returns:
            list: List of document dictionaries
        """
        documents = []
        source = Path(source_path)

        if not source.exists():
            logger.error(f"❌ Source path does not exist: {source_path}")
            return documents

        # Support for text files
        for file_path in source.rglob('*.txt'):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                documents.append({
                    'content': content,
                    'metadata': {
                        'filename': file_path.name,
                        'filepath': str(file_path),
                        'file_type': 'txt',
                        'size': file_path.stat().st_size
                    }
                })
                logger.info(f"✅ Extracted: {file_path.name}")
            except Exception as e:
                logger.error(f"❌ Failed to extract {file_path}: {e}")

        logger.info(f"✅ Total documents extracted: {len(documents)}")
        return documents

    def generate_embeddings(self, documents):
        """
        Generate embeddings for documents

        Args:
            documents (list): List of document dictionaries

        Returns:
            list: Documents with embeddings added
        """
        if not self.model:
            logger.error("❌ Model not loaded. Call load_embedding_model() first")
            return documents

        logger.info(f"Generating embeddings for {len(documents)} documents...")

        for i, doc in enumerate(documents):
            try:
                # Generate embedding
                embedding = self.model.encode(doc['content'])
                doc['embedding'] = embedding.tolist()

                if (i + 1) % 10 == 0:
                    logger.info(f"  Progress: {i + 1}/{len(documents)} documents")
            except Exception as e:
                logger.error(f"❌ Failed to generate embedding for document {i}: {e}")
                doc['embedding'] = None

        logger.info("✅ Embeddings generated")
        return documents

    def load_to_pgvector(self, documents):
        """
        Load documents with embeddings into PostgreSQL

        Args:
            documents (list): List of documents with embeddings

        Returns:
            int: Number of documents loaded
        """
        loaded_count = 0

        try:
            with self.conn.cursor() as cur:
                for doc in documents:
                    if doc.get('embedding') is None:
                        continue

                    cur.execute("""
                        INSERT INTO documents (content, metadata, embedding)
                        VALUES (%s, %s, %s)
                    """, (
                        doc['content'],
                        json.dumps(doc['metadata']),
                        doc['embedding']
                    ))
                    loaded_count += 1

                self.conn.commit()
                logger.info(f"✅ Loaded {loaded_count} documents into pgvector")
        except Exception as e:
            logger.error(f"❌ Failed to load documents: {e}")
            self.conn.rollback()

        return loaded_count

    def run_etl(self, source_path, model_name='all-MiniLM-L6-v2'):
        """
        Run complete ETL pipeline

        Args:
            source_path (str): Path to documents directory
            model_name (str): Embedding model name

        Returns:
            bool: Success status
        """
        logger.info("=" * 80)
        logger.info("🚀 Starting ETL Pipeline")
        logger.info("=" * 80)

        # Step 1: Connect to database
        if not self.connect_db():
            return False

        # Step 2: Initialize pgvector
        if not self.initialize_pgvector():
            return False

        # Step 3: Load embedding model
        if not self.load_embedding_model(model_name):
            return False

        # Step 4: Extract documents
        documents = self.extract_documents(source_path)
        if not documents:
            logger.warning("⚠️  No documents found to process")
            return False

        # Step 5: Generate embeddings
        documents = self.generate_embeddings(documents)

        # Step 6: Load to pgvector
        loaded_count = self.load_to_pgvector(documents)

        logger.info("=" * 80)
        logger.info(f"✅ ETL Pipeline Complete! Loaded {loaded_count} documents")
        logger.info("=" * 80)

        return True

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")


def main():
    """Main execution function"""

    # Database configuration from environment variables
    db_config = {
        'host': os.getenv('POSTGRES_HOST', 'postgresql-pgvector'),
        'port': int(os.getenv('POSTGRES_PORT', 5432)),
        'database': os.getenv('POSTGRES_DB', 'vectordb'),
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', 'postgres')
    }

    # Source documents path
    source_path = os.getenv('DOCUMENTS_PATH', './documents')

    # Embedding model
    model_name = os.getenv('EMBEDDING_MODEL', 'all-MiniLM-L6-v2')

    # Initialize and run ETL
    etl = PgVectorETL(db_config)

    try:
        success = etl.run_etl(source_path, model_name)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"❌ ETL pipeline failed: {e}")
        sys.exit(1)
    finally:
        etl.close()


if __name__ == "__main__":
    main()
