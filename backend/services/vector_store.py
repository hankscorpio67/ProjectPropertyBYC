"""
ChromaDB-based vector store for document chunk retrieval.
Falls back to simple keyword search if ChromaDB is unavailable.
"""
import os
from typing import List, Dict, Optional
from ..config import config


class VectorStore:
    def __init__(self):
        self._client = None
        self._collections: Dict[str, object] = {}
        self._init_chroma()

    def _init_chroma(self):
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=config.chroma_dir)
        except Exception as e:
            print(f"[vector store] ChromaDB unavailable ({e}), falling back to keyword search")
            self._client = None

    def _get_collection(self, project_id: str):
        if self._client is None:
            return None
        collection_name = f"project_{project_id.replace('-', '_')}"
        if collection_name not in self._collections:
            self._collections[collection_name] = self._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[collection_name]

    def add(self, project_id: str, texts: List[str], ids: List[str], metadatas: List[Dict]):
        """Add document chunks to the vector store."""
        collection = self._get_collection(project_id)
        if collection is None:
            self._fallback_store(project_id, texts, ids, metadatas)
            return
        # ChromaDB handles batching internally, but we batch for safety
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            collection.add(
                documents=texts[i:i+batch_size],
                ids=ids[i:i+batch_size],
                metadatas=metadatas[i:i+batch_size],
            )

    def query(self, project_id: str, query_text: str, n_results: int = 6) -> List[Dict]:
        """Return top-k relevant chunks for a query."""
        collection = self._get_collection(project_id)
        if collection is None:
            return self._fallback_query(project_id, query_text, n_results)
        try:
            count = collection.count()
            if count == 0:
                return []
            results = collection.query(
                query_texts=[query_text],
                n_results=min(n_results, count),
                include=["documents", "metadatas", "distances"],
            )
            chunks = []
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            dists = results["distances"][0]
            for text, meta, dist in zip(docs, metas, dists):
                chunks.append({
                    "text": text,
                    "metadata": meta,
                    "relevance": round(1 - dist, 3),
                })
            return chunks
        except Exception as e:
            print(f"[vector store] query error: {e}")
            return []

    def delete_by_doc(self, project_id: str, doc_id: str):
        """Delete all chunks belonging to a document."""
        collection = self._get_collection(project_id)
        if collection is None:
            return
        try:
            collection.delete(where={"doc_id": doc_id})
        except Exception as e:
            print(f"[vector store] delete error: {e}")

    # --- Keyword fallback ---

    def _fallback_store(self, project_id: str, texts: List[str], ids: List[str], metadatas: List[Dict]):
        """Store chunks as JSON files for keyword search fallback."""
        import json
        store_path = os.path.join(config.DATA_DIR, "keyword_store", project_id)
        os.makedirs(store_path, exist_ok=True)
        for text, chunk_id, meta in zip(texts, ids, metadatas):
            chunk_file = os.path.join(store_path, f"{chunk_id}.json")
            with open(chunk_file, "w") as f:
                json.dump({"id": chunk_id, "text": text, "metadata": meta}, f)

    def _fallback_query(self, project_id: str, query_text: str, n_results: int) -> List[Dict]:
        """Simple keyword search over stored JSON files."""
        import json
        store_path = os.path.join(config.DATA_DIR, "keyword_store", project_id)
        if not os.path.exists(store_path):
            return []
        query_words = set(query_text.lower().split())
        scored = []
        for fname in os.listdir(store_path):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(store_path, fname)) as f:
                chunk = json.load(f)
            text_lower = chunk["text"].lower()
            score = sum(1 for w in query_words if w in text_lower)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"text": c["text"], "metadata": c["metadata"], "relevance": s / len(query_words)}
            for s, c in scored[:n_results]
        ]
