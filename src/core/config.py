"""YAML-based configuration management."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


_DEFAULTS: dict[str, Any] = {
    "stock": {"x": 100.0, "y": 100.0, "z": 20.0, "material": "Aluminum 6061"},
    "target": {"x": 60.0, "y": 60.0, "z": 15.0, "fillet_radius": 3.0},
    "tools": [
        {
            "name": "10mm Flat Endmill",
            "type": "flat_endmill",
            "diameter": 10.0,
            "flute_length": 30.0,
            "flutes": 3,
        },
        {
            "name": "6mm Ball Endmill",
            "type": "ball_endmill",
            "diameter": 6.0,
            "flute_length": 20.0,
            "flutes": 2,
        },
    ],
    "cutting": {
        "spindle_rpm": 8000,
        "feed_rate": 500.0,
        "plunge_rate": 200.0,
        "depth_per_pass": 2.0,
        "stepover_ratio": 0.4,
    },
    "postprocessor": "fanuc",
    "output": {
        "step": "output/step/part.step",
        "gcode": "output/gcode/part.nc",
        "image": "output/images/part.png",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


@dataclass
class Config:
    """Project configuration loaded from YAML with defaults."""

    data: dict[str, Any] = field(default_factory=lambda: _DEFAULTS.copy())

    @classmethod
    def from_yaml(cls, path: str | Path) -> Config:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path) as f:
            user_data = yaml.safe_load(f) or {}
        merged = _deep_merge(_DEFAULTS, user_data)
        return cls(data=merged)

    @classmethod
    def default(cls) -> Config:
        return cls(data=_DEFAULTS.copy())

    def get(self, *keys: str, default: Any = None) -> Any:
        """Nested key access: config.get('stock', 'x')"""
        val = self.data
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k, default)
            else:
                return default
        return val

    def __getitem__(self, key: str) -> Any:
        return self.data[key]
