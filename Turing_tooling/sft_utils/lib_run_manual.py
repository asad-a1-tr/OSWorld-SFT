import json
import logging
import os
import time
from typing import List
import pyautogui as pg
from PIL import Image
import io
import desktop_env.actions as actions
from .notebook_generator import generate_notebook_for_manual_task

from desktop_env.desktop_env import DesktopEnv

logger = logging.getLogger("desktopenv.manual_run.lib")


def _wait_for_observation(env: DesktopEnv, timeout: float = 60.0, poll_interval: float = 5.0):
    """Poll until screenshot is available."""
    deadline = time.time() + timeout
    obs = None
    while time.time() < deadline:
        obs = env._get_obs()
        if obs and obs.get("screenshot"):
            return obs
        time.sleep(poll_interval)
    return obs


def run_single_example_manual(
    env: DesktopEnv,
    config: dict,
    max_steps: int,
    instruction: str,
    args,
    result_dir: str,
):
    """
    Runs a single example in manual mode, prompting the user for actions.
    """
    os.makedirs(result_dir, exist_ok=True)
    # Reset environment for the new task
    env.reset(task_config=config)
    obs = _wait_for_observation(env)
    
    # Start recording
    recording_path = os.path.join(result_dir, "recording.mp4")
    env.controller.start_recording()
    
    # Wait for vm to be ready
    print("Initializing VM and services...")
    time.sleep(10)
    
    trajectory = []
    
    # Save initial screenshot as step_0.png
    initial_screenshot_path = os.path.join(result_dir, "step_0.png")
    if "screenshot" in obs and isinstance(obs["screenshot"], bytes):
        try:
            screenshot_img = Image.open(io.BytesIO(obs["screenshot"]))
            screenshot_img.save(initial_screenshot_path)
        except Exception as e:
            logger.error(f"Failed to save initial screenshot: {e}")
    
    print("\n" + "="*50)
    print(f"Instruction: {instruction}")
    print("="*50)
    print("Enter actions one by one. Type 'done' to finish the task, or 'exit' to quit.")
    print("You can see the VM screen in the VirtualBox/VMware window.")
    print("Mouse coordinates are based on a 1920x1080 screen resolution.")

    for step in range(max_steps):
        # Get manual action
        try:
            manual_action = input(f"\nStep {step + 1}/{max_steps} | Enter action (e.g., pg.click(100, 200)): ")
        except KeyboardInterrupt:
            print("\nExiting manual run.")
            break

        if not manual_action or manual_action.lower() == "exit":
            print("Exiting current task.")
            break
        if manual_action.lower() == "done":
            print("Task marked as done.")
            break

        # Save all available observations before the action
        step_log = {
            "step": step,
            "observation": {},
            "instruction": instruction
        }
        
        # Take a pre-action screenshot
        obs = _wait_for_observation(env)
        if "screenshot" in obs and isinstance(obs["screenshot"], bytes):
            try:
                screenshot_img = Image.open(io.BytesIO(obs["screenshot"]))
                screenshot_path = os.path.join(result_dir, f"step_{step+1}_pre.png")
                screenshot_img.save(screenshot_path)
                step_log["observation"]["screenshot_before"] = os.path.basename(screenshot_path)
            except Exception as e:
                logger.error(f"Failed to save screenshot: {e}")

        # Execute action
        try:
            if manual_action.startswith("pg."):
                command = manual_action.replace("pg.", "pyautogui.")
            elif manual_action.startswith("time.") or manual_action.startswith("actions."):
                command = manual_action
            else:
                command = f'pyautogui.typewrite("{manual_action}"); pyautogui.press("enter")'

            result = env.controller.execute_python_command(command)
            if result and result.get("error"):
                print(f"  -> Error from VM: {result['error']}")
            
            obs, reward, done, info = env.step(None)
            
            if "screenshot" in obs and isinstance(obs["screenshot"], bytes):
                try:
                    screenshot_img = Image.open(io.BytesIO(obs["screenshot"]))
                    screenshot_path = os.path.join(result_dir, f"step_{step+1}_post.png")
                    screenshot_img.save(screenshot_path)
                    step_log["observation"]["screenshot_after"] = os.path.basename(screenshot_path)
                except Exception as e:
                    logger.error(f"Failed to save screenshot: {e}")

            step_log["action"] = manual_action
            step_log["info"] = info
            print(f"  -> Executed: {manual_action}")
            if info.get('error'):
                print(f"  -> Error: {info['error']}")
        except Exception as e:
            print(f"  -> An error occurred during execution: {e}")
            step_log["action"] = manual_action
            step_log["error"] = str(e)

        trajectory.append(step_log)
        
        if args.sleep_after_execution > 0:
            time.sleep(args.sleep_after_execution)

        if done:
            print("Environment signaled task is done.")
            break

    # Stop recording and save trajectory
    video_path = env.controller.end_recording(dest=recording_path)
    if video_path:
        # Ensure the target directory exists
        os.makedirs(result_dir, exist_ok=True)
        # Move the recording to the desired results directory
        final_video_path = os.path.join(result_dir, "recording.mp4")
        os.rename(video_path, final_video_path)
        print(f"Video saved to {final_video_path}")
    
    traj_path = os.path.join(result_dir, "trajectory.jsonl")
    with open(traj_path, "w", encoding="utf-8") as f:
        for entry in trajectory:
            f.write(json.dumps(entry) + "\n")
            
    print(f"Trajectory saved to {traj_path}")
    
    # Generate SFT notebook
    try:
        notebook_path = generate_notebook_for_manual_task(
            task_config=config,
            instruction=instruction,
            trajectory=trajectory,
            result_dir=result_dir
        )
        print(f"SFT Notebook saved to {notebook_path}")
    except Exception as e:
        logger.error(f"Failed to generate SFT notebook: {e}")
    # Run evaluation after manual session completes and notebook generation
    try:
        score = env.evaluate()
        print(f"Evaluation score: {score}")
        with open(os.path.join(result_dir, "evaluation_score.txt"), "w", encoding="utf-8") as sf:
            sf.write(str(score))
    except Exception as e:
        logger.error(f"Failed to evaluate task: {e}")
    
    print("="*50 + "\n")
