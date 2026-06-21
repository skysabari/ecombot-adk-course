"""
support_agent.py — Ecombot support agent (Day 05)
--------------------------------------------------
Wires together:
  - PostgreSQL-backed tools (order + product)
  - RAG retrieval tool (ChromaDB + OpenAI embeddings)
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

# ---------------------------------------------------------------------------
# RAG tool
# ---------------------------------------------------------------------------

def search_knowledge_base(query: str) -> dict:
    """
    Search the product catalogue and FAQ knowledge base for information
    relevant to the customer's question.

    Use this tool when the customer asks about:
    - Product specs, features, or compatibility
    - Shipping times or policies
    - Warranty coverage
    - Return or refund policies
    - General support or troubleshooting questions

    Do NOT use this tool for order status or cancellation — use the order tools instead.

    Args:
        query: The customer's question or topic to search for.

    Returns:
        A dict with the most relevant knowledge base excerpts.
    """
    try:
        from rag.retriever import retrieve
        chunks = retrieve(query, n_results=3)

        if not chunks:
            return {
            "found": False,
            "grounded": False,
            "fallback_message": (
                f"I searched our knowledge base for '{query}' but could not find "
                f"a confident match. This topic may not be covered in our current "
                f"documentation. For accurate information, please contact our "
                f"support team directly or visit our help centre."
            ),
        }

        return {
            "found": True,
            "grounded": True,
            "results": [
                {
                    "text": chunk["text"],
                    "type": chunk["metadata"].get("chunk_type", "faq"),
                    "score": chunk["score"],
                }
                for chunk in chunks
            ],
        }
    except Exception as exc:
        return {
            "found": False,
            "message": f"Knowledge base search unavailable: {exc}",
        }


# ---------------------------------------------------------------------------
# Instructions
# ---------------------------------------------------------------------------

_INSTRUCTION = (Path(__file__).parent.parent / 'instructions' / "support_instructions_v2.txt").read_text().strip()

_INSTRUCTION += """

## Grounding rules — IMPORTANT
- ALWAYS use search_knowledge_base before answering questions about product specs,
  shipping, warranty, returns, or general policies.
- Base your answer ONLY on what the tool returns. Do not add information from
  general knowledge that was not returned by the tool.
- If the tool returns no results, say: "I don't have that information available.
  Please contact our support team for help."
- Never invent product details, prices, delivery times, or policy details.

## Tool usage rules
- Use get_order_status or cancel_order for anything related to a specific order.
- Use get_product_details or check_stock for real-time product and stock data.
- Use search_knowledge_base for specs, policies, shipping rules, warranty, FAQ.
- If the customer asks a follow-up about the same order or product, reuse
  session state — do NOT call the tool again unless they give a new ID.
- If an order ID or product ID is needed and not provided, ask for it first.

## Hallucination rules — STRICTLY ENFORCED
- If search_knowledge_base returns grounded=False, relay the fallback_message
  word for word. Do not supplement it with your own knowledge.
- Never answer product, policy, or shipping questions from memory.
- If you are not certain the answer came from a tool result, say:
  "I don't have verified information on that. Please contact our support team."
- A helpful specific fallback is better than a confident wrong answer.

## Session state rules
- After a successful lookup the order ID and product ID are saved in session memory.
- Use them for follow-up questions like "cancel it" or "is it in stock".
- If session has no stored ID and customer asks a follow-up, ask for the reference.
"""

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

root_agent = LlmAgent(
    name=APP_NAME,
    model=LiteLlm(model=MODEL),
    description="A formal, professional e-commerce customer support assistant",
    instruction=_INSTRUCTION,
    tools=[
        get_order_status,
        cancel_order,
        get_product_details,
        check_stock,
        search_knowledge_base,
    ],
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

        record_turn(session_id, user_id, "user", prompt)

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=prompt)])
        ):
            if event.is_final_response():
                response_text = event.content.parts[0].text
                print(f"\nAgent: {response_text}\n")
                record_turn(session_id, user_id, "assistant", response_text)


if __name__ == "__main__":
    asyncio.run(main())