"""Central model configuration.

Decision (grill #1): gemini-2.0-flash via langchain-google-genai, temperature=0
for deterministic demos, max_retries=3 to ride out free-tier 429s. Centralising
the model here means swapping providers is a one-line change.
"""

import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

MODEL_NAME = "gemini-3.1-flash-lite-preview"  # 15 RPM free tier (vs 5 RPM on flash 2.5)

if not os.getenv("GOOGLE_API_KEY"):
    raise RuntimeError(
        "GOOGLE_API_KEY is not set. Copy .env.example to .env and add your "
        "free Gemini key from https://aistudio.google.com/apikey"
    )

# Shared chat model used by every agent and every structured-output call.
model = ChatGoogleGenerativeAI(
    model=MODEL_NAME,
    temperature=0,
    max_retries=3,
)
