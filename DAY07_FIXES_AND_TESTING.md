# Day 07 - LiteLLM Proxy Integration - Fixes and Testing Guide

## Issues Found and Fixed

### 1. Missing Dependencies
**Problem**: The requirements.txt was incomplete, missing critical packages like litellm, google-adk, etc.

**Fix**: Updated requirements.txt with all necessary dependencies:
```
google-adk>=2.1.0
litellm>=1.83.0
python-dotenv>=1.2.0
chromadb
psycopg2-binary
redis
requests
```

### 2. Agent Model Configuration Bug
**Problem**: In `src/agents/support_agent.py`, the code created an `agent_model` variable based on `USE_LITELLM_PROXY`, but then hardcoded `model=LiteLlm(model=MODEL)` when creating the `root_agent`, ignoring the proxy configuration entirely.

**Original Code** (lines 136-148):
```python
if USE_LITELLM_PROXY:
    agent_model = LiteLlm(
        model="openai/fast-faq",
        api_base=LITELLM_PROXY_BASE,
        api_key="local-dev",
    )
else:
    agent_model = LiteLlm(model=MODEL)
    
root_agent = LlmAgent(
    name=APP_NAME,
    model=LiteLlm(model=MODEL),  # BUG: Not using agent_model!
    ...
)
```

**Fixed Code**:
```python
if USE_LITELLM_PROXY:
    agent_model = LiteLlm(
        model="fast-faq",  # Fixed: removed "openai/" prefix
        api_base=LITELLM_PROXY_BASE,
        api_key="local-dev",
    )
else:
    agent_model = LiteLlm(model=MODEL)
    
root_agent = LlmAgent(
    name=APP_NAME,
    model=agent_model,  # Fixed: Use the configured agent_model
    ...
)
```

### 3. Incorrect Model Name
**Problem**: The code used `"openai/fast-faq"` but the litellm_config.yaml defines model groups as just `"fast-faq"` and `"deep-support"`.

**Fix**: Changed to `"fast-faq"` to match the configuration.

## Current Implementation Status

### ✅ Completed Tasks

#### Task 4.1 - Point eComBot at the LiteLLM proxy
- Configuration option `USE_LITELLM_PROXY` added in settings.py
- When enabled, agent uses `LITELLM_PROXY_BASE` (http://localhost:4000)
- Fallback to direct provider call when disabled

#### Task 4.2 - Define fast and deep model groups
- `litellm_config.yaml` defines two model groups:
  - **fast-faq**: Uses `gemini-2.5-flash-lite` (512 tokens, temp 0.3)
  - **deep-support**: Uses `gemini-2.5-flash` (2048 tokens, temp 0.5)
  - **general-fallback**: Backup model for resilience

#### Task 4.4 - Configure fallback behavior
- Fallback chain configured in litellm_config.yaml:
  - `fast-faq` → `deep-support`
  - `deep-support` → `general-fallback`
- 2 retries before fallback
- 15-second timeout

### 🔄 Partially Completed

#### Task 4.3 - Add routing hints
**Current State**: Agent always uses "fast-faq" route (hardcoded)

**What's Needed**: Implement dynamic route selection based on query complexity. Example approach:

```python
def classify_query_complexity(prompt: str) -> str:
    """Determine if query needs fast-faq or deep-support route."""
    complex_keywords = [
        "complaint", "multiple orders", "refund", "escalate",
        "complicated", "several items", "problem with"
    ]
    
    simple_keywords = [
        "where is", "order status", "tracking", "when will",
        "in stock", "price", "available"
    ]
    
    prompt_lower = prompt.lower()
    
    if any(kw in prompt_lower for kw in complex_keywords):
        return "deep-support"
    elif any(kw in prompt_lower for kw in simple_keywords):
        return "fast-faq"
    else:
        return "fast-faq"  # default to cheaper route
```

Then update the agent creation to use this classification.

## Testing Instructions

### Prerequisites
1. LiteLLM proxy must be running:
```bash
cd /Users/sgg839/agentic-ai-course/ecombot
source .env
litellm --config litellm_config.yaml --port 4000
```

2. Verify proxy is accessible:
```bash
curl http://localhost:4000/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "fast-faq",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### Run the Agent
```bash
cd /Users/sgg839/agentic-ai-course/ecombot/src
USE_LITELLM_PROXY=true SESSION_BACKEND=memory PYTHONPATH=. python3 agents/support_agent.py
```

### Test Scenarios

#### Test 1: Simple FAQ Query (should use fast-faq)
```
You: Where is my order?
```
Expected: Agent asks for order ID, then queries order status

#### Test 2: Product Query (should use fast-faq)
```
You: Do you have the UltraWidget Pro in stock?
```
Expected: Agent checks stock and provides information

#### Test 3: Complex Query (currently uses fast-faq, should use deep-support after Task 4.3)
```
You: I have a complaint about multiple orders that were delivered late and damaged
```
Expected: Agent handles complex multi-part customer complaint

### Verify Proxy Usage
Check the LiteLLM proxy logs to confirm:
1. Requests are hitting the proxy endpoint
2. The correct model group is being used
3. Fallback behavior works when primary model fails

## Next Steps for Full Day 07 Completion

### Task 4.3 Implementation (Priority: High)
Implement dynamic routing logic to choose between fast-faq and deep-support:

1. Add classification function (see example above)
2. Modify agent creation to be dynamic per-query
3. Or use ADKs's multi-agent approach (see day07 demo)

### Task 4.5 - Add Verification Tests
Create automated tests in `/tests/` folder:
- Test fast-faq route selection
- Test deep-support route selection  
- Test fallback behavior
- Test proxy vs direct mode

### Optional Enhancements (Stretch Goals)
1. Add logging for route decisions and latency (Stretch 5.1)
2. Experiment with different models in each group (Stretch 5.2)
3. Add metrics collection for cost/performance analysis
4. Implement A/B testing between routes

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'litellm'"
**Solution**: Install dependencies: `pip install -r requirements.txt`

### Issue: "Connection refused" when using proxy
**Solution**: Ensure LiteLLM proxy is running on port 4000

### Issue: Agent uses wrong model
**Solution**: 
1. Check `.env` has `USE_LITELLM_PROXY=true`
2. Verify `litellm_config.yaml` model names match code
3. Restart the agent after config changes

### Issue: Python version incompatibility
**Solution**: litellm requires Python 3.10-3.13, or use flexible version specs (>=)

## Configuration Files Reference

### .env
```bash
USE_LITELLM_PROXY=true
LITELLM_PROXY_BASE=http://localhost:4000
OPENROUTER_API_KEY=sk-or-v1-...
```

### litellm_config.yaml
- Defines model groups: fast-faq, deep-support, general-fallback
- Configures fallback chains
- Sets retry and timeout behavior

### src/config/settings.py
- Loads environment variables
- Provides USE_LITELLM_PROXY flag
- Sets LITELLM_PROXY_BASE URL

## Summary

Day 07 is now **functionally working** with these fixes:
- ✅ Dependencies installed
- ✅ Agent properly configured to use proxy
- ✅ Proxy running with model groups defined
- ✅ Fallback behavior configured
- ⚠️ Dynamic routing (Task 4.3) needs implementation for full completion

The agent successfully runs and routes through the LiteLLM proxy. The main remaining work is implementing intelligent route selection based on query complexity.
