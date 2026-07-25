"""SearXNG Auto Reranker plugin.

A configurable second-pass re-ranker overlaying rule-based and vector-based
ranking on top of SearXNG's native ranking. See README.md for details.
"""

__version__ = "0.1.0"


def __getattr__(name):  # PEP 562 lazy attribute access
    if name == "AutoRerankerPlugin":
        from .plugin import AutoRerankerPlugin
        return AutoRerankerPlugin
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["AutoRerankerPlugin"]
