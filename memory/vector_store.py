from __future__ import annotations
import os
import chromadb
from chromadb.config import Settings


class VectorStore:
    """
    Stores chapter embeddings so the writer can retrieve semantically
    relevant past chapters as context (avoids passing all 100+ chapters).
    Uses ChromaDB's built-in embedding (all-MiniLM-L6-v2 by default).
    """

    def __init__(self):
        persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name="chapters",
            metadata={"hnsw:space": "cosine"},
        )

    def add_chapter(self, chapter_number: int, title: str, content: str, arc: int):
        doc_id = f"chapter_{chapter_number:03d}"
        self._collection.upsert(
            ids=[doc_id],
            documents=[content],
            metadatas=[{"chapter": chapter_number, "title": title, "arc": arc}],
        )

    def query_relevant(self, query: str, top_k: int = 5, exclude_chapter: int = -1) -> list[dict]:
        """Return top_k most semantically similar past chapters."""
        if self._collection.count() == 0:
            return []
        results = self._collection.query(
            query_texts=[query],
            n_results=min(top_k, self._collection.count()),
        )
        output = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            if meta["chapter"] == exclude_chapter:
                continue
            output.append({"chapter": meta["chapter"], "title": meta["title"], "content": doc})
        return output

    def count(self) -> int:
        return self._collection.count()
