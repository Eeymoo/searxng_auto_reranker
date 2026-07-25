"""SearXNG Auto Reranker plugin.

A configurable second-pass re-ranker overlaying rule-based and vector-based
ranking on top of SearXNG's native ranking. See README.md for details.
"""

__version__ = "0.1.0"

from .plugin import AutoRerankerPlugin

__all__ = ["AutoRerankerPlugin"]
