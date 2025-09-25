import os
import shutil
import tkinter as tk
from tkinter import filedialog
import json


def collect_files(src, colab_dest, traj_dest):
    """Collect notebooks into Colab and other relevant files into Trajectory"""
    for root, _, files in os.walk(src):
        for file in files:
            src_file = os.path.join(root, file)

            # Skip evaluator.diff
            if file == "evaluator.diff":
                continue

            # Rule 1: notebooks → Colab
            if file.endswith(".ipynb") and colab_dest:
                shutil.copy2(src_file, os.path.join(colab_dest, file))

            # Rule 2: screenshots, json, logs, txt, xml → Trajectory
            elif file.endswith((".png", ".jpg", ".jpeg", ".json", ".txt", ".log", ".xml")) and traj_dest:
                shutil.copy2(src_file, os.path.join(traj_dest, file))

            else:
                # Ignore junk/system files
                pass


def copy_sft(src, dest):
    """Rebuild SFT with only Colab and Trajectory content"""
    os.makedirs(dest, exist_ok=True)

    colab_dest = os.path.join(dest, "Colab")
    traj_dest = os.path.join(dest, "Trajectory and Screenshot")
    os.makedirs(colab_dest, exist_ok=True)
    os.makedirs(traj_dest, exist_ok=True)

    collect_files(src, colab_dest, traj_dest)


def find_subdir_ending_with(root_dir: str, tail_parts):
    """Search for a directory within root_dir whose relative path ends with the given tail_parts sequence.
    Returns the first match or None if not found.
    """
    tail = os.path.join(*tail_parts)
    for current_root, dirs, _ in os.walk(root_dir):
        for d in dirs:
            candidate = os.path.join(current_root, d)
            # Normalize case and separators
            if candidate.replace("\\", "/").endswith(tail.replace("\\", "/")):
                return candidate
    return None


def copy_evaluation_score(src_tree: str, dest_file: str):
    """Find and copy evaluation_score.txt from anywhere under src_tree to dest_file. Create empty if missing."""
    for current_root, _, files in os.walk(src_tree):
        if "evaluation_score.txt" in files:
            shutil.copy2(os.path.join(current_root, "evaluation_score.txt"), dest_file)
            return
    # If not found, create an empty placeholder
    open(dest_file, "w").close()


def process_annotator(src_root: str, dest_root: str, tool: str, taskid: str):
    """Rebuild annotator folder into correct structure, scoped to tool/taskid when possible."""
    os.makedirs(dest_root, exist_ok=True)

    # Detect the most relevant source subtree
    specific = os.path.join(src_root, tool, taskid)
    if os.path.isdir(specific):
        chosen_src = specific
    else:
        chosen_src = find_subdir_ending_with(src_root, [tool, taskid]) or src_root

    colab_dest = os.path.join(dest_root, "Colab")
    traj_dest = os.path.join(dest_root, "Trajectory and Screenshot")
    os.makedirs(colab_dest, exist_ok=True)
    os.makedirs(traj_dest, exist_ok=True)

    # evaluation_score.txt handling
    copy_evaluation_score(src_root, os.path.join(dest_root, "evaluation_score.txt"))

    collect_files(chosen_src, colab_dest, traj_dest)


def process_run(src_root: str, dest_root: str, tool: str, taskid: str, model_name: str):
    """Rebuild run folder into correct structure, focusing on subfolder matching tool/taskid when available."""
    os.makedirs(dest_root, exist_ok=True)
    traj_dest = os.path.join(dest_root, "Trajectory and Screenshot")
    os.makedirs(traj_dest, exist_ok=True)

    # Prefer deeper pattern including model_name/tool/taskid, then tool/taskid, else entire run
    match = (
        find_subdir_ending_with(src_root, [model_name, tool, taskid])
        or find_subdir_ending_with(src_root, [tool, taskid])
        or src_root
    )

    collect_files(match, None, traj_dest)


