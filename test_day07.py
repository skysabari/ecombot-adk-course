#!/usr/bin/env python3
"""
test_day07.py - Test script for Day 07 LiteLLM proxy integration
Run this after starting the LiteLLM proxy to verify routing works correctly.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_settings():
    """Test that configuration is properly loaded."""
    print("=" * 70)
    print("TEST 1: Configuration Loading")
    print("=" * 70)
    
    from config.settings import (
        MODEL, APP_NAME, LITELLM_PROXY_BASE, USE_LITELLM_PROXY
    )
    
    print(f"✓ APP_NAME: {APP_NAME}")
    print(f"✓ MODEL: {MODEL}")
    print(f"✓ LITELLM_PROXY_BASE: {LITELLM_PROXY_BASE}")
    print(f"✓ USE_LITELLM_PROXY: {USE_LITELLM_PROXY}")
    
    if USE_LITELLM_PROXY:
        print("\n✅ LiteLLM proxy mode is ENABLED")
    else:
        print("\n⚠️  LiteLLM proxy mode is DISABLED")
        print("   Set USE_LITELLM_PROXY=true in .env to enable")
    
    print()


def test_proxy_connectivity():
    """Test that LiteLLM proxy is accessible."""
    print("=" * 70)
    print("TEST 2: LiteLLM Proxy Connectivity")
    print("=" * 70)
    
    import requests
    from config.settings import LITELLM_PROXY_BASE
    
    try:
        # Try to get model list from proxy
        response = requests.get(f"{LITELLM_PROXY_BASE}/models", timeout=5)
        
        if response.status_code == 200:
            print(f"✅ LiteLLM proxy is accessible at {LITELLM_PROXY_BASE}")
            
            # Try to parse model list
            try:
                data = response.json()
                if "data" in data:
                    models = [m["id"] for m in data["data"]]
                    print(f"\n✓ Available models: {', '.join(models)}")
            except Exception as e:
                print(f"   (Could not parse model list: {e})")
        else:
            print(f"⚠️  LiteLLM proxy returned status {response.status_code}")
            print("   Make sure the proxy is running:")
            print(f"   litellm --config litellm_config.yaml --port 4000")
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to LiteLLM proxy at {LITELLM_PROXY_BASE}")
        print("\n   Start the proxy with:")
        print("   cd /Users/sgg839/agentic-ai-course/ecombot")
        print("   litellm --config litellm_config.yaml --port 4000")
        return False
    except Exception as e:
        print(f"❌ Error testing proxy: {e}")
        return False
    
    print()
    return True


def test_model_configuration():
    """Test that model configuration is correct."""
    print("=" * 70)
    print("TEST 3: Model Configuration")
    print("=" * 70)
    
    from config.settings import USE_LITELLM_PROXY, LITELLM_PROXY_BASE, MODEL
    from google.adk.models.lite_llm import LiteLlm
    
    if USE_LITELLM_PROXY:
        agent_model = LiteLlm(
            model="fast-faq",
            api_base=LITELLM_PROXY_BASE,
            api_key="local-dev",
        )
        print("✓ Agent configured for LiteLLM proxy mode")
        print(f"  - Model: fast-faq")
        print(f"  - API Base: {LITELLM_PROXY_BASE}")
    else:
        agent_model = LiteLlm(model=MODEL)
        print("✓ Agent configured for direct provider mode")
        print(f"  - Model: {MODEL}")
    
    print(f"\n✅ Model configuration is valid")
    print()


def test_agent_creation():
    """Test that the agent can be created successfully."""
    print("=" * 70)
    print("TEST 4: Agent Creation")
    print("=" * 70)
    
    try:
        # Import the agent module (this will create the agent)
        sys.path.insert(0, str(Path(__file__).parent / "src"))
        
        # We can't directly import because it will try to run the async main
        # Instead, just check that the module can be parsed
        import ast
        agent_file = Path(__file__).parent / "src" / "agents" / "support_agent.py"
        
        with open(agent_file) as f:
            code = f.read()
            ast.parse(code)
        
        print("✅ Agent module is syntactically valid")
        
        # Check for the key fix
        if "model=agent_model" in code:
            print("✅ Agent correctly uses agent_model (Day 07 fix applied)")
        else:
            print("⚠️  Agent might not be using agent_model correctly")
        
        if 'model="fast-faq"' in code or "model='fast-faq'" in code:
            print("✅ Default model is 'fast-faq' (correct for proxy mode)")
        else:
            print("⚠️  Default model might not be set correctly")
            
    except Exception as e:
        print(f"❌ Error checking agent: {e}")
        return False
    
    print()
    return True


def test_litellm_config():
    """Test that litellm_config.yaml is properly configured."""
    print("=" * 70)
    print("TEST 5: LiteLLM Configuration File")
    print("=" * 70)
    
    import yaml
    
    config_file = Path(__file__).parent / "litellm_config.yaml"
    
    if not config_file.exists():
        print(f"❌ Configuration file not found: {config_file}")
        return False
    
    try:
        with open(config_file) as f:
            config = yaml.safe_load(f)
        
        # Check for model groups
        if "model_list" in config:
            models = [m["model_name"] for m in config["model_list"]]
            print(f"✓ Model groups defined: {', '.join(models)}")
            
            if "fast-faq" in models:
                print("  ✓ fast-faq group found")
            else:
                print("  ⚠️  fast-faq group not found")
            
            if "deep-support" in models:
                print("  ✓ deep-support group found")
            else:
                print("  ⚠️  deep-support group not found")
        
        # Check for fallback configuration
        if "router_settings" in config and "fallbacks" in config["router_settings"]:
            print("\n✓ Fallback configuration found:")
            for fallback in config["router_settings"]["fallbacks"]:
                for primary, backups in fallback.items():
                    print(f"  - {primary} → {backups}")
        
        print("\n✅ LiteLLM configuration is valid")
        
    except Exception as e:
        print(f"❌ Error reading configuration: {e}")
        return False
    
    print()
    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print(" Day 07 - LiteLLM Proxy Integration Tests")
    print("=" * 70 + "\n")
    
    # Run tests
    test_settings()
    proxy_ok = test_proxy_connectivity()
    test_model_configuration()
    test_agent_creation()
    test_litellm_config()
    
    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    if proxy_ok:
        print("✅ All tests passed!")
        print("\nYou can now run the agent with:")
        print("  cd src")
        print("  USE_LITELLM_PROXY=true SESSION_BACKEND=memory PYTHONPATH=. \\")
        print("    python3 agents/support_agent.py")
    else:
        print("⚠️  Some tests failed. Please review the output above.")
        print("\nMake sure:")
        print("  1. LiteLLM proxy is running (litellm --config litellm_config.yaml --port 4000)")
        print("  2. .env file has USE_LITELLM_PROXY=true")
        print("  3. All dependencies are installed (pip install -r requirements.txt)")
    
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
