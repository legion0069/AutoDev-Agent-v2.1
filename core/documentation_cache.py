"""
documentation_cache.py - Documentation Fragment Cache for AutoDev (v3.6.1)

Reduces documentation generation time by caching sections derived from unchanged source code.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from core.cache_manager import CacheManager

logger = logging.getLogger("AutoDev.DocumentationCache")

class DocumentationCache:
    """
    Caches documentation fragments derived from source file ASTs and symbols.
    """

    VERSION = "1.0.0"

    def __init__(self, cache_manager: Optional[CacheManager] = None) -> None:
        self.cache_manager = cache_manager or CacheManager()
        self.cache_path = self.cache_manager.register_cache("documentation_cache", self.VERSION)

    def _compute_key(self, doc_type: str, source_hash: str, params: Dict[str, Any]) -> str:
        """Computes a unique cache key."""
        param_str = json.dumps(params, sort_keys=True)
        raw_key = f"{doc_type}:{source_hash}:{param_str}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get_fragment(self, doc_type: str, source_hash: str, params: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Retrieves a cached documentation fragment."""
        key = self._compute_key(doc_type, source_hash, params or {})
        cache_file = self.cache_path / f"{key}.md"
        
        if cache_file.exists():
            try:
                fragment = cache_file.read_text(encoding="utf-8")
                self.cache_manager.update_stats("documentation_cache", hit=True)
                return fragment
            except Exception as e:
                logger.warning(f"Failed to read cached doc fragment: {e}")
        
        self.cache_manager.update_stats("documentation_cache", miss=True)
        return None

    def set_fragment(self, doc_type: str, source_hash: str, fragment: str, params: Optional[Dict[str, Any]] = None) -> None:
        """Caches a documentation fragment."""
        key = self._compute_key(doc_type, source_hash, params or {})
        cache_file = self.cache_path / f"{key}.md"
        
        try:
            cache_file.write_text(fragment, encoding="utf-8")
            
            # Update stats
            size = sum(f.stat().st_size for f in self.cache_path.glob("*.md"))
            count = len(list(self.cache_path.glob("*.md")))
            self.cache_manager.update_stats("documentation_cache", size_bytes=size, entry_count=count)
        except Exception as e:
            logger.error(f"Failed to cache doc fragment: {e}")

    def clear(self) -> None:
        """Clears the documentation cache."""
        self.cache_manager.clear_cache("documentation_cache")
