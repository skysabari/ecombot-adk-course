from pathlib import Path

import litellm
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from config.settings import APP_NAME, MODEL
from tools.order_tools import get_order_status
from services.session_service import make_runner, APP_NAME
import uuid
litellm.suppress_debug_info = True
load_dotenv()

_INSTRUCTION = (Path(__file__).parent.parent / "instructions" / "support_instructions_v2.txt").read_text().strip()

root_agent = LlmAgent(
    name=APP_NAME,
    model=LiteLlm(model=MODEL),
    description="A formal, professional e-commerce customer support assistant",
    instruction=_INSTRUCTION,
    tools=[get_order_status],
)

import asyncio
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

async def main():
    session_service = InMemorySessionService()
    runner, user_id, session_id = await make_runner(root_agent)

    print("Ecombot ready. Type 'q' to quit.\n")
    while True:
        prompt = input("You: ").strip()
        if prompt.lower() == "q":
            break

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=prompt)])
        ):
            if event.is_final_response():
                print(f"\nAgent: {event.content.parts[0].text}\n")

if __name__ == "__main__":
    asyncio.run(main())