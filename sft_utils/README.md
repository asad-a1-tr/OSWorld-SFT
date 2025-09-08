# SFT Utils

Utilities for Supervised Fine-Tuning (SFT) data collection in OSWorld.

## Files

- `lib_run_manual.py`: Core library for manual task execution with human interaction
- `notebook_generator.py`: Utilities for generating Jupyter notebooks in SFT format
- `__init__.py`: Package initialization and exports

## Usage

### Manual Data Collection with Notebook Generation

```python
from sft_utils import run_single_example_manual

# This will automatically generate:
# - trajectory.jsonl (execution log)
# - recording.mp4 (screen recording)
# - {task_id}.ipynb (SFT notebook)
```

### Convert Existing Trajectories to Notebooks

Use the top-level script:

```bash
python convert_trajectory_to_notebook.py path/to/trajectory.jsonl --instruction "Your task instruction"
```

## SFT Notebook Format

The generated notebooks follow the OSWorld SFT format with:

1. **Metadata cell** - Task configuration JSON
2. **User cell** - Task instruction
3. **Assistant cells** - Reasoning for each step
4. **Tool call cells** - PyAutoGUI commands
5. **Tool output cells** - Screenshot and accessibility tree references
6. **Final assistant cell** - "DONE" marker

## Dependencies

- desktop_env
- pyautogui
- PIL (Pillow)
- Standard library (json, os, time, etc.)
