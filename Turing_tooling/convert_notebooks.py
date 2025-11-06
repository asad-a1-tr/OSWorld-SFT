import json
import os
import sys
import glob
import re

def convert_notebook(file_path):
    """Converts a single old-style OSWorld notebook to the new format."""
    print(f"Processing {file_path}...")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error reading {file_path}: {e}")
        return

    new_cells = []
    step_counter = 1

    # First cell should be user instruction
    if notebook.get('cells') and notebook['cells'][0]['source'][0].startswith('**[user]**'):
        new_cells.append(notebook['cells'][0])
    else:
        print(f"Warning: No user instruction cell found in {file_path}")

    # Iterate through the rest of the cells, expecting action/tool_output pairs
    cell_iterator = iter(notebook.get('cells', [])[1:])
    for action_cell in cell_iterator:
        tool_output_cell = next(cell_iterator, None)

        if not tool_output_cell:
            print(f"Warning: Found an action cell without a following tool_output cell in {file_path}")
            continue

        try:
            # Extract action command
            action_source = "".join(action_cell.get('source', []))
            action_json_str = action_source.split('```json')[1].split('```')[0].strip()
            action_data = json.loads(action_json_str)
            command_str = action_data.get('arguments', '')
            # The actual command is usually on the second line after "import..."
            command = '\n'.join(command_str.splitlines()[1:]) if len(command_str.splitlines()) > 1 else command_str

            # Extract screenshot filenames from tool_output
            tool_output_source = "".join(tool_output_cell.get('source', []))
            attachments_json_str = tool_output_source.split('```json')[1].split('```')[0].strip()
            attachments = json.loads(attachments_json_str)

            screenshot_before = attachments[0]['src'].replace('vm://', '')
            screenshot_after = attachments[1]['src'].replace('vm://', '')

            # Create the new set of cells
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

        except (KeyError, IndexError, json.JSONDecodeError) as e:
            print(f"Warning: Could not process a cell pair in {file_path}. Error: {e}")
            # continue processing other cells

    # Assemble the new notebook
    new_notebook = {
        "cells": new_cells,
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 4
    }

    # Write the new notebook file
    new_file_path = file_path.replace('_old.ipynb', '.ipynb')
    if new_file_path == file_path:
        base, ext = os.path.splitext(file_path)
        new_file_path = f"{base}_converted{ext}"

    try:
        with open(new_file_path, 'w', encoding='utf-8') as f:
            json.dump(new_notebook, f, indent=2, ensure_ascii=False)
        print(f"Successfully converted {file_path} to {new_file_path}")
    except IOError as e:
        print(f"Error writing to {new_file_path}: {e}")


def main():
    """
    Main function to find and convert notebooks.
    Searches for files ending with '_old.ipynb' in the current directory and its subdirectories.
    """
    # Use glob to find all *_old.ipynb files recursively
    search_pattern = os.path.join('.', '**', '*_old.ipynb')
    old_notebooks = glob.glob(search_pattern, recursive=True)

    if not old_notebooks:
        print("No notebooks ending with '_old.ipynb' found to convert.")
        return

    print(f"Found {len(old_notebooks)} notebooks to convert.")
    for notebook_path in old_notebooks:
        convert_notebook(notebook_path)

if __name__ == "__main__":
    main()
