from .base import PostProcessor
from .fanuc import FanucPost
from .siemens import SiemensPost
from .haas import HaasPost
from .grbl import GrblPost

POSTPROCESSORS: dict[str, type[PostProcessor]] = {
    "fanuc": FanucPost,
    "siemens": SiemensPost,
    "haas": HaasPost,
    "grbl": GrblPost,
}


def get_postprocessor(name: str) -> PostProcessor:
    """Factory: get a post-processor instance by name."""
    cls = POSTPROCESSORS.get(name.lower())
    if cls is None:
        raise ValueError(f"Unknown post-processor: {name}. Available: {list(POSTPROCESSORS.keys())}")
    return cls()


__all__ = [
    "PostProcessor", "FanucPost", "SiemensPost", "HaasPost", "GrblPost",
    "POSTPROCESSORS", "get_postprocessor",
]
