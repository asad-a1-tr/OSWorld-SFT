"""Script to run 16 parallel evaluations for pass@k calculation.
Combines parallel processing from run_multienv_claude.py with agent.py support from run.py.
"""

import argparse
import datetime
import json
import logging
import os
import sys
import signal
import time
from typing import List
from multiprocessing import Process, Manager, current_process
import lib_run_single
from desktop_env.desktop_env import DesktopEnv
from mm_agents.agent import PromptAgent

# Global variables for signal handling
active_environments = []
processes = []
is_terminating = False

# Logger Configs
def config() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run 16 parallel evaluations for pass@k calculation"
    )

    # environment config
    parser.add_argument("--path_to_vm", type=str, default=None)
    parser.add_argument(
        "--provider_name", type=str, default="vmware",
        help="Virtualization provider (vmware, docker, aws, azure, gcp, virtualbox)"
    )
    parser.add_argument(
        "--headless", action="store_true", help="Run in headless machine"
    )
    parser.add_argument(
        "--action_space", type=str, default="pyautogui", help="Action type"
    )
    parser.add_argument(
        "--observation_type",
        choices=["screenshot", "a11y_tree", "screenshot_a11y_tree", "som"],
        default="a11y_tree",
        help="Observation type",
    )
    parser.add_argument("--screen_width", type=int, default=1920)
    parser.add_argument("--screen_height", type=int, default=1080)
    parser.add_argument("--sleep_after_execution", type=float, default=0.0)
    parser.add_argument("--max_steps", type=int, default=15)
    parser.add_argument(
        "--client_password", type=str, default="", help="Client password"
    )

    # agent config
    parser.add_argument("--max_trajectory_length", type=int, default=3)
    parser.add_argument(
        "--test_config_base_dir", type=str, default="evaluation_examples"
    )

    # lm config
    parser.add_argument("--model", type=str, default="gpt-4o")
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--top_p", type=float, default=0.9)
    parser.add_argument("--max_tokens", type=int, default=1500)
    parser.add_argument("--stop_token", type=str, default=None)

    # example config
    parser.add_argument("--domain", type=str, default="all")
    parser.add_argument(
        "--test_all_meta_path", type=str, default="evaluation_examples/test_all.json"
    )
    parser.add_argument(
        "--specific_task", type=str, required=True,
        help="REQUIRED: Specify which task to run in format 'domain/example_id' (e.g., 'chrome/bb5e4c0d-f964-439c-97b6-bdb9747de3f4')"
    )

    # logging related
    parser.add_argument("--result_dir", type=str, default="./results")
    parser.add_argument("--num_parallel_runs", type=int, default=16, help="Number of parallel runs for pass@k calculation")
    parser.add_argument("--log_level", type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], 
                       default='INFO', help="Set the logging level")

    # aws config
    parser.add_argument(
        "--region", type=str, default="us-east-1", help="AWS region for the VM"
    )
    parser.add_argument(
        "--disable_signal_handling", action="store_true", 
        help="Disable Ctrl+C signal handling (script will ignore keyboard interrupts)"
    )
    parser.add_argument(
        "--continue_on_interrupt", action="store_true",
        help="Continue running tasks even after Ctrl+C (asks for confirmation)"
    )
    
    args = parser.parse_args()
    return args

args = config()  # Get command line arguments first

logger = logging.getLogger()
log_level = getattr(logging, args.log_level.upper())
logger.setLevel(log_level)

datetime_str: str = datetime.datetime.now().strftime("%Y%m%d@%H%M%S")

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)

file_handler = logging.FileHandler(
    os.path.join("logs", f"parallel_eval-{datetime_str}.log"), encoding="utf-8"
)
debug_handler = logging.FileHandler(
    os.path.join("logs", f"parallel_eval_debug-{datetime_str}.log"), encoding="utf-8"
)
stdout_handler = logging.StreamHandler(sys.stdout)

file_handler.setLevel(logging.INFO)
debug_handler.setLevel(logging.DEBUG)
stdout_handler.setLevel(logging.INFO)

formatter = logging.Formatter(
    fmt="\x1b[1;33m[%(asctime)s \x1b[31m%(levelname)s \x1b[32m%(module)s/%(lineno)d-%(processName)s\x1b[1;33m] \x1b[0m%(message)s"
)
file_handler.setFormatter(formatter)
debug_handler.setFormatter(formatter)
stdout_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(debug_handler)
logger.addHandler(stdout_handler)

