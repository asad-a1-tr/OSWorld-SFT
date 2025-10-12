# How to Restructure Notebook Reasoning

This document outlines the steps to use the `restructure_notebook.py` script to automatically rewrite and improve the assistant's reasoning within Jupyter notebooks.

## Purpose

The `restructure_notebook.py` script processes one or more `.ipynb` files. For each notebook, it:
1.  Reads the user's instruction and the sequence of tool calls.
2.  Uses the OpenAI API to generate a detailed, step-by-step explanation for the actions taken.
3.  Replaces the old, generic assistant reasoning with the new, high-quality explanations.

## Prerequisites

Before running the script, ensure you have the following set up:

1.  **Python:** Make sure you have Python 3 installed on your system.

2.  **Dependencies:** Install the required Python libraries using pip and the `requirements.txt` file.
    ```bash
    pip install -r requirements.txt
    ```

3.  **OpenAI API Key:** Create a file named `.env` in the root of the project directory and add your OpenAI API key to it, like this:
    ```
    OPENAI_API_KEY='your_api_key_here'
    ```
    The script will automatically load this key.

## How to Run

You can run the script on a single notebook file or an entire directory containing multiple notebooks.

### Running on a Directory

To process all `.ipynb` files within a directory (and its subdirectories), provide the directory path as an argument.

**Command:**
```bash
python restructure_notebook.py <path_to_directory>
```

**Example:**
To restructure all notebooks in the `colab_rewrite` directory:
```bash
python restructure_notebook.py colab_rewrite
```

### Running on a Single File

To process a single `.ipynb` file, provide the file path as an argument.

**Command:**
```bash
python restructure_notebook.py <path_to_notebook.ipynb>
```

**Example:**
```bash
python restructure_notebook.py colab_rewrite/sft/osw.manual_task.1759970264.ipynb
```
