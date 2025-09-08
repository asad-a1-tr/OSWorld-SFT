## Manual Data Collection for SFT

This document explains how to use the `run_manual.py` script to manually interact with the virtual environment and generate data for Supervised Fine-Tuning (SFT).

### 1. Purpose

The `run_manual.py` script allows a human to take the place of the AI agent. Instead of the model predicting actions, you will be prompted to type in the actions yourself. The script will execute your actions in the virtual machine and save a complete trajectory, including screenshots and the actions you took. This is ideal for creating high-quality, human-annotated datasets.

### 2. How It Works

1.  **Initialization**: The script starts a virtual machine using the provider you specify (e.g., VirtualBox).
2.  **Task Loading**: It loads a task from the `evaluation_examples` directory.
3.  **Instruction Display**: It prints the task instruction to your terminal (e.g., "Open the start menu and find the calculator").
4.  **Interactive Loop**:
    *   You will see the virtual machine's screen in the provider's GUI (the VirtualBox or VMware window).
    *   In your terminal, you will be prompted to enter a command.
    *   You type the command and press Enter.
    *   The script executes the command inside the VM.
    *   A "before" screenshot and the action are saved.
    *   The loop repeats until you finish the task.
5.  **Data Saving**: When you are done, a video recording, a `trajectory.jsonl` file containing all steps, and an **SFT Jupyter notebook** are saved to the `sft_results` directory.

### 3. Available Commands (Actions)

The actions you provide are strings of Python code that will be executed inside the VM. The primary library for controlling the GUI is `pyautogui`.

Here are the most common commands you will use:

| Command | Description | Example |
| :--- | :--- | :--- |
| `pg.click(x, y)` | Clicks the mouse at the specified (x, y) coordinates. | `pg.click(100, 250)` |
| `pg.doubleClick(x, y)`| Double-clicks the mouse. | `pg.doubleClick(500, 400)` |
| `pg.rightClick(x, y)` | Right-clicks the mouse. | `pg.rightClick(800, 600)` |
| `pg.moveTo(x, y)` | Moves the mouse cursor to the specified coordinates. | `pg.moveTo(300, 300)` |
| `pg.dragTo(x, y, duration=1)`| Drags the mouse from its current position to the new (x, y) coordinates over a duration. | `pg.dragTo(1000, 500, duration=1.5)` |
| `pg.typewrite("text")`| Types the given string of text. | `pg.typewrite("Hello, world!")` |
| `pg.press("key")` | Presses a single keyboard key. | `pg.press("enter")` |
| `pg.hotkey("key1", "key2")`| Presses multiple keys simultaneously (a keyboard shortcut). | `pg.hotkey("ctrl", "c")` |
| `time.sleep(seconds)` | Pauses the execution for a number of seconds. Useful for waiting for animations. | `time.sleep(2)` |

**Important Notes:**

*   The script automatically imports `pyautogui as pg` and `time`, so you can use `pg.` and `time.` prefixes directly.
*   The screen resolution is assumed to be **1920x1080**. All (x, y) coordinates should be based on this resolution.
*   There is a **2-second pause** after each action execution, plus an additional **2-second sleep** by default, for a total of 4 seconds between actions.

### 4. How to Run the Script

Open your terminal and use the following command structure. You must specify a provider.

```bash
# Make sure your virtual environment is activated
# Add VirtualBox/VMware to your PATH if it's not already
$env:PATH += ";C:\Program Files\Oracle\VirtualBox"

# Run the script
python run_manual.py --provider_name virtualbox
```

#### Command-Line Arguments

*   `--provider_name`: **(Required)** The virtualization provider to use. Options: `virtualbox`, `vmware`.
*   `--task_file`: (Optional) Path to a specific task file to run (e.g., `evaluation_examples/manual_task.json`). Use this when you want to run specific tasks instead of using `--domain`.
*   `--observation_type`: (Optional) The type of observation to capture. Defaults to `screenshot`.
    *   `screenshot`: Captures only a screenshot of the screen.
    *   `a11y_tree`: Captures only the accessibility tree as an XML file.
    *   `screenshot_a11y_tree`: Captures both the screenshot and the accessibility tree.
    *   `som`: Captures a Set-of-Mark (SoM) overlay on the screenshot.
*   `--path_to_vm`: (Optional) If you have an existing VM you want to use, provide the path to its `.vbox` or `.vmx` file. If not provided, the script will download one automatically.
*   `--domain`: (Optional) Specify a category of tasks to run, e.g., `--domain os`. If not provided, it will run all tasks. Not needed if using `--task_file`.
*   `--headless`: (Optional) Run the VM without a GUI window. **Do not use this for manual data collection**, as you need to see the screen.
*   `--result_dir`: (Optional) Change the directory where the SFT data is saved. Defaults to `./sft_results`.
*   `--sleep_after_execution`: (Optional) Additional time to sleep after each action. Defaults to `2.0` seconds.

