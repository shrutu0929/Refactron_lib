"""Context retrieval from the RAG index."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# RAG dependencies are loaded lazily in __init__ to prevent CLI crashes
# if libraries like PyTorch fail to initialize (common on some Windows environments).
CHROMA_AVAILABLE = None


@dataclass
class RetrievedContext:
    """Represents a retrieved code context."""

    content: str
    file_path: str
    chunk_type: str
    name: str
    line_range: tuple
    distance: float  # Similarity distance
    metadata: dict


class ContextRetriever:
    """Retrieves relevant code context from the RAG index."""

    def __init__(
        self,
        workspace_path: Path,
        embedding_model: str = "all-MiniLM-L6-v2",
        collection_name: str = "code_chunks",
    ):
        """Initialize the context retriever.

        Args:
            workspace_path: Path to the workspace directory
            embedding_model: Name of the sentence-transformers model
            collection_name: Name of the ChromaDB collection
        """
        self.workspace_path = Path(workspace_path)
        self.index_path = self.workspace_path / ".rag"

        # Lazy load dependencies to avoid crashing the whole CLI
        # when PyTorch DLL initialization fails (WinError 1114)
        global CHROMA_AVAILABLE
        if CHROMA_AVAILABLE is None:
            try:
                import chromadb as _chromadb
                from chromadb.config import Settings as _Settings
                from sentence_transformers import SentenceTransformer as _SentenceTransformer

                globals()["chromadb"] = _chromadb
                globals()["Settings"] = _Settings
                globals()["SentenceTransformer"] = _SentenceTransformer
                CHROMA_AVAILABLE = True
            except (ImportError, OSError) as e:
                import logging

                logging.getLogger(__name__).warning(
                    f"RAG dependencies failed to load, falling back to keyword mode: {e}"
                )
                CHROMA_AVAILABLE = False

        if CHROMA_AVAILABLE:
            self.mode = "vector"
            # Initialize embedding model
            try:
                self.embedding_model = globals()["SentenceTransformer"](embedding_model)
            except Exception as e:
                import logging

                logging.getLogger(__name__).error(f"Failed to initialize embedding model: {e}")
                self.mode = "keyword"

            if self.mode == "vector":
                # Initialize ChromaDB client
                self.client = globals()["chromadb"].PersistentClient(
                    path=str(self.index_path / "chroma"),
                    settings=globals()["Settings"](anonymized_telemetry=False),
                )

                # Get collection
                try:
                    self.collection = self.client.get_collection(name=collection_name)
                except Exception:
                    # If vector collection is missing but folder exists,
                    # we might have indexed in keyword mode before
                    if (self.index_path / "keyword_chunks.json").exists():
                        self.mode = "keyword"
                    else:
                        raise RuntimeError(
                            f"Index not found at {self.index_path}. Run 'refactron rag index' first."
                        )
        else:
            self.mode = "keyword"

        # In keyword mode, we load chunks from the JSON file
        if self.mode == "keyword":
            self.keyword_chunks = []
            chunk_file = self.index_path / "keyword_chunks.json"
            if chunk_file.exists():
                import json

                try:
                    with open(chunk_file, "r", encoding="utf-8") as f:
                        self.keyword_chunks = json.load(f)
                except Exception as e:
                    import logging

                    logging.getLogger(__name__).error(f"Failed to load keyword index: {e}")
            else:
                # Only raise if we are actually trying to search
                pass

    def retrieve_similar(
        self, query: str, top_k: int = 5, chunk_type: Optional[str] = None
    ) -> List[RetrievedContext]:
        """Retrieve similar code chunks.

        Args:
            query: The search query
            top_k: Number of results to return
            chunk_type: Optional filter by chunk type (function/class/module)

        Returns:
            List of retrieved contexts sorted by relevance
        """
        if self.mode == "keyword":
            if not self.keyword_chunks:
                import logging

                logging.getLogger(__name__).warning("No keyword chunks found for retrieval.")
                return []

            # Implementation of simple keyword search
            query_terms = set(query.lower().split())
            results = []

            for chunk in self.keyword_chunks:
                # Filter by chunk type if requested
                if chunk_type and chunk["metadata"].get("chunk_type") != chunk_type:
                    continue

                content = chunk["content"]
                # Simple score: count query terms that appear in content
                content_lower = content.lower()
                score = 0
                for term in query_terms:
                    if term in content_lower:
                        score += 1

                # Normalize score
                if score > 0:
                    # Invert score to look like 'distance' (lower is better)
                    results.append((chunk, 1.0 - (score / len(query_terms))))

            # Sort by distance (relevance)
            results.sort(key=lambda x: x[1])

            # Convert to RetrievedContext
            retrieved = []
            for chunk_data, dist in results[:top_k]:
                meta = chunk_data["metadata"]
                retrieved.append(
                    RetrievedContext(
                        content=chunk_data["content"],
                        file_path=meta.get("file_path", "unknown"),
                        chunk_type=meta.get("chunk_type", "unknown"),
                        name=meta.get("name", "unknown"),
                        line_range=(meta.get("line_start", 0), meta.get("line_end", 0)),
                        distance=dist,
                        metadata=meta,
                    )
                )
            return retrieved

        # Generate query embedding
        query_embedding = self.embedding_model.encode([query], show_progress_bar=False).tolist()[0]

        # Build query filters
        where_filter = {}
        if chunk_type:
            where_filter["chunk_type"] = chunk_type

        # Search in ChromaDB
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter if where_filter else None,
        )

        # Parse results
        contexts = []
        if results and results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i]
                distance = results["distances"][0][i] if results["distances"] else 0.0

                contexts.append(
                    RetrievedContext(
                        content=doc,
                        file_path=metadata.get("file_path", ""),
                        chunk_type=metadata.get("chunk_type", ""),
                        name=metadata.get("name", ""),
                        line_range=(metadata.get("line_start", 0), metadata.get("line_end", 0)),
                        distance=distance,
                        metadata=metadata,
                    )
                )

        return contexts

    def retrieve_by_file(self, file_path: str) -> List[RetrievedContext]:
        """Retrieve all chunks from a specific file.

        Args:
            file_path: Path to the file

        Returns:
            List of all chunks from the file
        """
        # Query by file path metadata
        results = self.collection.get(where={"file_path": file_path})

        # Parse results
        contexts = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"]):
                metadata = results["metadatas"][i]

                contexts.append(
                    RetrievedContext(
                        content=doc,
                        file_path=metadata.get("file_path", ""),
                        chunk_type=metadata.get("chunk_type", ""),
                        name=metadata.get("name", ""),
                        line_range=(metadata.get("line_start", 0), metadata.get("line_end", 0)),
                        distance=0.0,  # Not applicable for exact match
                        metadata=metadata,
                    )
                )

        return contexts

    def retrieve_functions(self, query: str, top_k: int = 5) -> List[RetrievedContext]:
        """Retrieve similar functions.

        Args:
            query: The search query
            top_k: Number of results to return

        Returns:
            List of similar function chunks
        """
        return self.retrieve_similar(query, top_k=top_k, chunk_type="function")

    def retrieve_classes(self, query: str, top_k: int = 5) -> List[RetrievedContext]:
        """Retrieve similar classes.

        Args:
            query: The search query
            top_k: Number of results to return

        Returns:
            List of similar class chunks
        """
        return self.retrieve_similar(query, top_k=top_k, chunk_type="class")
