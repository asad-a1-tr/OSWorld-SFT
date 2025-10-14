import json
import os
import argparse
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage, SystemMessage
from dotenv import load_dotenv

def restructure_notebook(file_path, google_api_key):
    """
    Restructures the assistant reasoning in a Jupyter notebook using an LLM.

    Args:
        file_path (str): The path to the .ipynb file.
        google_api_key (str): The Google API key.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error reading or parsing notebook {file_path}: {e}")
        return

    user_instruction = None
    tool_calls = []
    assistant_cells = []

    for cell in notebook.get('cells', []):
        if cell.get('cell_type') == 'markdown':
            source = ''.join(cell.get('source', []))
            if source.startswith('**[user]**'):
                user_instruction = source.replace('**[user]**', '').strip()
            elif source.startswith('**[assistant]**'):
                assistant_cells.append(cell)
            elif source.startswith('**[tool_call]**'):
                try:
                    tool_call_json = source.replace('**[tool_call]**', '').strip()
                    # The tool call is wrapped in a json block
                    tool_call_json = tool_call_json.replace('```json', '').replace('```', '').strip()
                    tool_calls.append(json.loads(tool_call_json))
                except json.JSONDecodeError:
                    print(f"Warning: Could not parse tool call in {file_path}")


    if not user_instruction or not tool_calls or not assistant_cells:
        print(f"Skipping {file_path}: missing user instruction, tool calls, or assistant cells.")
        return

    print(f"Processing {file_path}...")

    prompt = f"""You are an expert in explaining complex automation tasks. Your goal is to provide detailed, step-by-step reasoning for a series of tool calls made to accomplish a user's instruction.

The user's instruction was: "{user_instruction}"

The following tool calls were executed in sequence:
"""
    for i, tool_call in enumerate(tool_calls):
        prompt += f"{i+1}. Tool: {tool_call.get('tool_name')}, Arguments: {tool_call.get('arguments')}\n"

    prompt += """
For each tool call, you must provide a detailed explanation that includes:
1.  **The specific action being taken.**
2.  **The immediate purpose of that action.**
3.  **How this action contributes to the overall goal of fulfilling the user's instruction.**
4.  **A concluding sentence that summarizes the efficiency or benefit of this step.**

Your response should be a numbered list of explanations, corresponding to the tool calls. Do not output any other text, just the numbered list. Each explanation should be a single, comprehensive paragraph. Do not include the command itself in the explanation.

Here is an example of the desired explanation style for a hypothetical action 'press the Windows key':

"To initiate this workflow, I will press the Windows key to open the system application menu. Accessing the application menu is the first step for launching the necessary applications—such as a file manager or code editor—that will be used to create and edit the notes.txt file in the specified code_workspace directory. This approach ensures I can efficiently navigate to the tools needed for file creation and content editing."

Now, generate the explanations for the provided tool calls.
"""

    try:
        llm = ChatGoogleGenerativeAI(model="gemini-pro-latest", google_api_key=google_api_key)
        messages = [
            SystemMessage(content="You are a helpful assistant that provides clear and concise explanations for automation tasks."),
            HumanMessage(content=prompt)
        ]
        response = llm.invoke(messages)
        new_reasoning = response.content.strip().split('\n')
    except Exception as e:
        print(f"Error calling Google API: {e}")
        return

    # Filter out empty strings from the split
    new_reasoning = [r.strip() for r in new_reasoning if r.strip()]

    if len(new_reasoning) != len(assistant_cells) -1: # one assistant cell is for DONE
        print(f"Warning: Number of generated reasoning steps ({len(new_reasoning)}) does not match number of assistant cells ({len(assistant_cells) - 1}) in {file_path}.")
        #return

    # Update assistant cells with new reasoning
    for i, reason in enumerate(new_reasoning):
        if i < len(assistant_cells):
            assistant_cells[i]['source'] = [f'**[assistant]**\n\n{reason}']

    # The last assistant cell is usually "DONE"
    if assistant_cells:
        assistant_cells[-1]['source'] = ['**[assistant]**\n\nDONE']


    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(notebook, f, indent=2, ensure_ascii=False)
        print(f"Successfully restructured {file_path}")
    except IOError as e:
        print(f"Error writing to notebook {file_path}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Restructure assistant reasoning in Jupyter notebooks.")
    parser.add_argument('path', type=str, help='Path to a .ipynb file or a directory containing .ipynb files.')
    args = parser.parse_args()

    load_dotenv()

    google_api_key = os.environ.get("GOOGLE_API_KEY")
    if not google_api_key:
        print("Error: GOOGLE_API_KEY environment variable not set.")
        return

    if os.path.isfile(args.path) and args.path.endswith('.ipynb'):
        restructure_notebook(args.path, google_api_key)
    elif os.path.isdir(args.path):
        for root, _, files in os.walk(args.path):
            for file in files:
                if file.endswith('.ipynb'):
                    file_path = os.path.join(root, file)
                    restructure_notebook(file_path, google_api_key)
    else:
        print(f"Error: Invalid path {args.path}. Please provide a valid .ipynb file or directory.")

if __name__ == "__main__":
    main()
