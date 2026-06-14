"""
support_agent.py — Ecombot support agent (Day 04)
--------------------------------------------------
Wires together:
  - PostgreSQL-backed tools (order + product)
  - Redis session persistence
  - PostgreSQL conversation history
"""

import asyncio
from pathlib import Path

import litellm
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

load_dotenv(Path(__file__).parent.parent.parent / ".env")

from config.settings import APP_NAME, MODEL
from tools.order_tools import get_order_status, cancel_order
from tools.product_tools import get_product_details, check_stock
from services.history_service import record_turn

litellm.suppress_debug_info = True

_INSTRUCTION = (Path(__file__).parent / "support_instructions_v2.txt").read_text().strip()

_INSTRUCTION += """

## Tool usage rules
- ALWAYS call get_order_status or get_product_details when the customer asks for details.
- NEVER invent or guess order status, product price, or stock levels.
- If the customer asks a follow-up about the same order or product, reuse the session state — do NOT call the tool again unless they give a new ID.
- If the customer has not provided an order ID or product ID, ask for it before calling any tool.
- If a tool returns an error, relay it clearly and offer to help further.

## Session state rules
- After a successful lookup, the order ID and product ID are saved in session memory.
- Use them for follow-up questions like "cancel it" or "is it in stock" without asking again.
- If the session has no stored ID and the customer asks a follow-up, politely ask them to provide the reference.
"""

root_agent = LlmAgent(
    name=APP_NAME,
    model=LiteLlm(model=MODEL),
    description="A formal, professional e-commerce customer support assistant",
    instruction=_INSTRUCTION,
    tools=[get_order_status, cancel_order, get_product_details, check_stock],
)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def main():
    from services.session_service import make_runner

    runner, user_id, session_id = await make_runner(root_agent)
    print(f"Ecombot ready. [user: {user_id} | session: {session_id}]")
    print("Type 'q' to quit, 'history' to view conversation history.\n")

    while True:
        prompt = input("You: ").strip()

        if not prompt:
            continue

        if prompt.lower() == "q":
            break

        if prompt.lower() == "history":
            from services.history_service import print_history
            print_history(session_id)
            continue

        # Record user turn
        record_turn(session_id, user_id, "user", prompt)

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=prompt)])
        ):
            if event.is_final_response():
                response_text = event.content.parts[0].text
                print(f"\nAgent: {response_text}\n")

                # Record assistant turn
                record_turn(session_id, user_id, "assistant", response_text)


if __name__ == "__main__":
    asyncio.run(main())