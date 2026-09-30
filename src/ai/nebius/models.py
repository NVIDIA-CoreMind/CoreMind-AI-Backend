"""
CoreMind Backend — Nebius Model Definitions.

Model IDs and metadata for available NVIDIA Nemotron models on Nebius.
These may change — the model ID is always configurable via env var.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NemotronModel:
    """Metadata for an available Nemotron model."""

    id: str
    name: str
    context_window: int
    description: str


# Known models on Nebius Token Factory (subject to change)
KNOWN_MODELS: list[NemotronModel] = [
    NemotronModel(
        id="nvidia/Nemotron-3-Ultra-550b-a55b",
        name="Nemotron 3 Ultra 550B",
        context_window=131072,
        description="NVIDIA Nemotron 3 Ultra 550B — highest capability reasoning and agent model",
    ),
    NemotronModel(
        id="nvidia/nemotron-3-super-120b-a12b",
        name="Nemotron 3 Super 120B",
        context_window=131072,
        description="NVIDIA Nemotron 3 Super 120B — deep reasoning model",
    ),
    NemotronModel(
        id="nvidia/Nemotron-3_5-Lightning",
        name="Nemotron 3.5 Lightning",
        context_window=131072,
        description="NVIDIA Nemotron 3.5 Lightning — high-speed reasoning model",
    ),
    NemotronModel(
        id="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        name="Nemotron 3 Nano 30B",
        context_window=131072,
        description="NVIDIA Nemotron 3 Nano 30B — efficient compact model",
    ),
]


def get_model_info(model_id: str) -> NemotronModel | None:
    """Look up model metadata by ID."""
    for model in KNOWN_MODELS:
        if model.id == model_id:
            return model
    return None
