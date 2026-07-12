"""Diagnose why the Anthropic API is returning 404."""
import urllib.request
import urllib.error
import json
import os
import ssl

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

key = os.environ.get("ANTHROPIC_API_KEY", "")
print(f"Key: {key[:20]}...{key[-4:]}" if key else "Key: NOT FOUND")

payload = json.dumps({
    "model": "claude-sonnet-4-6",
    "max_tokens": 5,
    "messages": [{"role": "user", "content": "hi"}]
}).encode()

req = urllib.request.Request(
    "https://api.anthropic.com/v1/messages",
    data=payload,
    headers={
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    },
    method="POST"
)

# Test 1: normal call
print("\nTest 1 — normal call:")
try:
    with urllib.request.urlopen(req) as r:
        print("SUCCESS:", r.read().decode())
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"HTTP {e.code}: {body[:300]}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

# Test 2: skip SSL verification
print("\nTest 2 — skip SSL verification:")
req2 = urllib.request.Request(
    "https://api.anthropic.com/v1/messages",
    data=payload,
    headers={
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    },
    method="POST"
)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
try:
    with urllib.request.urlopen(req2, context=ctx) as r:
        print("SUCCESS:", r.read().decode())
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"HTTP {e.code}: {body[:300]}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

# Test 4: SDK direct — no tools
print("\nTest 4 — Anthropic SDK (no tools):")
try:
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    r = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=10,
        messages=[{"role": "user", "content": "say hi"}]
    )
    print("SUCCESS:", r.content[0].text)
except Exception as e:
    print(f"FAILED ({type(e).__name__}): {e}")

# Test 5: SDK with explicit base_url
print("\nTest 5 — SDK with explicit base_url:")
try:
    import anthropic
    client = anthropic.Anthropic(
        api_key=key,
        base_url="https://api.anthropic.com",
        default_headers={"anthropic-version": "2023-06-01"}
    )
    r = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=10,
        messages=[{"role": "user", "content": "say hi"}]
    )
    print("SUCCESS:", r.content[0].text)
except Exception as e:
    print(f"FAILED ({type(e).__name__}): {e}")

# Test 3: try the EU endpoint
print("\nTest 3 — EU endpoint:")
req3 = urllib.request.Request(
    "https://api.eu.anthropic.com/v1/messages",
    data=payload,
    headers={
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    },
    method="POST"
)
try:
    with urllib.request.urlopen(req3) as r:
        print("SUCCESS:", r.read().decode())
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"HTTP {e.code}: {body[:300]}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
