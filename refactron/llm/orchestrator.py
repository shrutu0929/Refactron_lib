"""Orchestrator for LLM-based refactoring suggestions."""

import json
import logging
import os
import re
import ast
from pathlib import Path
from typing import Dict, List, Optional, Union

from refactron.core.models import CodeIssue, IssueCategory, IssueLevel
from refactron.llm.backend_client import BackendLLMClient
from refactron.llm.client import GroqClient
from refactron.llm.models import RefactoringSuggestion, SuggestionStatus
from refactron.llm.prompts import (
    BATCH_SUGGESTION_PROMPT,
    BATCH_SUGGESTION_SYSTEM_PROMPT,
    BATCH_TRIAGE_PROMPT,
    BATCH_TRIAGE_SYSTEM_PROMPT,
    DOCUMENTATION_PROMPT,
    SUGGESTION_PROMPT,
    SYSTEM_PROMPT,
)
from refactron.llm.safety import SafetyGate
from refactron.rag.retriever import ContextRetriever

logger = logging.getLogger(__name__)


class LLMOrchestrator:
    """Coordinates RAG context retrieval and LLM generation."""

    def __init__(
        self,
        retriever: Optional[ContextRetriever] = None,
        workspace_path: Optional[Path] = None,
        llm_client: Optional[Union[GroqClient, BackendLLMClient]] = None,
        safety_gate: Optional[SafetyGate] = None,
    ):
        self.retriever = retriever
        self.workspace_path = workspace_path

        if llm_client:
            self.client = llm_client
        else:
            # Try to use GroqClient if API key is present,
            # otherwise use BackendLLMClient
            if os.getenv("GROQ_API_KEY"):
                try:
                    self.client = GroqClient()
                except RuntimeError:
                    self.client = BackendLLMClient()
            else:
                self.client = BackendLLMClient()

        self.safety_gate = safety_gate or SafetyGate()

        # Auto-initialize retriever if missing but workspace is provided
        if not self.retriever and self.workspace_path:
            self._ensure_retriever()

    def _ensure_retriever(self) -> None:
        """Attempt to load or build the context retriever."""
        from refactron.rag.retriever import ContextRetriever

        try:
            self.retriever = ContextRetriever(self.workspace_path)
        except RuntimeError:
            logger.info("RAG index missing. Auto-building index...")
            self.build_vector_index(self.workspace_path, summarize=False)

            # Try loading again after build
            try:
                self.retriever = ContextRetriever(self.workspace_path)
            except RuntimeError as final_e:
                logger.warning(
                    f"Context retrieval will be limited. Failed to load RAG index: {final_e}"
                )

    def build_vector_index(self, workspace_path: Path, summarize: bool = False) -> None:
        """Create or update the RAG vector index for the workspace.

        Args:
            workspace_path: Path to the workspace directory
            summarize: Whether to use AI to summarize code for better retrieval
        """
        # Lazy import to prevent circular dependency
        from refactron.rag.indexer import RAGIndexer

        try:
            indexer = RAGIndexer(workspace_path=workspace_path, llm_integration=self)
            indexer.index_repository(summarize=summarize)

            # Reload the retriever if it exists to pick up new chunks
            if self.retriever:
                # Assuming context retriever shares the same path concept
                from refactron.rag.retriever import ContextRetriever

                self.retriever = ContextRetriever(workspace_path)
                logger.info("Successfully updated LLMOrchestrator vector retrieval context.")
        except Exception as e:
            logger.error(f"Failed to build vector index: {e}")

    def generate_chunk_summary(self, chunk_content: str) -> Optional[str]:
        """Generate a semantic summary of a code chunk for RAG indexing.

        Args:
            chunk_content: The python code chunk

        Returns:
            A one-sentence description of the chunk, or None on failure.
        """
        prompt = (
            "Analyze the following Python code snippet and provide a one-sentence "
            "summary of its purpose, focusing on what it DOES (e.g. 'Calculates user permissions' "
            "or 'Handles secure database connections').\n\n"
            f"Code:\n{chunk_content}"
        )

        try:
            summary = self.client.generate(
                prompt=prompt,
                system=(
                    "You are a senior software architect. "
                    "Provide a concise, semantic summary of code purpose."
                ),
                max_tokens=100,
            )
            return summary.strip()
        except Exception as e:
            logger.warning(f"AI summarization failed: {e}")
            return None

    def generate_suggestion(self, issue: CodeIssue, original_code: str) -> RefactoringSuggestion:
        """Generate a refactoring suggestion for a code issue.

        Args:
            issue: The code issue to fix
            original_code: The failing code snippet

        Returns:
            A validated refactoring suggestion
        """
        # 1. Retrieve Context
        context_snippets = []
        if self.retriever:
            try:
                # Search for similar code or relevant context
                results = self.retriever.retrieve_similar(
                    f"{issue.message} {original_code}", top_k=3
                )
                context_snippets = [r.content for r in results]
            except Exception as e:
                logger.warning(f"Context retrieval failed: {e}")

        rag_context = "\n\n".join(context_snippets) if context_snippets else "No context available."

        # 2. Construct Prompt
        prompt = SUGGESTION_PROMPT.format(
            issue_message=issue.message,
            file_path=issue.file_path,
            line_number=issue.line_number,
            severity=issue.level.value,
            original_code=original_code,
            rag_context=rag_context,
        )

        # 3. Call LLM
        response_text = "N/A"
        try:
            response_text = self.client.generate(
                prompt=prompt, system=SYSTEM_PROMPT, temperature=0.2  # Low temperature for code
            )

            # Parse JSON response
            # Note: Groq might return markdown code blocks, strip them
            clean_text = self._clean_json_response(response_text)

            # Using strict=False allows control characters like newlines in strings
            data = json.loads(clean_text, strict=False)

            # Extract and parse confidence score
            raw_confidence = data.get("confidence_score", 0.7)
            try:
                # Handle strings with % or range strings
                if isinstance(raw_confidence, str):
                    match = re.search(r"(\d+\.?\d*)", raw_confidence)
                    confidence = (
                        float(match.group(1)) / 100.0
                        if "%" in raw_confidence
                        else float(match.group(1))
                    )
                else:
                    confidence = float(raw_confidence)
            except (ValueError, TypeError, AttributeError):
                confidence = 0.5  # Fallback

            proposed_code = data.get("proposed_code", "")

            # Aggressively clean up hallucinated markdown inside the JSON string
            if proposed_code.startswith("```"):
                lines = proposed_code.split("\n")
                if lines[0].startswith("```"):
                    lines.pop(0)
                if lines and lines[-1].startswith("```"):
                    lines.pop(-1)
                proposed_code = "\n".join(lines).strip()

            # If the LLM accidentally wrapped the code in JSON braces
            if proposed_code.startswith("{") and proposed_code.endswith("}"):
                potential_code = proposed_code[1:-1].strip()
                try:
                    # Only accept the stripped version if it's valid Python syntax
                    ast.parse(potential_code)
                    proposed_code = potential_code
                except SyntaxError:
                    pass

            suggestion = RefactoringSuggestion(
                issue=issue,
                original_code=original_code,
                context_files=[r.file_path for r in results] if self.retriever else [],
                proposed_code=proposed_code,
                explanation=data.get("explanation", "No explanation provided."),
                reasoning=data.get("reasoning", ""),
                model_name=self.client.model,
                confidence_score=min(max(confidence, 0.0), 1.0),
                llm_confidence=min(max(confidence, 0.0), 1.0),
            )

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            logger.debug(f"Raw response: {response_text}")
            # Return a failed suggestion
            return RefactoringSuggestion(
                issue=issue,
                original_code=original_code,
                context_files=[],
                proposed_code="",
                explanation=f"Generation failed: {str(e)}",
                reasoning="",
                model_name=self.client.model,
                confidence_score=0.0,
                status=SuggestionStatus.FAILED,
            )

        # 4. Safety Validation
        try:
            safety_result = self.safety_gate.validate(suggestion)
            suggestion.safety_result = safety_result

            # Link confidence score to safety result score
            suggestion.confidence_score = safety_result.score

            if not safety_result.passed:
                suggestion.status = SuggestionStatus.REJECTED
                logger.warning(f"Suggestion failed safety check: {safety_result.issues}")
            else:
                suggestion.status = SuggestionStatus.PENDING

        except Exception as e:
            logger.error(f"Safety validation failed: {e}")
            suggestion.status = SuggestionStatus.FAILED

        return suggestion

    def generate_batch_suggestion(
        self, issues: List[CodeIssue], original_code: str
    ) -> RefactoringSuggestion:
        """Generate a single refactoring suggestion that fixes a batch of issues.

        Args:
            issues: List of code issues to fix
            original_code: The original source code of the file

        Returns:
            A combined refactoring suggestion
        """
        if not issues:
            raise ValueError("No issues provided for batch suggestion")

        # 1. Retrieve Context
        context_snippets = []
        if self.retriever:
            try:
                # Use the first few issues for context retrieval
                query = " ".join([i.message for i in issues[:3]])
                results = self.retriever.retrieve_similar(query, top_k=3)
                context_snippets = [r.content for r in results]
            except Exception as e:
                logger.warning(f"Context retrieval failed: {e}")

        rag_context = "\n\n".join(context_snippets) if context_snippets else "No context available."

        # 2. Format issues for prompt
        issues_details = ""
        for idx, issue in enumerate(issues, 1):
            issues_details += (
                f"{idx}. {issue.category.value} (Line {issue.line_number}): {issue.message}\n"
            )

        # 3. Construct Prompt
        prompt = BATCH_SUGGESTION_PROMPT.format(
            issues_details=issues_details,
            original_code=original_code,
            rag_context=rag_context,
        )

        # 4. Call LLM
        response_text = "N/A"
        try:
            response_text = self.client.generate(
                prompt=prompt, system=BATCH_SUGGESTION_SYSTEM_PROMPT, temperature=0.2
            )

            # Reuse cleaning and parsing logic
            clean_text = self._clean_json_response(response_text)
            data = json.loads(clean_text, strict=False)

            proposed_code = data.get("proposed_code", "")

            # Clean up hallucinations
            if proposed_code.startswith("```"):
                lines = proposed_code.split("\n")
                if lines[0].startswith("```"):
                    lines.pop(0)
                if lines and lines[-1].startswith("```"):
                    lines.pop(-1)
                proposed_code = "\n".join(lines).strip()

            if proposed_code.startswith("{") and proposed_code.endswith("}"):
                potential_code = proposed_code[1:-1].strip()
                try:
                    ast.parse(potential_code)
                    proposed_code = potential_code
                except SyntaxError:
                    pass

            suggestion = RefactoringSuggestion(
                issue=issues[0],  # Use first issue as primary reference
                original_code=original_code,
                context_files=[r.file_path for r in results] if self.retriever else [],
                proposed_code=proposed_code,
                explanation=data.get("explanation", "Combined fix for multiple issues."),
                reasoning=data.get("reasoning", ""),
                model_name=self.client.model,
                confidence_score=float(data.get("confidence_score", 0.7)),
                llm_confidence=float(data.get("confidence_score", 0.7)),
            )

        except Exception as e:
            logger.error(f"LLM batch generation failed: {e}")
            return RefactoringSuggestion(
                issue=issues[0],
                original_code=original_code,
                context_files=[],
                proposed_code="",
                explanation=f"Batch generation failed: {str(e)}",
                reasoning="",
                model_name=self.client.model,
                confidence_score=0.0,
                status=SuggestionStatus.FAILED,
            )

        # 5. Safety Validation
        try:
            safety_result = self.safety_gate.validate(suggestion)
            suggestion.safety_result = safety_result
            suggestion.confidence_score = safety_result.score

            if not safety_result.passed:
                suggestion.status = SuggestionStatus.REJECTED
            else:
                suggestion.status = SuggestionStatus.PENDING

        except Exception as e:
            logger.error(f"Safety validation failed: {e}")
            suggestion.status = SuggestionStatus.FAILED

        return suggestion

    def generate_documentation(
        self, code: str, file_path: str = "unknown"
    ) -> RefactoringSuggestion:
        """Generate documentation for the provided code.

        Args:
            code: The code to document
            file_path: Optional file path for context

        Returns:
            A suggestion containing the documented code
        """
        # Create a synthetic issue for tracking
        issue = CodeIssue(
            category=IssueCategory.DOCUMENTATION,
            level=IssueLevel.INFO,
            message="Add documentation",
            file_path=Path(file_path),
            line_number=1,
        )

        # 1. Retrieve Context
        context_snippets = []
        if self.retriever:
            try:
                # Search for similar code or relevant context
                results = self.retriever.retrieve_similar(code[:500], top_k=2)
                context_snippets = [r.content for r in results]
            except Exception as e:
                logger.warning(f"Context retrieval failed: {e}")

        rag_context = "\n\n".join(context_snippets) if context_snippets else "No context available."

        # 2. Construct Prompt
        prompt = DOCUMENTATION_PROMPT.format(original_code=code, rag_context=rag_context)

        # 3. Call LLM
        try:
            response_text = self.client.generate(
                prompt=prompt, system=SYSTEM_PROMPT, temperature=0.2
            )

            # Parse custom delimiter format
            explanation = "Added documentation"
            proposed_code = ""
            confidence = 0.8

            if "@@@EXPLANATION@@@" in response_text:
                parts = response_text.split("@@@")
                for i, part in enumerate(parts):
                    if part == "EXPLANATION":
                        explanation = parts[i + 1].strip()
                    elif part == "CONFIDENCE":
                        try:
                            confidence = float(parts[i + 1].strip())
                        except ValueError:
                            pass
                    elif part == "MARKDOWN":
                        proposed_code = parts[i + 1].strip()

            if not proposed_code:
                raise ValueError("Could not extract markdown content from response")

            return RefactoringSuggestion(
                issue=issue,
                original_code=code,
                context_files=[],
                explanation=explanation,
                proposed_code=proposed_code,
                reasoning="Documentation update",
                confidence_score=confidence,
                llm_confidence=confidence,
                model_name=self.client.model,
                status=SuggestionStatus.PENDING,
            )

        except Exception as e:
            logger.error(f"Documentation generation failed: {e}")
            return RefactoringSuggestion(
                issue=issue,
                original_code=code,
                context_files=[],
                explanation=f"Error: {str(e)}",
                proposed_code="",
                reasoning="",
                confidence_score=0.0,
                llm_confidence=0.0,
                model_name=self.client.model,
                status=SuggestionStatus.FAILED,
            )

    def evaluate_issues_batch(self, issues: List[CodeIssue], source_code: str) -> Dict[str, float]:
        """Evaluate a batch of issues for a single file to suppress false positives.

        Args:
            issues: List of CodeIssues found in the file
            source_code: The full source code of the file

        Returns:
            Dict mapping issue IDs (using rule_id or index) to confidence scores
        """
        if not issues:
            return {}

        # 1. Retrieve Context
        context_snippets = []
        if self.retriever:
            try:
                # Search for similar code or relevant context
                results = self.retriever.retrieve_similar(source_code[:1000], top_k=3)
                context_snippets = [r.content for r in results]
            except Exception as e:
                logger.warning(f"Context retrieval failed: {e}")

        rag_context = "\n\n".join(context_snippets) if context_snippets else "No context available."

        # 2. Construct JSON for issues
        issues_data = {}
        for i, issue in enumerate(issues):
            # Determine a stable, unique issue ID
            base_id = getattr(issue, "rule_id", None) or "issue"

            # Prefer to include line number when available for better stability
            line_number = getattr(issue, "line_number", None)
            id_parts = [str(base_id)]
            if line_number is not None:
                id_parts.append(str(line_number))
            # Always include the index as a final disambiguator
            id_parts.append(str(i))
            issue_id = ":".join(id_parts)

            # Ensure uniqueness in case of unexpected collisions
            unique_id = issue_id
            suffix = 1
            while unique_id in issues_data:
                suffix += 1
                unique_id = f"{issue_id}_{suffix}"

            issues_data[unique_id] = {
                "rule_id": getattr(issue, "rule_id", None),
                "message": issue.message,
                "line": issue.line_number,
                "category": (
                    issue.category.value
                    if hasattr(issue.category, "value")
                    else str(issue.category)
                ),
                "severity": (
                    issue.level.value if hasattr(issue.level, "value") else str(issue.level)
                ),
            }

        # 3. Construct Prompt
        prompt = BATCH_TRIAGE_PROMPT.format(
            source_code=source_code,
            rag_context=rag_context,
            issues_json=json.dumps(issues_data, indent=2),
        )

        # 4. Call LLM
        try:
            response_text = self.client.generate(
                prompt=prompt, system=BATCH_TRIAGE_SYSTEM_PROMPT, temperature=0.1
            )
            clean_text = self._clean_json_response(response_text)
            data = json.loads(clean_text, strict=False)

            # Ensure we return a Dict[str, float]
            result = {}
            for k, v in data.items():
                try:
                    result[str(k)] = float(v)
                except (ValueError, TypeError):
                    result[str(k)] = 0.5  # Fallback for parsing errors
            return result

        except Exception as e:
            logger.error(f"Batch triage failed: {e}")
            # Fallback: return default confidence
            return {str(k): 0.5 for k in issues_data.keys()}

    def _clean_json_response(self, text: str) -> str:
        """Clean LLM response to extract JSON."""
        text = text.strip()

        # Remove markdown code blocks
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end != -1:
                text = text[start:end]
            else:
                text = text[start:]
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end != -1:
                text = text[start:end]
            else:
                text = text[start:]

        return text.strip()
