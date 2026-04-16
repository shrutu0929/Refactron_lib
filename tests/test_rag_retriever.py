"""Tests for the RAG retriever module."""

from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from refactron.rag.retriever import ContextRetriever, RetrievedContext


# ── helper: build a fully-mocked ContextRetriever ────────────────────────────


def make_retriever(workspace_path: Path) -> ContextRetriever:
    """Return a ContextRetriever with all heavy deps mocked via globals injection."""
    import refactron.rag.retriever as _mod

    mock_model = Mock()
    mock_model.encode.return_value.tolist.return_value = [[0.1, 0.2]]

    mock_collection = Mock()
    mock_chroma_client = Mock()
    mock_chroma_client.get_collection.return_value = mock_collection
    mock_chromadb = MagicMock()
    mock_chromadb.PersistentClient.return_value = mock_chroma_client

    _mod.CHROMA_AVAILABLE = True
    _mod.__dict__["SentenceTransformer"] = MagicMock(return_value=mock_model)
    _mod.__dict__["chromadb"] = mock_chromadb
    _mod.__dict__["Settings"] = MagicMock()

    try:
        r = ContextRetriever(workspace_path)
        r._mock_collection = mock_collection
        r._mock_model = mock_model
        return r
    finally:
        _mod.CHROMA_AVAILABLE = None
        _mod.__dict__.pop("SentenceTransformer", None)
        _mod.__dict__.pop("chromadb", None)
        _mod.__dict__.pop("Settings", None)


# ── tests ─────────────────────────────────────────────────────────────────────


class TestContextRetriever:
    """Test cases for ContextRetriever."""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        """Create a temporary workspace directory."""
        (tmp_path / ".rag").mkdir()
        return tmp_path

    def test_retriever_initialization(self, temp_workspace):
        """Test retriever initialization."""
        retriever = make_retriever(temp_workspace)
        assert retriever.workspace_path == temp_workspace
        assert retriever.index_path == temp_workspace / ".rag"

    def test_retriever_requires_chromadb(self, temp_workspace):
        """When ChromaDB is unavailable the retriever falls back to keyword mode."""
        import refactron.rag.retriever as _mod

        _mod.CHROMA_AVAILABLE = False
        try:
            retriever = ContextRetriever(temp_workspace)
            assert retriever.mode == "keyword"
        finally:
            _mod.CHROMA_AVAILABLE = None

    def test_retriever_missing_index(self, temp_workspace):
        """Test that a missing collection (no keyword fallback file) raises RuntimeError."""
        import refactron.rag.retriever as _mod

        mock_model = Mock()
        mock_chroma_client = Mock()
        mock_chroma_client.get_collection.side_effect = Exception("Collection not found")
        mock_chromadb = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_chroma_client

        _mod.CHROMA_AVAILABLE = True
        _mod.__dict__["SentenceTransformer"] = MagicMock(return_value=mock_model)
        _mod.__dict__["chromadb"] = mock_chromadb
        _mod.__dict__["Settings"] = MagicMock()
        try:
            # No keyword_chunks.json present → should raise RuntimeError("Index not found")
            with pytest.raises(RuntimeError, match="Index not found"):
                ContextRetriever(temp_workspace)
        finally:
            _mod.CHROMA_AVAILABLE = None
            _mod.__dict__.pop("SentenceTransformer", None)
            _mod.__dict__.pop("chromadb", None)
            _mod.__dict__.pop("Settings", None)

    def test_retrieve_similar(self, temp_workspace):
        """Test retrieving similar code chunks."""
        retriever = make_retriever(temp_workspace)
        retriever._mock_collection.query.return_value = {
            "documents": [["def test(): pass"]],
            "metadatas": [
                [
                    {
                        "file_path": "/test.py",
                        "chunk_type": "function",
                        "name": "test",
                        "line_start": 1,
                        "line_end": 1,
                    }
                ]
            ],
            "distances": [[0.15]],
        }
        results = retriever.retrieve_similar("test function", top_k=1)

        assert len(results) == 1
        assert isinstance(results[0], RetrievedContext)
        assert results[0].name == "test"
        assert results[0].chunk_type == "function"

    def test_retrieve_by_file(self, temp_workspace):
        """Test retrieving chunks by file path."""
        retriever = make_retriever(temp_workspace)
        retriever._mock_collection.get.return_value = {
            "documents": ["def test(): pass"],
            "metadatas": [
                {
                    "file_path": "/test.py",
                    "chunk_type": "function",
                    "name": "test",
                    "line_start": 1,
                    "line_end": 1,
                }
            ],
        }
        results = retriever.retrieve_by_file("/test.py")

        assert len(results) == 1
        assert results[0].file_path == "/test.py"

    def test_retrieve_functions(self, temp_workspace):
        """Test retrieving only function chunks."""
        retriever = make_retriever(temp_workspace)
        retriever._mock_collection.query.return_value = {
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        retriever.retrieve_functions("test", top_k=5)

        # Verify that chunk_type filter was used
        call_args = retriever._mock_collection.query.call_args
        assert call_args.kwargs.get("where") == {"chunk_type": "function"}

    def test_retrieve_no_results(self, temp_workspace):
        """Test retrieval with no results."""
        retriever = make_retriever(temp_workspace)
        retriever._mock_collection.query.return_value = {
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        results = retriever.retrieve_similar("nonexistent", top_k=5)

        assert len(results) == 0
