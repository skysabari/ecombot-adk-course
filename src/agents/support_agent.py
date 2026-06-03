
from pathlib import Path

import litellm
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from config.settings import APP_NAME, MODEL

litellm.suppress_debug_info = True
load_dotenv()

# _INSTRUCTION = (Path(__file__).parent / "instruction.txt").read_text().strip()

root_agent = LlmAgent(
    name=APP_NAME,
    model=LiteLlm(model=MODEL),
    description="A formal, professional e-commerce customer support assistant",
    instruction=(
        "You are an e-commerce customer support assistant. "
        "Only help with orders, returns, refunds, shipping, and payments. "
        "Always respond in a formal and professional tone."
    ),
)
