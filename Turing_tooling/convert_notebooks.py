import json
import os
import sys
import glob

def is_new_format(notebook):
    """Heuristically checks if a notebook is already in the new format."""
    if not isinstance(notebook, dict):
        return False

    # New format has a specific metadata structure
    if "language_info" not in notebook.get("metadata", {}):
        return False

    # New format has step-based cells
    cells = notebook.get("cells", [])
    if len(cells) > 1:
        cell_source = "".join(cells[1].get("source", []))
        if cell_source.startswith("**[Step 1 pre]**"):
            return True
    
    # If it has metadata but no steps (e.g., only a user cell), consider it new format.
    return True

def convert_old_to_new(notebook):
    """Converts a notebook dictionary from the old format to the new format."""
    new_cells = []
    step_counter = 1

    # First cell should be user instruction
    if notebook.get('cells') and notebook['cells'][0]['source'][0].startswith('**[user]**'):
        new_cells.append(notebook['cells'][0])
    
    cell_iterator = iter(notebook.get('cells', [])[1:])
    for action_cell in cell_iterator:
        tool_output_cell = next(cell_iterator, None)

        if not tool_output_cell:
            continue

        try:
            action_source = "".join(action_cell.get('source', []))
            action_json_str = action_source.split('```json')[1].split('```')[0].strip()
            action_data = json.loads(action_json_str)
            command_str = action_data.get('arguments', '')
            command = '\n'.join(command_str.splitlines()[1:]) if len(command_str.splitlines()) > 1 else command_str

            tool_output_source = "".join(tool_output_cell.get('source', []))
            attachments_json_str = tool_output_source.split('```json')[1].split('```')[0].strip()
            attachments = json.loads(attachments_json_str)

            screenshot_before = attachments[0]['src'].replace('vm://', '')
            screenshot_after = attachments[1]['src'].replace('vm://', '')

            pre_screenshot_cell = {
                "cell_type": "markdown", "metadata": {},
                "source": [f"**[Step {step_counter} pre]**\n\n![step_{step_counter}_pre](./{screenshot_before})"]
            }
            new_action_cell = {
                "cell_type": "markdown", "metadata": {},
                "source": [f"**[action]**\n\n```json\n{command}\n```"]
            }
            post_screenshot_cell = {
                "cell_type": "markdown", "metadata": {},
                "source": [f"**[Step {step_counter} post]**\n\n![step_{step_counter}_post](./{screenshot_after})"]
            }

            new_cells.extend([pre_screenshot_cell, new_action_cell, post_screenshot_cell])
            step_counter += 1
        except (KeyError, IndexError, json.JSONDecodeError):
            # This pair of cells is not in the expected old format, skip.
            continue

    # If no cells were converted, it's likely not the old format.
    if step_counter == 1:
        return None

    return {
        "cells": new_cells,
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 4
    }

def process_notebooks(input_dir, output_dir):
    """Processes all notebooks in the input directory and saves them to the output directory."""
    search_pattern = os.path.join(input_dir, '**', '*.ipynb')
    notebook_paths = glob.glob(search_pattern, recursive=True)

    if not notebook_paths:
        print(f"No .ipynb files found in '{input_dir}'.")
        return

    print(f"Found {len(notebook_paths)} notebooks to process.")

    for notebook_path in notebook_paths:
        print(f"Processing {notebook_path}...")
        
        try:
            with open(notebook_path, 'r', encoding='utf-8') as f:
                notebook_data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"  - Error reading file: {e}")
            continue

        output_notebook_data = None
        if is_new_format(notebook_data):
            print("  - Already in new format. Copying as is.")
            output_notebook_data = notebook_data
        else:
            print("  - Old format detected. Converting...")
            output_notebook_data = convert_old_to_new(notebook_data)
            if output_notebook_data:
                 print("  - Conversion successful.")
            else:
                 print("  - Conversion failed or not applicable.")
                 # If conversion fails, we can copy the original file
                 output_notebook_data = notebook_data

        relative_path = os.path.relpath(notebook_path, input_dir)
        output_path = os.path.join(output_dir, relative_path)
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output_notebook_data, f, indent=2, ensure_ascii=False)
            print(f"  - Saved to {output_path}")
        except IOError as e:
            print(f"  - Error writing to file: {e}")

def main():
    """Main entry point for the script."""
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python convert_notebooks.py <input_directory> [output_directory]")
        sys.exit(1)

    input_dir = sys.argv[1]
    output_dir = input_dir # Default to input_dir if output_dir is not provided

    if len(sys.argv) == 3:
        output_dir = sys.argv[2]

    if not os.path.isdir(input_dir):
        print(f"Error: Input directory '{input_dir}' not found.")
        sys.exit(1)

    # Ensure output directory exists (only needed if output_dir is different from input_dir)
    # If output_dir is input_dir, it's already checked by os.path.isdir(input_dir)
    if output_dir != input_dir:
        os.makedirs(output_dir, exist_ok=True)

    process_notebooks(input_dir, output_dir)

if __name__ == "__main__":
    main()