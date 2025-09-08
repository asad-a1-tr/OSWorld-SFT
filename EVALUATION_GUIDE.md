# OSWorld Qwen3 Evaluation Guide

## Quick Start

### 1. Set API Key
```bash
export DASHSCOPE_API_KEY="your-qwen-api-key-here"
```

### 2. Run Evaluation
```bash
python run_multienv_qwen25vl.py \
    --provider_name docker \
    --headless \
    --observation_type screenshot \
    --model qwen3-coder-480b-a35b-instruct \
    --max_steps 15 \
    --num_envs 1 \
    --result_dir ./results
```

### 3. View Results
```bash
python show_result.py
```

## Available Qwen3 Models

### Model Options:
- `qwen3-coder-480b-a35b-instruct` (Coding optimized)
- `qwen3-235b-a22b-instruct-2507` (General purpose)
- `qwen3-30b-a3b-instruct-2507` (Smaller, faster)

## Current Task Configuration

### System Info Task (`system-info-task`)
**Task**: Create system information file using gedit
**File**: `evaluation_examples/examples/os/system-info-task.json`
**Requirements**:
- Use gedit text editor
- Create file named `system_info.txt`
- Include hostname information
- Include system uptime information
- Save in home directory (`~/system_info.txt`)

**Test Configuration**: `evaluation_examples/test_all.json`
```json
{
  "os": ["system-info-task"]
}
```

## Command Reference

### Basic Evaluation
```bash
python run_multienv_qwen25vl.py \
    --provider_name docker \
    --headless \
    --model MODEL_NAME \
    --result_dir ./results
```

### With Custom Parameters
```bash
python run_multienv_qwen25vl.py \
    --provider_name docker \
    --headless \
    --observation_type screenshot \
    --model MODEL_NAME \
    --max_steps 20 \
    --num_envs 1 \
    --temperature 0.3 \
    --top_p 0.8 \
    --max_tokens 2000 \
    --result_dir ./results
```

### Multiple Environments (Parallel)
```bash
python run_multienv_qwen25vl.py \
    --provider_name docker \
    --headless \
    --model MODEL_NAME \
    --num_envs 3 \
    --result_dir ./results
```

## Results Location

Results are saved in: `./results/pyautogui/screenshot/MODEL_NAME/os/system-info-task/`

**Contains**:
- `result.txt` - Final score (1.0 = success, 0.0 = failure)
- `traj.jsonl` - Step-by-step actions taken
- `step_*.png` - Screenshots at each step
- `recording.mp4` - Video recording of the evaluation
- `runtime.log` - Detailed execution logs

## Environment Variables

### Required
```bash
export DASHSCOPE_API_KEY="your-api-key"
```

### Optional
```bash
export DASHSCOPE_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
```

### Using .env File
Create `.env` file in project root:
```bash
DASHSCOPE_API_KEY=your-api-key-here
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

## Docker Requirements

### Prerequisites
1. Docker installed and running
2. KVM support (check with: `egrep -c '(vmx|svm)' /proc/cpuinfo`)
3. Sufficient disk space for VM images

### First Run
- VM images download automatically (~10.8GB)
- Allow extra time for initial setup and VM image download
- Download and unzipping process can take 15-30 minutes depending on connection speed

## Troubleshooting

### Setup Requirements (WSL/Linux)
Before running the evaluation, ensure you have the proper environment setup:

1. **Use conda environment**: The evaluation must run in the `osworld` conda environment
   ```bash
   source /home/asad/miniconda3/etc/profile.d/conda.sh
   conda activate osworld
   ```

2. **Set required environment variables**: 
   ```bash
   export DASHSCOPE_API_KEY="your-qwen-api-key-here"
   export AWS_REGION="us-east-1"
   export AWS_SUBNET_ID="dummy"
   export AWS_SECURITY_GROUP_ID="dummy"
   ```

3. **Complete setup command**:
   ```bash
   source /home/asad/miniconda3/etc/profile.d/conda.sh && \
   conda activate osworld && \
   export DASHSCOPE_API_KEY="your-api-key" && \
   export AWS_REGION="us-east-1" && \
   export AWS_SUBNET_ID="dummy" && \
   export AWS_SECURITY_GROUP_ID="dummy" && \
   python run_multienv_qwen25vl.py --provider_name docker --headless --observation_type screenshot --model qwen3-coder-480b-a35b-instruct --max_steps 15 --num_envs 1 --result_dir ./results
   ```

### Common Issues
1. **Docker not running**: Start Docker service
2. **Permission denied**: Add user to docker group
3. **KVM not supported**: Use `--provider_name virtualbox` or `vmware`
4. **API key invalid**: Check DASHSCOPE_API_KEY environment variable
5. **Missing DASHSCOPE_API_KEY**: Set the environment variable before running
6. **Missing AWS environment variables**: Set AWS_REGION, AWS_SUBNET_ID, and AWS_SECURITY_GROUP_ID (can use dummy values for Docker provider)
7. **Wrong Python environment**: Must activate the `osworld` conda environment
8. **First run downloads**: Initial run downloads ~10.8GB VM image - allow extra time

### Cleanup Docker Containers
```bash
docker stop $(docker ps -q) && docker rm $(docker ps -a -q)
```

### View Logs
```bash
# Check logs directory
ls logs/

# View latest log
tail -f logs/normal-*.log
```

## Restoring Full Test Suite

To restore all original tests:
```bash
cp evaluation_examples/test_all_backup.json evaluation_examples/test_all.json
```

## Custom Task Development

### Adding New Tasks
1. Create JSON file in `evaluation_examples/examples/DOMAIN/`
2. Add task ID to `evaluation_examples/test_all.json`
3. Define proper evaluator configuration

### Task Format
```json
{
  "id": "task-id",
  "snapshot": "os",
  "instruction": "Task description",
  "config": [{"type": "launch", "parameters": {"command": ["app"]}}],
  "related_apps": ["app1", "app2"],
  "evaluator": {
    "func": "check_include_exclude",
    "result": {"type": "vm_command_line", "command": "test_command"},
    "expected": {"type": "rule", "rules": {"include": ["success"], "exclude": ["error"]}}
  }
}
```

## Performance Tips

1. **Single environment** for debugging: `--num_envs 1`
2. **Lower temperature** for deterministic results: `--temperature 0.1`
3. **More steps** for complex tasks: `--max_steps 30`
4. **Headless mode** for server deployment: `--headless`