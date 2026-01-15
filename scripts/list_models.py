import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai

# Load env vars
config_path = Path.home() / ".config" / "kpaperflux" / ".env"
load_dotenv(config_path)

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("No API Key found")
    exit(1)

client = genai.Client(api_key=api_key)
try:
    print("Listing models...")
    # GenAI SDK list_models might be client.models.list()
    for m in client.models.list():
        print(f"Model: {m.name}")
        # print(f"Supported methods: {m.supported_generation_methods}")
except Exception as e:
    print(f"Error: {e}")
