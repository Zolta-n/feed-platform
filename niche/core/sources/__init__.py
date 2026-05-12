"""Source adapters — each implements Source.fetch() -> [RawItem] (EP2)."""
from .base import RawItem, Source
from .factory import SOURCE_REGISTRY, build_sources

__all__ = ["RawItem", "Source", "SOURCE_REGISTRY", "build_sources"]
