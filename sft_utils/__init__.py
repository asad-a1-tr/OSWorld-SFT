"""
SFT (Supervised Fine-Tuning) utilities for OSWorld manual data collection.

This package contains utilities for:
- Manual task execution with human interaction
- Jupyter notebook generation in SFT format
- Trajectory processing and data collection
"""

from .lib_run_manual import run_single_example_manual
from .notebook_generator import (
    generate_notebook_for_manual_task,
    create_sft_notebook_from_trajectory
)

__all__ = [
    "run_single_example_manual",
    "generate_notebook_for_manual_task", 
    "create_sft_notebook_from_trajectory"
]
