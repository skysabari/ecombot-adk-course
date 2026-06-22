import os

MODEL = "openrouter/google/gemini-2.5-flash"
APP_NAME = "EcomBot"
LITELLM_PROXY_BASE = os.getenv("LITELLM_PROXY_BASE", "http://localhost:4000")
USE_LITELLM_PROXY = os.getenv("USE_LITELLM_PROXY", "false").lower() == "true"   