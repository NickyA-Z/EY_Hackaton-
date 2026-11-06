"""
Step 4 - checks on the AI's answer (no AI involved):
  1. schema   : the answer has exactly the required fields, types and allowed values
  2. numbers  : every number the AI cites as evidence really exists in the briefing pack
"""
from __future__ import annotations

import math
import re

NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def validate(obj, schema, path="$") -> list[str]:
    """Minimal JSON-Schema check for the subset used in prompt.OUTPUT_SCHEMA."""
    errs = []
    t = schema.get("type")
    ok = {"object": isinstance(obj, dict), "array": isinstance(obj, list), "string": isinstance(obj, str),
          "number": isinstance(obj, (int, float)) and not isinstance(obj, bool), "boolean": isinstance(obj, bool)}
    if t and not ok.get(t, True):
        return [f"{path}: expected {t}, got {type(obj).__name__}"]
    if "enum" in schema and obj not in schema["enum"]:
        errs.append(f"{path}: '{obj}' not in {schema['enum']}")
    if t == "object":
        for k in schema.get("required", []):
            if k not in obj:
                errs.append(f"{path}.{k}: missing")
        if schema.get("additionalProperties") is False:
            errs += [f"{path}.{k}: not allowed" for k in obj if k not in schema.get("properties", {})]
        for k, sub in schema.get("properties", {}).items():
            if k in obj:
                errs += validate(obj[k], sub, f"{path}.{k}")
    if t == "array":
        for i, item in enumerate(obj):
            errs += validate(item, schema.get("items", {}), f"{path}[{i}]")
    return errs


def _resolve(pack, dotted):
    cur = pack
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
    return cur


def _numbers_in(x) -> list[float]:
    """All numbers inside a value: numbers, lists, dicts, and numbers written inside strings ('high 14:21 1.49 m')."""
    if isinstance(x, bool) or x is None:
        return []
    if isinstance(x, (int, float)):
        return [float(x)]
    if isinstance(x, str):
        return [float(n) for n in NUM_RE.findall(x)]
    if isinstance(x, dict):
        return [n for v in x.values() for n in _numbers_in(v)]
    if isinstance(x, list):
        return [n for v in x for n in _numbers_in(v)]
    return []


def _close(a, b) -> bool:
    # pack numbers are rounded to 0.1 / 0.01, and the AI is told to copy them exactly: allow only rounding noise
    return abs(a - b) <= max(0.051, 0.001 * abs(b))


def trace_numbers(answer: dict, pack: dict) -> dict:
    """Each cited evidence value must equal the value at its pack_path (or, failing that, appear somewhere in the pack)."""
    all_pack = _numbers_in(pack)
    rows = []

    def walk(x, where):
        if isinstance(x, dict):
            if {"value", "pack_path"} <= set(x):
                at = _resolve(pack, x["pack_path"])
                at_nums = _numbers_in(at) if at is not None else []
                if at is not None and any(_close(x["value"], n) for n in at_nums):
                    status = "verified_at_path"
                elif any(_close(x["value"], n) for n in all_pack):
                    status = "in_pack_wrong_path" if at is not None else "in_pack_path_not_found"
                else:
                    status = "NOT_IN_PACK"
                rows.append({"where": where, "value": x["value"], "unit": x.get("unit"), "pack_path": x["pack_path"], "status": status})
            for k, v in x.items():
                walk(v, f"{where}.{k}")
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{where}[{i}]")

    walk(answer, "$")
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"cited_numbers": len(rows), "by_status": counts,
            "problems": [r for r in rows if r["status"] != "verified_at_path"]}