### 5. The Data Collection Workflow

1.  **Start the script**: Run `python run_manual.py --provider_name virtualbox`.
2.  **Wait for VM**: The script will start the VM. This may take a few minutes the first time.
3.  **View Instruction**: The first task instruction will be printed in your terminal.
4.  **Perform Action**: Look at the VM window, decide on your action, and type the corresponding command (e.g., `pg.click(50, 50)`) into the terminal prompt.
5.  **Repeat**: Continue performing actions until the task is complete.
6.  **Finish Task**: When the task is done, type `done` and press Enter.
7.  **Next Task**: The script will load the next task and the process repeats.
8.  **Exit**: To stop the entire process, you can type `exit` at a prompt or use `Ctrl+C`.

## 6. Task Configuration and JSON Structure

### 6.1 Understanding Task Files

Tasks are defined in JSON files located in `evaluation_examples/examples/` organized by domain. Each task file defines what the AI agent (or human) should accomplish.

### 6.2 Task File Structure

Here's the complete structure of a task JSON file:

```json
{
  "id": "unique-task-identifier",
  "snapshot": "domain_name",
  "instruction": "Human-readable task description",
  "source": "source_reference_or_url",
  "trajectory": "trajectories/path/",
  "config": [
    {
      "type": "configuration_type",
      "parameters": {
        "key": "value"
      }
    }
  ],
  "related_apps": ["app1", "app2"],
  "evaluator": {
    "func": "evaluation_function",
    "result": {
      "type": "evaluation_type",
      "command": "evaluation_command"
    },
    "expected": {
      "type": "rule",
      "rules": {
        "include": ["required_strings"],
        "exclude": ["forbidden_strings"]
      }
    }
  },
  "proxy": false,
  "tag": "task_category"
}
```

### 6.3 Key-by-Key Explanation

#### Core Task Information

- **`id`**: Unique identifier for the task (usually UUID format)
- **`snapshot`**: VM snapshot to use. Available snapshots:
  - `os` - Basic Ubuntu desktop
  - `chrome` - Ubuntu with Chrome browser
  - `gimp` - Ubuntu with GIMP installed
  - `libreoffice_calc` - Ubuntu with LibreOffice Calc
  - `libreoffice_writer` - Ubuntu with LibreOffice Writer
  - `libreoffice_impress` - Ubuntu with LibreOffice Impress
  - `thunderbird` - Ubuntu with Thunderbird email client
  - `vlc` - Ubuntu with VLC media player
  - `vs_code` - Ubuntu with Visual Studio Code

- **`instruction`**: Clear, human-readable description of what needs to be accomplished
- **`source`**: Reference URL or "authors" if created by OSWorld team
- **`trajectory`**: Path where trajectory data should be stored
- **`related_apps`**: List of applications this task involves
- **`proxy`**: Boolean indicating if proxy is needed (usually false)
- **`tag`**: Category or type of task

#### Configuration Section (`config`)

The `config` array defines setup steps before the task begins. Common configuration types:

##### `launch` - Start an application
```json
{
  "type": "launch",
  "parameters": {
    "command": ["application-name", "--option1", "--option2"]
  }
}
```

##### `download` - Download files needed for the task
```json
{
  "type": "download",
  "parameters": {
    "files": [
      {
        "url": "https://example.com/file.jpg",
        "path": "/home/user/Desktop/file.jpg"
      }
    ]
  }
}
```

##### `open` - Open a file with default application
```json
{
  "type": "open",
  "parameters": {
    "path": "/home/user/document.docx"
  }
}
```

##### `command` - Execute shell command
```json
{
  "type": "command",
  "parameters": {
    "command": ["mkdir", "-p", "/home/user/newfolder"]
  }
}
```

##### `execute` - Execute Python code
```json
{
  "type": "execute",
  "parameters": {
    "command": [
      "python", "-c",
      "import pyautogui; pyautogui.click(960, 540);"
    ]
  }
}
```

#### Evaluator Section

The `evaluator` defines how to check if the task was completed successfully.

##### Common Evaluation Functions

- **`check_include_exclude`**: Check if output contains/doesn't contain specific strings
- **`pixel_match`**: Compare pixel values in screenshots
- **`file_exist`**: Check if specific files exist
- **`vm_command_line`**: Run shell command and check output

##### Evaluation Result Types

- **`vm_command_line`**: Execute shell command in VM
```json
"result": {
  "type": "vm_command_line",
  "command": "ls -la /home/user/Desktop/"
}
```

- **`vm_file_content`**: Check file contents
```json
"result": {
  "type": "vm_file_content",
  "path": "/home/user/output.txt"
}
```

- **`vm_screenshot`**: Analyze screenshot
```json
"result": {
  "type": "vm_screenshot",
  "path": "final_screenshot.png"
}
```

