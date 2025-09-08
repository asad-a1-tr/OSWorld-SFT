import json
import logging
import os
import time
from typing import List
import pyautogui as pg
import time
from PIL import Image
import io
import desktop_env.actions as actions
from .notebook_generator import generate_notebook_for_manual_task

from desktop_env.desktop_env import DesktopEnv

logger = logging.getLogger("desktopenv.manual_run.lib")

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
    obs = env.reset(task_config=config)
    # Refresh observation after setup completed so initial screenshots reflect opened files
    time.sleep(1)
    obs = env._get_obs()
    
    # Start recording
    recording_path = os.path.join(result_dir, "recording.mp4")
    env.controller.start_recording()
    
    # Wait for accessibility service to be ready
    print("Initializing VM and services...")
    time.sleep(10)  # Give VM time to fully start up
    
    # Test accessibility service with debug checks
    print("Testing accessibility service...")
    # Check if AT-SPI is installed and running
    env.controller.execute_python_command("import subprocess; result = subprocess.run(['ps', 'aux'], capture_output=True, text=True); print('AT-SPI Processes:', [line for line in result.stdout.split('\\n') if 'at-spi' in line])")
    time.sleep(1)
    # Try to get accessibility tree
    result = env.controller.get_accessibility_tree()
    if result:
        print("Successfully got accessibility tree!")
        print(f"Tree size: {len(result)} characters")
        print("First 200 characters of tree:", result[:200])
    else:
        print("Warning: Could not get accessibility tree. Trying to fix...")
        print("Attempting to start AT-SPI if not running...")
        # Try to start AT-SPI services
        env.controller.execute_python_command("subprocess.run(['systemctl', '--user', 'start', 'at-spi-dbus-bus.service'])")
        env.controller.execute_python_command("pyautogui.press('win')")
        time.sleep(2)
        print("Retrying accessibility tree capture...")
        result = env.controller.get_accessibility_tree()
        if not result:
            print("Error: Could not initialize accessibility service.")
            print("Checking AT-SPI status:")
            env.controller.execute_python_command("subprocess.run(['systemctl', '--user', 'status', 'at-spi-dbus-bus.service'])")
            time.sleep(2)
    
    trajectory = []
    
    print("\n" + "="*50)
    print(f"Instruction: {instruction}")
    print("="*50)
    print("Enter actions one by one. Type 'done' to finish the task, or 'exit' to quit.")
    print("You can see the VM screen in the VirtualBox/VMware window.")
    print("Mouse coordinates are based on a 1920x1080 screen resolution.")

    for step in range(max_steps):
        # Save all available observations before the action
        observation_log = {}
        if "screenshot" in obs and isinstance(obs["screenshot"], bytes):
            try:
                screenshot_img = Image.open(io.BytesIO(obs["screenshot"]))
                screenshot_path = os.path.join(result_dir, f"step_{step}_before.png")
                screenshot_img.save(screenshot_path)
                observation_log["screenshot"] = screenshot_path
            except Exception as e:
                logger.error(f"Failed to save screenshot: {e}")

        if "accessibility_tree" in obs and obs["accessibility_tree"]:
            a11y_path = os.path.join(result_dir, f"step_{step}_before.xml")
            with open(a11y_path, "w", encoding="utf-8") as f:
                f.write(obs["accessibility_tree"])
            observation_log["a11y_tree"] = a11y_path
            print(f"  -> Saved accessibility tree to {a11y_path}")

        if "som" in obs and isinstance(obs["som"], bytes):
            try:
                som_img = Image.open(io.BytesIO(obs["som"]))
                som_path = os.path.join(result_dir, f"step_{step}_before_som.png")
                som_img.save(som_path)
                observation_log["som"] = som_path
            except Exception as e:
                logger.error(f"Failed to save SoM image: {e}")

        step_log = {
            "step": step,
            "observation": observation_log,
            "instruction": instruction
        }

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

        # Execute action
        try:
            if manual_action.startswith("pg."):
                # Convert pg.X to pyautogui.X
                command = manual_action.replace("pg.", "pyautogui.")
                print(f"  -> Converting to VM command: {command}")
            elif manual_action.startswith("time.") or manual_action.startswith("actions."):
                # It's a Python command, use as is
                command = manual_action
                print(f"  -> Executing Python command: {command}")
            else:
                # If it's not a Python command, assume it's a shell command
                print(f"  -> Interpreted as shell command: {manual_action}")
                command = f'pyautogui.typewrite("{manual_action}"); pyautogui.press("enter")'

            # Send the command to the VM to execute
            result = env.controller.execute_python_command(command)
            if result and result.get("error"):
                print(f"  -> Error from VM: {result['error']}")
            
            # Get the new state
            obs, reward, done, info = env.step(None)  # Pass None because action is already executed
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
        
        # Optional sleep
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
