import json
import os
import time
import uuid
from typing import List, Dict, Any

def generate_notebook_for_manual_task(
    task_config: dict,
    instruction: str,
    trajectory: List[dict],
    result_dir: str,
    task_id: str = None
) -> str:
    """
    Generate a Jupyter notebook in the OSWorld SFT format based on manual task execution.
    
    Args:
        task_config: The task configuration dictionary
        instruction: The task instruction string
        trajectory: List of step logs from manual execution
        result_dir: Directory where results are stored
        task_id: Optional task ID, will be generated if not provided
    
    Returns:
        Path to the generated notebook file
    """
    
    if not task_id:
        task_id = f"osw.manual_task.{int(time.time())}"
    
    # Create notebook structure
    notebook = {
        "cells": [],
        "metadata": {
            "language_info": {
                "name": "python"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 4
    }
    
    # 2. User instruction cell
    user_content = f"""**[user]**

{instruction}"""
    
    notebook["cells"].append({
        "cell_type": "markdown",
        "metadata": {},
        "source": [user_content]
    })
    
    # 3. Process trajectory steps
    step_counter = 1
    
    for step_data in trajectory:
        if "action" not in step_data:
            continue
            
        action = step_data["action"]
        
        # Skip non-action steps
        if action.lower() in ["done", "exit"]:
            continue

        # Pre-action screenshot cell
        if "screenshot_before" in step_data["observation"]:
            screenshot_before_path = step_data['observation']['screenshot_before']
            pre_screenshot_content = f"**[Step {step_counter} pre]**\n\n![step_{step_counter}_pre](./{screenshot_before_path})"
            notebook["cells"].append({
                "cell_type": "markdown",
                "metadata": {},
                "source": [pre_screenshot_content]
            })

        # Action cell
        if action.startswith("pg."):
            command = action.replace("pg.", "pyautogui.")
        else:
            command = action
        
        tool_call_content = f"**[action]**\n\n```json\n{command}\n```"
        notebook["cells"].append({
            "cell_type": "markdown",
            "metadata": {},
            "source": [tool_call_content]
        })
        
        # Post-action screenshot cell
        if "screenshot_after" in step_data["observation"]:
            screenshot_after_path = step_data['observation']['screenshot_after']
            post_screenshot_content = f"**[Step {step_counter} post]**\n\n![step_{step_counter}_post](./{screenshot_after_path})"
            notebook["cells"].append({
                "cell_type": "markdown",
                "metadata": {},
                "source": [post_screenshot_content]
            })
        
        step_counter += 1
    
    # Save notebook
    notebook_path = os.path.join(result_dir, f"{task_id}.ipynb")
    with open(notebook_path, 'w', encoding='utf-8') as f:
        json.dump(notebook, f, indent=2, ensure_ascii=False)
    
    return notebook_path

def create_sft_notebook_from_trajectory(
    trajectory_path: str,
    task_config: dict,
    instruction: str,
    output_dir: str = None
) -> str:
    """
    Create SFT notebook from an existing trajectory file.
    
    Args:
        trajectory_path: Path to trajectory.jsonl file
        task_config: Task configuration dictionary
        instruction: Task instruction
        output_dir: Output directory (defaults to same as trajectory)
    
    Returns:
        Path to generated notebook
    """
    import time
    
    if output_dir is None:
        output_dir = os.path.dirname(trajectory_path)
    
    # Load trajectory
    trajectory = []
    with open(trajectory_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                trajectory.append(json.loads(line))
    
    # Generate task ID from trajectory filename
    task_name = os.path.splitext(os.path.basename(trajectory_path))[0]
    task_id = f"osw.manual.{task_name}"
    
    return generate_notebook_for_manual_task(
        task_config=task_config,
        instruction=instruction,
        trajectory=trajectory,
        result_dir=output_dir,
        task_id=task_id
    )
