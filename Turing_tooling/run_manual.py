import argparse
import datetime
import json
import logging
import os
import sys
from pathlib import Path
from tqdm import tqdm

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def _load_manual_runner():
    """Resolve the manual runner without triggering heavy imports during CLI help."""
    if __package__:
        from .sft_utils.lib_run_manual import run_single_example_manual
        return run_single_example_manual
    try:
        from Turing_tooling.sft_utils.lib_run_manual import run_single_example_manual
    except ImportError:
        from sft_utils.lib_run_manual import run_single_example_manual
    return run_single_example_manual

def config() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manually run tasks to generate SFT data."
    )

    # environment config
    parser.add_argument("--path_to_vm", type=str, default=None, help="Path to the VM file (.vmx or .vbox)")
    parser.add_argument(
        "--headless", action="store_true", help="Run in headless mode (no GUI for the VM)"
    )
    parser.add_argument(
        "--action_space", type=str, default="pyautogui", help="Action type, defaults to pyautogui"
    )
    # parser.add_argument(
    #     "--observation_type",
    #     choices=["screenshot", "a11y_tree", "screenshot_a11y_tree", "som"],
    #     default="screenshot",
    #     help="Observation type",
    # )
    parser.add_argument("--sleep_after_execution", type=float, default=1.0, help="Time to sleep after each action")
    parser.add_argument("--max_steps", type=int, default=150, help="Maximum number of steps per task")

    # example config
    parser.add_argument(
        "--test_config_base_dir", type=str, default="evaluation_examples", help="Base directory for task configurations"
    )
    parser.add_argument("--task_file", type=str, help="Path to a specific task file to run")
    parser.add_argument("--domain", type=str, default="all", help="Domain to run tasks from (e.g., 'os', 'web', or 'all')")
    parser.add_argument(
        "--test_all_meta_path", type=str, default="evaluation_examples/test_all.json", help="Path to the meta file listing all tasks"
    )

    # logging related
    parser.add_argument("--result_dir", type=str, default="./sft_results", help="Directory to save the SFT data")
    parser.add_argument("--log_level", type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], 
                       default='INFO', help="Set the logging level")
    
    # provider config
    parser.add_argument(
        "--provider_name", type=str, default="virtualbox", choices=["virtualbox", "vmware", "docker", "aws", "azure"], help="Provider name"
    )
    parser.add_argument(
        "--client_password", type=str, default="", help="Client password for the VM"
    )
    parser.add_argument(
        "--screen_width", type=int, default=1920, help="Screen width"
    )
    parser.add_argument(
        "--screen_height", type=int, default=1080, help="Screen height"
    )
    args = parser.parse_args()
    return args

def main():
    args = config()

    manual_runner = _load_manual_runner()
    from desktop_env.desktop_env import DesktopEnv

    # Setup logging
    datetime_str = datetime.datetime.now().strftime("%Y%m%d@%H%M%S")
    log_dir = os.path.join(args.result_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger("desktopenv.manual_run")
    log_level = getattr(logging, args.log_level.upper())
    logger.setLevel(log_level)

    file_handler = logging.FileHandler(os.path.join(log_dir, f"manual-{datetime_str}.log"), encoding="utf-8")
    stdout_handler = logging.StreamHandler(sys.stdout)
    
    formatter = logging.Formatter(
        fmt="\x1b[1;33m[%(asctime)s \x1b[31m%(levelname)s \x1b[32m%(module)s/%(lineno)d\x1b[1;33m] \x1b[0m%(message)s"
    )
    file_handler.setFormatter(formatter)
    stdout_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(stdout_handler)

    # Initialize Environment
    env = DesktopEnv(
        path_to_vm=args.path_to_vm,
        action_space=args.action_space,
        provider_name=args.provider_name,
        headless=args.headless,
        screen_size=(args.screen_width, args.screen_height),
        client_password=args.client_password,
        require_a11y_tree=False,
    )

    # Load tasks
    if args.task_file:
        # Use specific task file
        with open(args.task_file, "r", encoding="utf-8") as f:
            task_meta = json.load(f)
            # Convert single task file format to match meta format
            test_all_meta = {}
            for domain, task_list in task_meta.items():
                test_all_meta[domain] = []
                for task in task_list:
                    # Remove .json extension if present in task name
                    task = task.replace(".json", "")
                    test_all_meta[domain].append(task)
    else:
        # Load from meta file
        with open(args.test_all_meta_path, "r", encoding="utf-8") as f:
            test_all_meta = json.load(f)

        if args.domain != "all":
            test_all_meta = {args.domain: test_all_meta.get(args.domain, [])}

    # Run tasks
    for domain, examples in test_all_meta.items():
        for example_id in tqdm(examples, desc=f"Domain {domain}"):
            base_examples = Path(args.test_config_base_dir) / "examples"
            primary_path = base_examples / domain / f"{example_id}.json"

            if primary_path.exists():
                resolved_config_path = primary_path
            else:
                fallback_domain = domain.replace("-", "_")
                fallback_example = example_id.replace("-", "_")
                fallback_path = base_examples / fallback_domain / f"{fallback_example}.json"
                if fallback_path.exists():
                    resolved_config_path = fallback_path
                    logger.debug(
                        "Resolved path mismatch: using %s instead of %s",
                        fallback_path,
                        primary_path,
                    )
                else:
                    raise FileNotFoundError(
                        f"Could not locate config for domain={domain!r} example={example_id!r}. "
                        f"Checked {primary_path} and {fallback_path}."
                    )

            with open(resolved_config_path, "r", encoding="utf-8") as f:
                example = json.load(f)

            example_result_dir = os.path.join(
                args.result_dir, domain, example_id
            )
            os.makedirs(example_result_dir, exist_ok=True)

            logger.info(f"Starting task: {example_id} - {example['instruction']}")
            
            manual_runner(
                env=env,
                config=example,
                max_steps=args.max_steps,
                instruction=example["instruction"],
                args=args,
                result_dir=example_result_dir,
            )

    logger.info("All tasks completed. Closing environment.")
    env.close()

if __name__ == "__main__":
    main()
# Minor formatting update for review