logger = logging.getLogger("desktopenv.parallel_eval")


def distribute_tasks(test_all_meta: dict, specific_task: str) -> List[tuple]:
    """Distribute tasks across all domains for parallel processing"""
    all_tasks = []
    
    # Parse specific task format: "domain/example_id"
    if "/" in specific_task:
        domain, example_id = specific_task.split("/", 1)
        if domain in test_all_meta and example_id in test_all_meta[domain]:
            all_tasks.append((domain, example_id))
            return all_tasks
        else:
            raise ValueError(f"Task '{specific_task}' not found in test configuration")
    else:
        raise ValueError(f"Invalid task format. Use 'domain/example_id' (e.g., 'chrome/bb5e4c0d-f964-439c-97b6-bdb9747de3f4')")


def run_env_tasks(task_queue, args, shared_scores):
    """Worker process function to run tasks in parallel"""
    env = None
    agent = None
    
    try:
        # Initialize agent
        agent = PromptAgent(
            model=args.model,
            temperature=args.temperature,
            top_p=args.top_p,
            max_tokens=args.max_tokens,
            max_trajectory_length=args.max_trajectory_length,
            action_space=args.action_space,
            observation_type=args.observation_type,
        )
        
        # Initialize environment
        env = DesktopEnv(
            path_to_vm=args.path_to_vm,
            action_space=args.action_space,
            provider_name=args.provider_name,
            headless=args.headless,
            screen_size=(args.screen_width, args.screen_height),
            client_password=args.client_password,
            require_a11y_tree=args.observation_type in ["a11y_tree", "screenshot_a11y_tree", "som"],
            region=args.region if args.provider_name == "aws" else None,
        )
        
        logger.info(f"Process {current_process().name} started.")
        
        while True:
            try:
                item = task_queue.get(timeout=5)
            except Exception:
                break
                
            if len(item) == 5:
                domain, example_id, run_num, task_dir, model_dir = item
            else:
                # Fallback for backward compatibility
                domain, example_id = item
                run_num = 1
                task_dir = os.path.join(args.result_dir, f"task_{example_id}")
                model_dir = os.path.join(task_dir, args.model)
            try:
                config_file = os.path.join(
                    args.test_config_base_dir, f"examples/{domain}/{example_id}.json"
                )
                with open(config_file, "r", encoding="utf-8") as f:
                    example = json.load(f)
                    
                logger.info(f"[{current_process().name}][Domain]: {domain}")
                logger.info(f"[{current_process().name}][Example ID]: {example_id}")
                logger.info(f"[{current_process().name}][Instruction]: {example['instruction']}")
                
                # Create result directory for this specific run using organized structure
                run_dir = os.path.join(model_dir, f"run_{run_num:02d}")
                example_result_dir = os.path.join(run_dir, "Trajectory and Screenshot")
                os.makedirs(example_result_dir, exist_ok=True)
                
                try:
                    lib_run_single.run_single_example(
                        agent,
                        env,
                        example,
                        args.max_steps,
                        example["instruction"],
                        args,
                        example_result_dir,
                        shared_scores,
                    )
                except Exception as e:
                    import traceback
                    logger.error(f"Exception in {current_process().name} {domain}/{example_id}: {e}")
                    logger.error(traceback.format_exc())
                    try:
                        env.controller.end_recording(
                            os.path.join(example_result_dir, "recording.mp4")
                        )
                    except Exception as rec_e:
                        logger.error(f"Failed to end recording: {rec_e}")
                    with open(os.path.join(example_result_dir, "traj.jsonl"), "a") as f:
                        f.write(
                            json.dumps(
                                {"Error": f"{domain}/{example_id} - {e}"}
                            )
                        )
                        f.write("\n")
            except Exception as e:
                logger.error(f"Task-level error in {current_process().name}: {e}")
                import traceback
                logger.error(traceback.format_exc())
    except Exception as e:
        logger.error(f"Process-level error in {current_process().name}: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        logger.info(f"{current_process().name} cleaning up environment...")
        try:
            if env:
                env.close()
                logger.info(f"{current_process().name} environment closed successfully")
        except Exception as e:
            logger.error(f"{current_process().name} error during environment cleanup: {e}")


def signal_handler(signum, frame):
    """Handle termination signals (SIGINT, SIGTERM) to gracefully shutdown environments."""
    global is_terminating, active_environments, processes
    
    # Avoid duplicate handling
    if is_terminating:
        return
    
    # Check if we should continue on interrupt
    if signum == signal.SIGINT and hasattr(args, 'continue_on_interrupt') and args.continue_on_interrupt:
        logger.info("Ctrl+C received. Continue running? (y/n): ")
        try:
            response = input().strip().lower()
            if response in ['y', 'yes']:
                logger.info("Continuing execution...")
                return
            else:
                logger.info("Shutting down as requested...")
        except (EOFError, KeyboardInterrupt):
            logger.info("Shutting down...")
    
    is_terminating = True
    logger.info(f"Received signal {signum}. Gracefully shutting down...")
    
    # Close all registered environments in the main process
    for env in active_environments:
        try:
            logger.info(f"Closing environment...")
            env.close()
            logger.info(f"Environment closed successfully")
        except Exception as e:
            logger.error(f"Error closing environment: {e}")
    
    # Send termination signal to all child processes first
    for p in processes:
        if p.is_alive():
            try:
                logger.info(f"Sending termination signal to process {p.name}...")
                p.terminate()
            except Exception as e:
                logger.error(f"Error terminating process {p.name}: {e}")


def calculate_pass_at_k_new_structure(task_dir, model, k=16):
    """Calculate pass@k for a specific task using new organized directory structure"""
    model_dir = os.path.join(task_dir, model)
    
    if not os.path.exists(model_dir):
        return 0.0
    
    # Count successful runs
    successful_runs = 0
    total_runs = 0
    
    for run_dir in os.listdir(model_dir):
        run_path = os.path.join(model_dir, run_dir)
        if os.path.isdir(run_path) and run_dir.startswith("run_"):
            total_runs += 1
            result_file = os.path.join(run_path, "Trajectory and Screenshot", "result.txt")
            if os.path.exists(result_file):
                try:
                    with open(result_file, "r") as f:
                        result = float(f.read().strip())
                        if result > 0.0:  # Consider any positive score as success
                            successful_runs += 1
                except:
                    pass
    
    if total_runs == 0:
        return 0.0
    
    pass_at_k = successful_runs / total_runs
    logger.info(f"Pass@k for task: {successful_runs}/{total_runs} = {pass_at_k:.3f}")
    return pass_at_k


def calculate_pass_at_k(result_dir, action_space, observation_type, model, domain, example_id, k=16):
    """Calculate pass@k for a specific task (legacy function for backward compatibility)"""
    task_dir = os.path.join(result_dir, action_space, observation_type, model, domain, example_id)
    
    if not os.path.exists(task_dir):
        return 0.0
    
    # Count successful runs
    successful_runs = 0
    total_runs = 0
    
    for run_dir in os.listdir(task_dir):
        run_path = os.path.join(task_dir, run_dir)
        if os.path.isdir(run_path) and run_dir.startswith("run_"):
            total_runs += 1
            result_file = os.path.join(run_path, "result.txt")
            if os.path.exists(result_file):
                try:
                    with open(result_file, "r") as f:
                        result = float(f.read().strip())
                        if result > 0.0:  # Consider any positive score as success
                            successful_runs += 1
                except:
                    pass
    
    if total_runs == 0:
        return 0.0
    
    pass_at_k = successful_runs / total_runs
    logger.info(f"Pass@k for {domain}/{example_id}: {successful_runs}/{total_runs} = {pass_at_k:.3f}")
    return pass_at_k


def test(args: argparse.Namespace, test_all_meta: dict) -> None:
    """Main test function that runs 16 parallel evaluations"""
    global processes
    logger.info("Args: %s", args)
    
    # Create tasks for each domain/example combination
    all_tasks = distribute_tasks(test_all_meta, args.specific_task)
    logger.info(f"Total tasks: {len(all_tasks)}")
    logger.info(f"Running specific task: {args.specific_task}")
    
    # For each task, we need to run it 16 times in parallel
    scores_snapshot = []
    with Manager() as manager:
        shared_scores = manager.list()
        
        for domain, example_id in all_tasks:
            logger.info(f"Starting {args.num_parallel_runs} parallel runs for task: {domain}/{example_id}")
            
            # Create organized directory structure
            task_dir, sft_dir, model_dir, annotator_dir = create_organized_directory_structure(
                args.result_dir, domain, example_id, args.model, args.num_parallel_runs
            )
            
            # Create task.json configuration file
            task_config = create_task_config(domain, example_id, args.model, 0.0, args.test_all_meta_path)
            task_config_file = os.path.join(task_dir, "task.json")
            with open(task_config_file, "w", encoding="utf-8") as f:
                json.dump(task_config, f, indent=2)
            
            # Create placeholder files for SFT and annotator sections
            create_placeholder_files(task_dir, sft_dir, annotator_dir)
            
            # Create task queue for this specific task
            task_queue = manager.Queue()
            
            # Add the same task multiple times to the queue
            for run_num in range(args.num_parallel_runs):
                task_queue.put((domain, example_id, run_num + 1, task_dir, model_dir))
            
            processes = []
            for i in range(args.num_parallel_runs):
                p = Process(
                    target=run_env_tasks,
                    args=(task_queue, args, shared_scores),
                    name=f"Run-{args.num_parallel_runs}-{i+1}"
                )
                p.daemon = True
                p.start()
                processes.append(p)
                logger.info(f"Started process {p.name} with PID {p.pid}")
            
            try:
                while True:
                    alive_count = 0
                    for idx, p in enumerate(processes):
                        if not p.is_alive():
                            logger.warning(f"Process {p.name} died, restarting...")
                            new_p = Process(
                                target=run_env_tasks,
                                args=(task_queue, args, shared_scores),
                                name=f"Run-{args.num_parallel_runs}-Restart-{idx+1}"
                            )
                            new_p.daemon = True
                            new_p.start()
                            processes[idx] = new_p
                            logger.info(f"Restarted process {new_p.name} with PID {new_p.pid}")
                        else:
                            alive_count += 1
                    if task_queue.empty():
                        logger.info("All runs for this task finished.")
                        break
                    if alive_count == 0:
                        logger.error("All processes died, exiting.")
                        break
                    time.sleep(5)
                
                for p in processes:
                    p.join()
                
                # Calculate pass@k for this task using new directory structure
                pass_at_k = calculate_pass_at_k_new_structure(
                    task_dir, 
                    args.model, 
                    args.num_parallel_runs
                )
                
                # Update task.json with final pass@k
                task_config_file = os.path.join(task_dir, "task.json")
                if os.path.exists(task_config_file):
                    with open(task_config_file, "r", encoding="utf-8") as f:
                        task_config = json.load(f)
                    task_config["model_pass_rate"] = pass_at_k
                    task_config["completed_at"] = datetime.datetime.now().isoformat()
                    with open(task_config_file, "w", encoding="utf-8") as f:
                        json.dump(task_config, f, indent=2)
                
                logger.info(f"Completed task {domain}/{example_id} with pass@k = {pass_at_k:.3f}")
                
            except KeyboardInterrupt:
                logger.info("Main process received KeyboardInterrupt. Initiating graceful shutdown...")
                raise
            except Exception as e:
                logger.error(f"Unexpected error while waiting for processes: {e}", exc_info=True)
                for p in processes:
                    if p.is_alive():
                        try:
                            logger.info(f"Terminating process {p.name} due to error...")
                            p.terminate()
                        except Exception as term_e:
                            logger.error(f"Error terminating process {p.name}: {term_e}")
                raise
        # Snapshot shared scores before Manager shuts down to avoid BrokenPipeError
        try:
            scores_snapshot = list(shared_scores)
        except Exception:
            scores_snapshot = []
    
    scores = scores_snapshot
    logger.info(f"Total evaluations completed: {len(scores)}")
    if scores:
        logger.info(f"Average score: {sum(scores) / len(scores):.3f}")


def get_unfinished(action_space, use_model, observation_type, result_dir, total_file_json):
    """Get unfinished tasks - modified to check for pass@k completion"""
    target_dir = os.path.join(result_dir, action_space, observation_type, use_model)

    if not os.path.exists(target_dir):
        return total_file_json

    finished = {}
    for domain in os.listdir(target_dir):
        finished[domain] = []
        domain_path = os.path.join(target_dir, domain)
        if os.path.isdir(domain_path):
            for example_id in os.listdir(domain_path):
                if example_id == "onboard":
                    continue
                example_path = os.path.join(domain_path, example_id)
                if os.path.isdir(example_path):
                    # Check if pass@k calculation is complete
                    pass_at_k_file = os.path.join(example_path, "pass_at_k.txt")
                    if os.path.exists(pass_at_k_file):
                        finished[domain].append(example_id)

    if not finished:
        return total_file_json

    for domain, examples in finished.items():
        if domain in total_file_json:
            total_file_json[domain] = [
                x for x in total_file_json[domain] if x not in examples
            ]

    return total_file_json


def create_organized_directory_structure(result_dir: str, domain: str, example_id: str, model: str, num_parallel_runs: int):
    """Create the organized directory structure for results"""
    # Base task directory
    task_dir = os.path.join(result_dir, f"task_{example_id}")
    
    # Create main directories
    sft_dir = os.path.join(task_dir, "SFT")
    model_dir = os.path.join(task_dir, model)  # Use the actual model name from args
    annotator_dir = os.path.join(task_dir, "Annotator Trajectory")
    
    # Create SFT subdirectories
    colab_dir = os.path.join(sft_dir, "Colab")
    trajectory_screenshot_dir = os.path.join(sft_dir, "Trajectory and Screenshot")
    
    # Create model run directories
    model_runs = []
    for i in range(1, num_parallel_runs + 1):
        run_dir = os.path.join(model_dir, f"run_{i:02d}")
        run_trajectory_dir = os.path.join(run_dir, "Trajectory and Screenshot")
        model_runs.append((run_dir, run_trajectory_dir))
    
    # Create annotator directories
    annotator_dirs = []
    for i in range(1, 4):  # 3 annotators
        annotator_run_dir = os.path.join(annotator_dir, f"annotator{i}")
        annotator_trajectory_dir = os.path.join(annotator_run_dir, "Trajectory and Screenshot")
        annotator_dirs.append((annotator_run_dir, annotator_trajectory_dir))
    
    # Create all directories
    directories_to_create = [
        task_dir,
        sft_dir,
        colab_dir,
        trajectory_screenshot_dir,
        model_dir
    ] + [run_dir for run_dir, _ in model_runs] + [run_trajectory_dir for _, run_trajectory_dir in model_runs]
    directories_to_create += [annotator_dir] + [annotator_run_dir for annotator_run_dir, _ in annotator_dirs] + [annotator_trajectory_dir for _, annotator_trajectory_dir in annotator_dirs]
    
    for directory in directories_to_create:
        os.makedirs(directory, exist_ok=True)
    
    return task_dir, sft_dir, model_dir, annotator_dir


def create_task_config(domain: str, example_id: str, model: str, pass_at_k: float, config_file: str):
    """Create OSWorld-compatible task.json configuration file"""
    task_config = {
        "task_id": example_id,
        "domain": domain,
        "model": model,
        "model_pass_rate": pass_at_k,
        "annotator_hints": [],
        "config_source": config_file,
        "created_at": datetime.datetime.now().isoformat()
    }
    return task_config


def create_placeholder_files(task_dir: str, sft_dir: str, annotator_dir: str):
    """Create placeholder files for SFT and annotator sections"""
    # Create SFT placeholder files
    evaluator_diff_file = os.path.join(sft_dir, "evaluator.diff")
    with open(evaluator_diff_file, "w") as f:
        f.write("# TODO: Add evaluator.diff content\n")
    
    colab_notebook_file = os.path.join(sft_dir, "Colab", "task_notebook.ipynb")
    with open(colab_notebook_file, "w") as f:
        f.write('{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 4}\n')
    
    # Create annotator placeholder files
    for i in range(1, 4):
        annotator_run_dir = os.path.join(annotator_dir, f"annotator{i}")
        evaluation_score_file = os.path.join(annotator_run_dir, "evaluation_score.txt")
        with open(evaluation_score_file, "w") as f:
            f.write("# TODO: Add annotator evaluation score\n")
        
        # Create placeholder trajectory file
        trajectory_file = os.path.join(annotator_run_dir, "Trajectory and Screenshot", "trajectory.jsonl")
        with open(trajectory_file, "w") as f:
            f.write('{"status": "placeholder", "message": "TODO: Add annotator trajectory data"}\n')


def list_available_tasks(test_all_meta: dict, max_examples_per_domain: int = 5):
    """List available tasks for reference"""
    print("\n=== Available Tasks ===")
    for domain, examples in test_all_meta.items():
        print(f"\n{domain}:")
        for i, example_id in enumerate(examples):
            if i < max_examples_per_domain:
                print(f"  {domain}/{example_id}")
            elif i == max_examples_per_domain:
                print(f"  ... and {len(examples) - max_examples_per_domain} more")
                break
    print(f"\nTotal: {sum(len(examples) for examples in test_all_meta.values())} tasks")
    print("Use --specific_task 'domain/example_id' to run a single task\n")


def get_result(action_space, use_model, observation_type, result_dir, total_file_json):
    """Get results with pass@k values"""
    target_dir = os.path.join(result_dir, action_space, observation_type, use_model)
    if not os.path.exists(target_dir):
        print("New experiment, no result yet.")
        return None

    all_pass_at_k = []

    for domain in os.listdir(target_dir):
        domain_path = os.path.join(target_dir, domain)
        if os.path.isdir(domain_path):
            for example_id in os.listdir(domain_path):
                example_path = os.path.join(domain_path, example_id)
                if os.path.isdir(example_path):
                    pass_at_k_file = os.path.join(example_path, "pass_at_k.txt")
                    if os.path.exists(pass_at_k_file):
                        try:
                            with open(pass_at_k_file, "r") as f:
                                pass_at_k = float(f.read().strip())
                                all_pass_at_k.append(pass_at_k)
                        except:
                            all_pass_at_k.append(0.0)

    if not all_pass_at_k:
        print("New experiment, no result yet.")
        return None
    else:
        avg_pass_at_k = sum(all_pass_at_k) / len(all_pass_at_k)
        print(f"Average Pass@k: {avg_pass_at_k:.3f} ({avg_pass_at_k*100:.1f}%)")
        print(f"Tasks with non-zero pass@k: {sum(1 for x in all_pass_at_k if x > 0)}/{len(all_pass_at_k)}")
        return all_pass_at_k


if __name__ == "__main__":
    ####### The complete version of the list of examples #######
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    
    # Register signal handlers for graceful termination
    if not args.disable_signal_handling:
        signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
        logger.info("Signal handling enabled - Ctrl+C will gracefully shutdown the script")
    else:
        logger.info("Signal handling disabled - Ctrl+C will be ignored")
    signal.signal(signal.SIGTERM, signal_handler)  # Handle termination signal
    
    try:
        # save args to json in result_dir/action_space/observation_type/model/args.json
        path_to_args = os.path.join(
            args.result_dir,
            args.action_space,
            args.observation_type,
            args.model,
            "args.json",
        )
        os.makedirs(os.path.dirname(path_to_args), exist_ok=True)
        with open(path_to_args, "w", encoding="utf-8") as f:
            json.dump(vars(args), f, indent=4)

        with open(args.test_all_meta_path, "r", encoding="utf-8") as f:
            test_all_meta = json.load(f)

        if args.domain != "all":
            test_all_meta = {args.domain: test_all_meta[args.domain]}
        
        # Show available tasks for reference
        list_available_tasks(test_all_meta)

        test_file_list = get_unfinished(
            args.action_space,
            args.model,
            args.observation_type,
            args.result_dir,
            test_all_meta,
        )
        left_info = ""
        for domain in test_file_list:
            left_info += f"{domain}: {len(test_file_list[domain])}\n"
        logger.info(f"Left tasks:\n{left_info}")

        get_result(
            args.action_space,
            args.model,
            args.observation_type,
            args.result_dir,
            test_all_meta,
        )
        test(args, test_file_list)
    except KeyboardInterrupt:
        logger.info("Main process received KeyboardInterrupt.")
        # Signal handler will take care of cleanup
    except Exception as e:
        logger.error(f"Unexpected error in main process: {e}", exc_info=True)
        # Also trigger cleanup for unhandled exceptions
        signal_handler(signal.SIGTERM, None)
    finally:
        # Final cleanup in case any environments or processes remain
        logger.info("Main process final cleanup...")
        for env in active_environments:
            if env is not None:
                try:
                    logger.info(f"Closing environment in final cleanup...")
                    env.close()
                    logger.info(f"Environment closed successfully in final cleanup")
                except Exception as e:
                    logger.error(f"Error during final environment cleanup: {e}")
        
        # First try gentle termination
        for p in processes:
            if p is not None and p.is_alive():
                try:
                    logger.info(f"Terminating process {p.name}...")
                    p.terminate()
                except Exception as e:
                    logger.error(f"Error terminating process: {e}")
        
        # Wait a moment for processes to terminate
        time.sleep(1)
        
        # Then force kill if needed
        for p in processes:
            if p is not None and p.is_alive():
                try:
                    logger.info(f"Force killing process {p.name}...")
                    os.kill(p.pid, signal.SIGKILL)
                    logger.info(f"Process {p.name} force killed")
                except Exception as e:
                    logger.error(f"Error force killing process: {e}")