import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load env vars
config_path = Path.home() / ".config" / "kpaperflux" / ".env"
load_dotenv(config_path)

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("No API Key found")
    sys.exit(1)

client = genai.Client(api_key=api_key)
model_name = 'gemini-2.0-flash-lite-preview-02-05'

print(f"Testing Model: {model_name}")

try:
    response = client.models.generate_content(
        model=model_name,
        contents="Hello, are you working?"
    )
    print("Success!")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"API Error: {e}")
    sys.exit(1)
