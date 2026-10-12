"""
prompt_cache.py - Prompt Context Cache for AutoDev (v3.6.1)

Caches rendered engineering prompts to reduce synthesis latency.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

from core.cache_manager import CacheManager

logger = logging.getLogger("AutoDev.PromptCache")

class PromptCache:
    """
    Caches rendered prompts based on task, memory, and context state.
    """

    VERSION = "1.0.0"

    def __init__(self, cache_manager: Optional[CacheManager] = None) -> None:
        self.cache_manager = cache_manager or CacheManager()
        self.cache_path = self.cache_manager.register_cache("prompt_cache", self.VERSION)

    def _compute_key(
        self,
        task_id: str,
        memory_version: str,
        context_data: Dict[str, Any],
        code_hashes: Dict[str, str],
        impact_hash: str
    ) -> str:
        """Computes a unique cache key based on all inputs."""
        # Normalize context data for hashing
        ctx_str = json.dumps(context_data, sort_keys=True)
        code_str = json.dumps(code_hashes, sort_keys=True)
        
        raw_key = f"{task_id}:{memory_version}:{ctx_str}:{code_str}:{impact_hash}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get_prompt(
        self,
        task_id: str,
        memory_version: str,
        context_data: Dict[str, Any],
        code_hashes: Dict[str, str],
        impact_hash: str
    ) -> Optional[str]:
        """Retrieves a cached prompt if it exists and is valid."""
        key = self._compute_key(task_id, memory_version, context_data, code_hashes, impact_hash)
        cache_file = self.cache_path / f"{key}.txt"
        
        if cache_file.exists():
            try:
                prompt = cache_file.read_text(encoding="utf-8")
                self.cache_manager.update_stats("prompt_cache", hit=True)
                return prompt
            except Exception as e:
                logger.warning(f"Failed to read cached prompt: {e}")
        
        self.cache_manager.update_stats("prompt_cache", miss=True)
        return None

    def set_prompt(
        self,
        task_id: str,
        memory_version: str,
        context_data: Dict[str, Any],
        code_hashes: Dict[str, str],
        impact_hash: str,
        prompt: str
    ) -> None:
        """Caches a rendered prompt."""
        key = self._compute_key(task_id, memory_version, context_data, code_hashes, impact_hash)
        cache_file = self.cache_path / f"{key}.txt"
        
        try:
            cache_file.write_text(prompt, encoding="utf-8")
            
            # Update stats
            size = sum(f.stat().st_size for f in self.cache_path.glob("*.txt"))
            count = len(list(self.cache_path.glob("*.txt")))
            self.cache_manager.update_stats("prompt_cache", size_bytes=size, entry_count=count)
        except Exception as e:
            logger.error(f"Failed to cache prompt: {e}")

    def clear(self) -> None:
        """Clears the prompt cache."""
        self.cache_manager.clear_cache("prompt_cache")
