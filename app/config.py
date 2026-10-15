"""Env-driven settings. Everything else lives in memory."""

import os

from dotenv import load_dotenv

load_dotenv()

HAS_API_KEY = bool(os.getenv("TYPESAFE_API_KEY"))
JEV_MODEL = os.getenv("JEV_MODEL") or "jev-latest"
MAX_COST_USD = float(os.getenv("MAX_COST_USD") or "2.00")

# $0.042 per million input tokens; output is free.
COST_PER_INPUT_TOKEN = 0.042 / 1e6

# Max messages per second sent to Jev; anything above is dropped and counted.
RATE_CAP_PER_S = 20

# Concurrent classification calls.
WORKERS = 4

IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN") or ""
# Instagram-login tokens use graph.instagram.com with /me; Facebook-login tokens
# use graph.facebook.com with the numeric IG user id.
IG_GRAPH_HOST = (os.getenv("IG_GRAPH_HOST") or "https://graph.instagram.com/v21.0").rstrip("/")
IG_USER_ID = os.getenv("IG_USER_ID") or "me"
IG_GRAPH_ENABLED = bool(IG_ACCESS_TOKEN)

LABELS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "labels.jsonl")
