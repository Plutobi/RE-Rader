"""Quick diagnostic — run this to find out exactly why the API is failing."""
import os
import sys

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("  dotenv loaded")
except ImportError:
    print("  dotenv not installed (that's fine)")

# Check key
key = os.environ.get("ANTHROPIC_API_KEY", "")
if not key:
    print("\n  ERROR: ANTHROPIC_API_KEY not set.")
    print("  Create a .env file in this folder with:")
    print("    ANTHROPIC_API_KEY=sk-ant-...")
    sys.exit(1)

print(f"  Key found: {key[:18]}...{key[-4:]}")

# Check anthropic package
try:
    import anthropic
    print(f"  anthropic SDK version: {anthropic.__version__}")
except ImportError:
    print("\n  ERROR: anthropic not installed. Run: pip install anthropic")
    sys.exit(1)

# Try the simplest possible API call
print("\n  Calling API...")
try:
    client = anthropic.Anthropic(api_key=key)
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=20,
        messages=[{"role": "user", "content": "Reply with the word OK only."}]
    )
    print(f"  SUCCESS: {response.content[0].text}")
except anthropic.AuthenticationError as e:
    print(f"\n  AUTH ERROR (invalid or revoked key): {e}")
except anthropic.NotFoundError as e:
    print(f"\n  404 NOT FOUND: {e}")
    print("\n  Possible causes:")
    print("  1. API key was revoked — regenerate at console.anthropic.com/settings/keys")
    print("  2. SDK version is too old — run: pip install --upgrade anthropic")
    print("  3. Network/proxy blocking the API endpoint")
except anthropic.PermissionDeniedError as e:
    print(f"\n  PERMISSION DENIED: {e}")
except Exception as e:
    print(f"\n  UNEXPECTED ERROR ({type(e).__name__}): {e}")