def find_run_folder(base_dir, index):
    """Return the path to run folder supporting run_1 or run_01 naming."""
    candidates = [
        os.path.join(base_dir, f"run_{index}"),
        os.path.join(base_dir, f"run_{index:02d}")
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    return None


def find_tool_taskid_in_directory(base_dir, tool, taskid):
    """Search for a directory containing tool/taskid structure within base_dir.
    
    Returns the path if found, None otherwise.
    """
    if not os.path.isdir(base_dir):
        return None
    
    # Check direct path: base_dir/tool/taskid
    direct_path = os.path.join(base_dir, tool, taskid)
    if os.path.isdir(direct_path):
        return direct_path
    
    # Search recursively for tool/taskid pattern
    for root, dirs, _ in os.walk(base_dir):
        for d in dirs:
            if d == taskid:
                # Check if parent directory is the tool
                parent = os.path.basename(root)
                if parent == tool:
                    return os.path.join(root, d)
    
    return None


def check_annotator_has_content(annotator_path, tool, taskid):
    """Check if annotator directory has the tool/taskid structure."""
    return find_tool_taskid_in_directory(annotator_path, tool, taskid) is not None


def check_run_has_content(run_path, tool, taskid):
    """Check if run directory has the tool/taskid structure."""
    return find_tool_taskid_in_directory(run_path, tool, taskid) is not None


def check_sft_has_content(sft_base, tool, taskid):
    """Check if SFT directory has the tool/taskid structure."""
    sft_path = os.path.join(sft_base, tool, taskid)
    return os.path.isdir(sft_path)


def load_tasks_from_manual(manual_path):
    """Load tool and task ids from evaluation_examples/manual_task.json.

    Returns a list of (tool, task_id) tuples.
    """
    if not os.path.isfile(manual_path):
        print(f"Error: manual_task.json not found at {manual_path}")
        return []

    with open(manual_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tasks = []
    for tool, ids in data.items():
        if isinstance(ids, list):
            for task_id in ids:
                tasks.append((tool, task_id))
        elif isinstance(ids, str):
            tasks.append((tool, ids))
    return tasks


def main():
    root = tk.Tk()
    root.withdraw()

    # Select the project root containing SFT, run_*, annotator_*, evaluation_examples
    source_folder = filedialog.askdirectory(title="Select your project root (contains SFT, run_*, annotator_*, evaluation_examples)")
    if not source_folder:
        print("No source folder selected. Exiting.")
        return

    # Load tool and task id(s) from evaluation_examples/manual_task.json
    manual_path = os.path.join(source_folder, "evaluation_examples", "manual_task.json")
    tasks = load_tasks_from_manual(manual_path)
    if not tasks:
        print("Error: No tasks found in manual_task.json. Exiting.")
        return

    # Fixed model name
    model_name = "claude-4-sonnet-20250514"

    for tool, taskid in tasks:
        print(f"\nProcessing task: tool={tool}, id={taskid}")

        # First, check what content exists for this tool/taskid combination
        sft_exists = check_sft_has_content(os.path.join(source_folder, "SFT"), tool, taskid)
        
        # Check annotators
        annotators_with_content = []
        for i in range(1, 4):
            ann_path = os.path.join(source_folder, f"annotator_{i}")
            if check_annotator_has_content(ann_path, tool, taskid):
                annotators_with_content.append(i)
        
        # Check runs
        runs_with_content = []
        for i in range(1, 17):
            run_path = find_run_folder(source_folder, i)
            if run_path and check_run_has_content(run_path, tool, taskid):
                runs_with_content.append(i)
        
        # Only proceed if we found any content
        if not (sft_exists or annotators_with_content or runs_with_content):
            print(f"⚠️  No content found for {tool}/{taskid} in any directory. Skipping.")
            continue

        print(f"📁 Found content in: SFT={sft_exists}, Annotators={annotators_with_content}, Runs={runs_with_content}")

        # Create destination root folder (same as JSON filename / task id)
        dest_root = os.path.join(os.path.dirname(source_folder), taskid)
        os.makedirs(dest_root, exist_ok=True)

        # --- Copy example JSON ---
        example_json = os.path.join(source_folder, "evaluation_examples", "examples", tool, f"{taskid}.json")
        if os.path.isfile(example_json):
            shutil.copy2(example_json, os.path.join(dest_root, f"{taskid}.json"))
            print("Copied example JSON.")
        else:
            print(f"Warning: Example JSON not found at {example_json}")

        # --- Copy SFT (only if exists) ---
        if sft_exists:
            sft_src = os.path.join(source_folder, "SFT", tool, taskid)
            sft_dest = os.path.join(dest_root, "SFT")
            copy_sft(sft_src, sft_dest)
            print("✅ Copied SFT content.")

        # --- Process runs (only those with content) ---
        if runs_with_content:
            runs_dest = os.path.join(dest_root, model_name)
            os.makedirs(runs_dest, exist_ok=True)
            for i in runs_with_content:
                run_src = find_run_folder(source_folder, i)
                run_dest = os.path.join(runs_dest, f"run_{i:02d}")
                if run_src:
                    process_run(run_src, run_dest, tool, taskid, model_name)
                    print(f"✅ Processed {os.path.basename(run_src)} -> run_{i:02d}")

        # --- Process annotators (only those with content) ---
        if annotators_with_content:
            annotator_root = os.path.join(dest_root, "Annotator Trajectory")
            os.makedirs(annotator_root, exist_ok=True)
            for i in annotators_with_content:
                ann_src = os.path.join(source_folder, f"annotator_{i}")
                ann_dest = os.path.join(annotator_root, f"annotator_{i}")
                process_annotator(ann_src, ann_dest, tool, taskid)
                print(f"✅ Processed annotator_{i}")

        print(f"\n✅ Output generated at: {dest_root}")

    print("\nAll tasks completed.")


if __name__ == "__main__":
    main()
