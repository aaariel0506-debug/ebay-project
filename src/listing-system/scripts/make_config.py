#!/usr/bin/env python3
"""
Generate config.json from environment variables.
For local runs: uses hardcoded credentials.
For CI/CD: uses environment variables (EBAY_APP_ID, EBAY_APP_SECRET, EBAY_REFRESH_TOKEN).
"""
import json, os, base64, urllib.request

CLIENT_ID = os.environ.get("EBAY_APP_ID") or "Masakiyo-orderinf-PRD-0bf27a730-27144d91"
CLIENT_SECRET = os.environ.get("EBAY_APP_SECRET") or "PRD-bf1f19d47086-ca52-47c9-9c59-7a2c"
REFRESH_TOKEN = os.environ.get("EBAY_REFRESH_TOKEN") or "v^1.1#i^1#r^1#I^3#f^0#p^3#t^Ul4xMF83OjYzN0Q1MEI2NTU3RDc0NzREQUQxRjBFQzIwOEE2OUYzXzJfMSNFXjI2MA=="

# Get fresh access token
cred = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
req = urllib.request.Request(
    "https://api.ebay.com/identity/v1/oauth2/token",
    data=f"grant_type=refresh_token&refresh_token={REFRESH_TOKEN}&scope=https://api.ebay.com/oauth/api_scope/sell.fulfillment%20https://api.ebay.com/oauth/api_scope/sell.inventory%20https://api.ebay.com/oauth/api_scope/sell.marketing".encode(),
    headers={"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Basic {cred}"}
)
resp = urllib.request.urlopen(req)
tokens = json.load(resp)
access_token = tokens["access_token"]
print(f"Got fresh access token: {access_token[:30]}...")

config = {
    "environment": "production",
    "production": {"api_base": "https://api.ebay.com", "web_base": "https://www.ebay.com"},
    "sandbox": {"api_base": "https://api.sandbox.ebay.com", "web_base": "https://www.sandbox.ebay.com"},
    "marketplace": {"marketplace_id": "EBAY_US", "currency": "USD"},
    "oauth": {
        "user_token": access_token,
        "refresh_token": REFRESH_TOKEN
    },
    "business_policies": {
        "payment_policy_id": "265656298018",
        "fulfillment_policy_id": "266026679018",
        "return_policy_id": "265656303018"
    },
    "listing_defaults": {
        "auto_publish": False,
        "condition": "NEW",
        "condition_id": "1000",
        "format": "FIXED_PRICE"
    }
}

config_path = os.path.join(os.path.dirname(__file__), "..", "config.json")
with open(config_path, "w") as f:
    json.dump(config, f, indent=2, ensure_ascii=False)
print("config.json created at", config_path)
