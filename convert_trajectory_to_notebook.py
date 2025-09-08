#!/usr/bin/env python3
"""
Utility script to convert existing trajectory.jsonl files to SFT notebooks.

Usage:
    python convert_trajectory_to_notebook.py <trajectory_path> [--task_config <config_path>] [--instruction "<instruction>"]
"""

import argparse
import json
import os
import sys
from sft_utils import create_sft_notebook_from_trajectory


def main():
    parser = argparse.ArgumentParser(
        description="Convert trajectory.jsonl to SFT notebook format"
    )
    parser.add_argument(
        "trajectory_path", 
        help="Path to trajectory.jsonl file"
    )
    parser.add_argument(
        "--task_config", 
        help="Path to task config JSON file (optional)"
    )
    parser.add_argument(
        "--instruction", 
        default="Complete the given task",
        help="Task instruction text"
    )
    parser.add_argument(
        "--output_dir",
        help="Output directory (defaults to same as trajectory file)"
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.trajectory_path):
        print(f"Error: Trajectory file {args.trajectory_path} not found")
        sys.exit(1)
    
    # Load task config if provided
    task_config = {}
    if args.task_config and os.path.exists(args.task_config):
        with open(args.task_config, 'r') as f:
            task_config = json.load(f)
    else:
        # Create minimal task config
        task_name = os.path.splitext(os.path.basename(args.trajectory_path))[0]
        task_config = {
            "task_id": f"osw.manual.{task_name}",
            "title": f"Manual task: {task_name}",
            "instruction": args.instruction,
            "modality": ["screenshot", "a11y_tree"],
            "action_schema": "pyautogui_code_string",
            "tool_name": "pyautogui"
        }
    
    try:
        notebook_path = create_sft_notebook_from_trajectory(
            trajectory_path=args.trajectory_path,
            task_config=task_config,
            instruction=args.instruction,
            output_dir=args.output_dir
        )
        print(f"Successfully created notebook: {notebook_path}")
    except Exception as e:
        print(f"Error creating notebook: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
