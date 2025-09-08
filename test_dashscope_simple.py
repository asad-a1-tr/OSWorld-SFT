import os
from dotenv import load_dotenv
from dashscope import Generation
import dashscope

load_dotenv()  # Load environment variables from .env file
env_key = os.getenv('DASHSCOPE_API_KEY')
print(f"Environment DASHSCOPE_API_KEY: {env_key}")

if env_key and not env_key.startswith('sk-'):
    env_key = f"sk-{env_key}"
print(f"Using API key: {env_key}")

dashscope.api_key = env_key

def call_qwen_model():
    """
    Makes a minimal call to a Qwen model via DashScope.
    """

    response = Generation.call(
        model='qwen3-30b-a3b-instruct-2507',  # You can choose other Qwen models like 'qwen-plus', 'qwen-max'
        messages=[{'role': 'user', 'content': 'Hello, Qwen!'}],
        result_format='message'  # Ensure the result is returned as a message object
    )
    if response.status_code == 200:
        print("Response from Qwen model:")
        print(response.output.choices[0].message.content)
    else:
        print(f"Error calling Qwen model: {response.status_code} - {response.message}")
        print(response)



if __name__ == "__main__":
    call_qwen_model()