##### Expected Results

- **`rule`**: Define inclusion/exclusion rules
```json
"expected": {
  "type": "rule",
  "rules": {
    "include": ["SUCCESS", "completed"],
    "exclude": ["ERROR", "failed"]
  }
}
```

### 6.4 Domain-Specific Examples

#### OS Domain Task
```json
{
  "id": "system-info-task",
  "snapshot": "os",
  "instruction": "Using gedit text editor, create a text file containing basic system information (hostname, current date, and system uptime) and save it as 'system_info.txt'",
  "source": "custom_task",
  "config": [],
  "related_apps": ["os"],
  "evaluator": {
    "func": "check_include_exclude",
    "result": {
      "type": "vm_command_line",
      "command": "if [ -f ~/system_info.txt ]; then echo 'FILE_EXISTS'; cat ~/system_info.txt; else echo 'FILE_NOT_FOUND'; fi"
    },
    "expected": {
      "type": "rule",
      "rules": {
        "include": ["FILE_EXISTS", "hostname", "uptime"],
        "exclude": ["FILE_NOT_FOUND"]
      }
    }
  }
}
```

#### Chrome Domain Task
```json
{
  "id": "chrome-search-task",
  "snapshot": "chrome",
  "instruction": "Make Bing the default search engine in Chrome",
  "config": [
    {
      "type": "launch",
      "parameters": {
        "command": ["google-chrome", "--remote-debugging-port=1337"]
      }
    }
  ],
  "related_apps": ["chrome"],
  "evaluator": {
    "func": "check_include_exclude",
    "result": {
      "type": "vm_command_line",
      "command": "grep -r 'bing' ~/.config/google-chrome/ || echo 'NOT_FOUND'"
    },
    "expected": {
      "type": "rule",
      "rules": {
        "include": ["bing"],
        "exclude": ["NOT_FOUND"]
      }
    }
  }
}
```

#### GIMP Domain Task
```json
{
  "id": "gimp-brightness-task",
  "snapshot": "gimp",
  "instruction": "Reduce the brightness of the loaded image",
  "config": [
    {
      "type": "download",
      "parameters": {
        "files": [
          {
            "url": "https://example.com/photo.jpg",
            "path": "/home/user/Desktop/photo.jpg"
          }
        ]
      }
    },
    {
      "type": "launch",
      "parameters": {
        "command": ["gimp", "/home/user/Desktop/photo.jpg"]
      }
    }
  ],
  "related_apps": ["gimp"],
  "evaluator": {
    "func": "pixel_match",
    "result": {
      "type": "vm_screenshot",
      "path": "final_result.png"
    },
    "expected": {
      "type": "pixel_threshold",
      "threshold": 0.8
    }
  }
}
```

### 6.5 Creating Custom Task Files

1. **Create task JSON file** in appropriate domain folder:
   ```
   evaluation_examples/examples/[domain]/your-task-id.json
   ```

2. **Add task ID to test configuration**:
   Edit `evaluation_examples/test_all.json` to include your task:
   ```json
   {
     "os": ["existing-task", "your-task-id"],
     "chrome": ["existing-chrome-task"]
   }
   ```

3. **Create custom test file** for specific tasks:
   ```json
   {
     "os": ["your-task-id"]
   }
   ```
   Save as `evaluation_examples/my_custom_tasks.json`

4. **Run your custom tasks**:
   ```bash
   python run_manual.py --provider_name virtualbox --task_file evaluation_examples/my_custom_tasks.json
   ```

### 6.6 Test Configuration Files

Test configuration files (like `test_all.json`) define which tasks to run:

```json
{
  "domain1": ["task-id-1", "task-id-2"],
  "domain2": ["task-id-3", "task-id-4"]
}
```

Available test files:
- `test_all.json` - All 369 tasks across all domains
- `test_small.json` - Small subset for quick testing
- `test_nogdrive.json` - Tasks excluding Google Drive dependencies
- `manual_task.json` - Single custom task for manual testing

### 6.7 Output Data Structure

After running manual data collection, you'll get:

```
sft_results/
└── domain/
    └── task-id/
        ├── trajectory.jsonl          # Step-by-step actions
        ├── recording.mp4             # Screen recording
        ├── step_0_before.png         # Screenshots
        ├── step_0_before.xml         # Accessibility trees
        ├── osw.manual.task-id.ipynb  # SFT Jupyter Notebook
        └── ...
```

The **SFT Jupyter Notebook** contains:
- **Metadata cell** with complete task configuration
- **User cell** with task instruction
- **Assistant cells** with reasoning for each step
- **Tool call cells** with PyAutoGUI commands
- **Tool output cells** with screenshot and accessibility tree references

This comprehensive guide covers all aspects of task configuration, from understanding existing tasks to creating your own custom evaluations.
