"""Append human disagreement labels to data/labels.jsonl."""

import json
import os
import time
from typing import Any

from app import config


def append_label(record: dict[str, Any]) -> None:
    record = {**record, "timestamp": time.time()}
    os.makedirs(os.path.dirname(os.path.abspath(config.LABELS_PATH)), exist_ok=True)
    with open(config.LABELS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
