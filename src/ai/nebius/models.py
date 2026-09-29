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
        id="nvidia/llama-3.3-nemotron-super-49b-v1",
        name="Nemotron Super 49B",
        context_window=131072,
        description="NVIDIA Nemotron Super 49B — strong reasoning and coding",
    ),
    NemotronModel(
        id="nvidia/llama-3.1-nemotron-ultra-253b-v1",
        name="Nemotron Ultra 253B",
        context_window=131072,
        description="NVIDIA Nemotron Ultra 253B — highest capability model",
    ),
]


def get_model_info(model_id: str) -> NemotronModel | None:
    """Look up model metadata by ID."""
    for model in KNOWN_MODELS:
        if model.id == model_id:
            return model
    return None
