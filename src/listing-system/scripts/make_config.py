#!/usr/bin/env python3
"""Generate config.json from environment variables"""
import json, os

config = {
    "environment": "production",
    "production": {
        "api_base": "https://api.ebay.com",
        "web_base": "https://www.ebay.com"
    },
    "sandbox": {
        "api_base": "https://api.sandbox.ebay.com",
        "web_base": "https://www.sandbox.ebay.com"
    },
    "marketplace": {
        "marketplace_id": "EBAY_US",
        "currency": "USD"
    },
    "oauth": {
        "user_token": os.environ.get("EBAY_USER_TOKEN", ""),
        "refresh_token": os.environ.get("EBAY_REFRESH_TOKEN", "")
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
