"""Pattern matching for finding similar code patterns."""

import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from refactron.patterns.models import ProjectPatternProfile, RefactoringPattern
from refactron.patterns.storage import PatternStorage

logger = logging.getLogger(__name__)


class PatternMatcher:
    """Matches code patterns against learned patterns with scoring."""

    def __init__(self, storage: PatternStorage, cache_ttl_seconds: int = 300):
        """
        Initialize pattern matcher.

        Args:
            storage: PatternStorage instance for loading patterns
            cache_ttl_seconds: Cache time-to-live in seconds (default: 300 seconds / 5 minutes)
        """
        self.storage = storage
        self._patterns_cache: Optional[Dict[str, RefactoringPattern]] = None
        self._hash_index: Optional[Dict[str, List[RefactoringPattern]]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._similarity_threshold = 0.8  # Default similarity threshold for fuzzy matching
        self._cache_ttl_seconds = cache_ttl_seconds  # Cache TTL

    def find_similar_patterns(
        self,
        code_hash: str,
        operation_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[RefactoringPattern]:
        """
        Find patterns similar to given code hash.

        Optimized with O(1) hash-based lookup instead of O(n) linear search.

        Args:
            code_hash: Hash of the code pattern to match
            operation_type: Optional operation type to filter by
            limit: Optional maximum number of results to return

        Returns:
            List of similar patterns, sorted by acceptance rate
        """
        # Validate hash format (SHA256 produces 64 char hex, but allow shorter
        # for testing/backwards compatibility)
        if not code_hash:
            logger.warning("Empty code_hash provided")
            return []

        # Warn if hash doesn't look like SHA256 (but still allow it for
        # backward compatibility)
        if len(code_hash) != 64:
            logger.debug(
                f"Non-standard hash length ({len(code_hash)} chars, "
                f"expected 64): {code_hash[:16]}..."
            )

        # Load patterns and index
        hash_index = self._load_hash_index()

        # Optimize: O(1) lookup instead of O(n) linear search
        exact_matches = hash_index.get(code_hash, [])

        # Filter by operation_type if specified
        if operation_type and exact_matches:
            exact_matches = [p for p in exact_matches if p.operation_type == operation_type]

        if exact_matches:
            # Sort by acceptance rate (highest first)
            exact_matches.sort(key=lambda p: p.acceptance_rate, reverse=True)
            return exact_matches[:limit] if limit else exact_matches

        # If no exact match, look for fuzzy matches
        # For now, we'll use exact hash matching. Fuzzy matching can be added later
        # with more sophisticated algorithms (e.g., edit distance, structural similarity)

        logger.debug(f"No exact pattern match found for hash: {code_hash[:8]}...")
        return []

    def calculate_pattern_score(
        self,
        pattern: RefactoringPattern,
        project_profile: Optional[ProjectPatternProfile] = None,
    ) -> float:
        """
        Calculate score for pattern suggestion.

        The scoring algorithm applies multiple bonuses multiplicatively:
        - Project weight: 0.0-1.0 (disabled patterns get 0.0)
        - Enabled pattern bonus: 1.2x (20% bonus)
        - Recency bonus: up to 1.2x (20% bonus for patterns seen in last 30 days)
        - Frequency bonus: up to 1.3x (30% bonus based on log scale of occurrences)
        - Benefit bonus: up to 1.15x (15% bonus based on average_benefit_score)

        These bonuses can compound to exceed 1.0, but the final score is normalized
        to the range [0.0, 1.0] using min/max clipping.

        Args:
            pattern: Pattern to score
            project_profile: Optional project-specific profile for weighting

        Returns:
            Score between 0.0 and 1.0 (higher = better suggestion)
        """
        # Base score from acceptance rate (0.0 to 1.0)
        base_score = pattern.acceptance_rate

        # Apply project-specific weights if available
        if project_profile:
            weight = project_profile.get_pattern_weight(pattern.pattern_id, default=1.0)
            base_score *= weight

            # Check if pattern is disabled for this project
            if pattern.pattern_id in project_profile.disabled_patterns:
                return 0.0  # Disabled patterns get zero score

            # Check if pattern is explicitly enabled (bonus)
            if pattern.pattern_id in project_profile.enabled_patterns:
                base_score *= 1.2  # 20% bonus for explicitly enabled patterns

        # Adjust for recency (recent patterns weighted higher)
        # Patterns seen in last 30 days get a recency bonus
        now = datetime.now(timezone.utc)
        days_since_seen = (now - pattern.last_seen).days

        if days_since_seen <= 30:
            recency_factor = 1.0 + (0.2 * (1 - days_since_seen / 30))  # Up to 20% bonus
            base_score *= recency_factor

        # Apply frequency bonus (more occurrences = more reliable)
        # Use log scale to avoid over-weighting very frequent patterns
        frequency_bonus = 1.0 + (0.1 * math.log10(max(1, pattern.total_occurrences)))
        base_score *= min(frequency_bonus, 1.3)  # Cap at 30% bonus

        # Apply average benefit score bonus
        if pattern.average_benefit_score > 0:
            benefit_factor = 1.0 + (0.15 * min(pattern.average_benefit_score / 10.0, 1.0))
            base_score *= benefit_factor

        # Normalize to 0.0-1.0 range
        return min(1.0, max(0.0, base_score))

    def find_best_matches(
        self,
        code_hash: str,
        operation_type: Optional[str] = None,
        project_profile: Optional[ProjectPatternProfile] = None,
        limit: int = 10,
    ) -> List[Tuple[RefactoringPattern, float]]:
        """
        Find best matching patterns with scores.

        Args:
            code_hash: Hash of the code pattern to match
            operation_type: Optional operation type to filter by
            project_profile: Optional project-specific profile for weighting
            limit: Maximum number of results to return

        Returns:
            List of tuples (pattern, score) sorted by score (highest first)
        """
        patterns = self.find_similar_patterns(code_hash, operation_type)

        # Calculate scores for each pattern
        scored_patterns = [
            (pattern, self.calculate_pattern_score(pattern, project_profile))
            for pattern in patterns
        ]

        # Sort by score (highest first)
        scored_patterns.sort(key=lambda x: x[1], reverse=True)

        # Filter out zero-score patterns
        scored_patterns = [(p, s) for p, s in scored_patterns if s > 0.0]

        return scored_patterns[:limit]

    def _load_patterns(self) -> Dict[str, RefactoringPattern]:
        """
        Load patterns from storage (with caching).

        Returns:
            Dictionary mapping pattern_id to RefactoringPattern
        """
        now = datetime.now(timezone.utc)
        if self._patterns_cache is None or self._cache_timestamp is None:
            self._patterns_cache = self.storage.load_patterns()
            self._cache_timestamp = now
            return self._patterns_cache

        # Optimize: Use timedelta for proper time comparison (handles > 1 day)
        time_diff = now - self._cache_timestamp
        if time_diff.total_seconds() > self._cache_ttl_seconds:
            self._patterns_cache = self.storage.load_patterns()
            self._cache_timestamp = now

        return self._patterns_cache

    def _load_hash_index(self) -> Dict[str, List[RefactoringPattern]]:
        """
        Load hash-based index for O(1) pattern lookups.

        Returns:
            Dictionary mapping pattern_hash to list of patterns with that hash
        """
        # Check if we need to rebuild before loading patterns (to detect cache reload)
        need_rebuild = (
            self._hash_index is None
            or self._cache_timestamp is None
            or (datetime.now(timezone.utc) - self._cache_timestamp).total_seconds()
            >= self._cache_ttl_seconds
        )

        # Load patterns (may update cache if stale)
        patterns = self._load_patterns()

        # Rebuild index if needed
        if need_rebuild:
            self._hash_index = {}
            for pattern in patterns.values():
                if pattern.pattern_hash not in self._hash_index:
                    self._hash_index[pattern.pattern_hash] = []
                self._hash_index[pattern.pattern_hash].append(pattern)

        return self._hash_index

    def clear_cache(self) -> None:
        """Clear the pattern cache (force reload on next access)."""
        self._patterns_cache = None
        self._hash_index = None
        self._cache_timestamp = None
