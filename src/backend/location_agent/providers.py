"""
Step 3b - swappable AI providers. Switch model/provider by editing the repo-root .env only.

  LLM_PROVIDER=anthropic           Claude via LangChain (langchain-anthropic)
  LLM_PROVIDER=openai_compatible   any server with POST {LLM_BASE_URL}/chat/completions
                                   (OpenRouter, Ollama, vLLM, LM Studio, TGI ... e.g. behind an ngrok URL);
                                   LLM_EXTRA_BODY adds provider-specific JSON fields, LLM_JSON_MODE=false
                                   turns off response_format for models that reject it
  LLM_PROVIDER=mock                offline test: returns a fixed, schema-valid answer (no API call)

Every provider returns (answer_dict, meta_dict).
"""
from __future__ import annotations

import json
import os
import re
import time

from backend import paths

from .prompt import OUTPUT_SCHEMA, SYSTEM_PROMPT, compact_schema, schema_instruction, user_message

ENV_FILE = paths.ROOT / ".env"      # the repo-wide .env, git-ignored


# ------------------------------------------------------------------ config
def load_config(overrides: dict | None = None) -> dict:
    """Reads the repo-root .env (KEY=VALUE lines). Real environment variables win over the file."""
    cfg = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.split(" #", 1)[0].strip().strip('"').strip("'")
    for k in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL", "LLM_TEMPERATURE", "LLM_EFFORT", "LLM_MAX_TOKENS",
              "LLM_EXTRA_BODY", "LLM_JSON_MODE", "LLM_STREAM"):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    cfg.update({k: v for k, v in (overrides or {}).items() if v})
    cfg.setdefault("LLM_PROVIDER", "anthropic")
    cfg.setdefault("LLM_MODEL", "claude-opus-5-5" if cfg["LLM_PROVIDER"] == "anthropic" else "")
    cfg.setdefault("LLM_MAX_TOKENS", "8000")
    cfg.setdefault("LLM_EFFORT", "medium")
    return cfg


def _extract_json(text: str) -> dict:
    """Parse a JSON object from model text (tolerates code fences / leading prose)."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        a, b = t.find("{"), t.rfind("}")
        if a >= 0 and b > a:
            return json.loads(t[a:b + 1])
        raise


# ------------------------------------------------------------------ Claude (LangChain)
def _anthropic(cfg: dict, pack: dict, model=None):
    """Claude through LangChain's ChatAnthropic. The request is the one the raw SDK call used to send: strict
    JSON-schema output, reasoning effort, and the server-side refusal fallback (beta). ``model`` replaces the real
    chat model (tests pass a scripted one)."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from backend.ai.models import text_of

    if model is None:
        from langchain_anthropic import ChatAnthropic

        # LLM_API_KEY, else ANTHROPIC_API_KEY from the repo-root .env (the key the dashboard's AI layer uses), else
        # ANTHROPIC_API_KEY in the shell
        api_key = cfg.get("LLM_API_KEY") or cfg.get("ANTHROPIC_API_KEY")
        model = ChatAnthropic(
            model=cfg["LLM_MODEL"], max_tokens=int(cfg["LLM_MAX_TOKENS"]), **({"api_key": api_key} if api_key else {}),
            output_config={"effort": cfg["LLM_EFFORT"], "format": {"type": "json_schema", "schema": compact_schema()}},
            # server-side refusal fallback: if the model declines, the API re-runs the request on Anthropic's
            # recommended fallback model inside the same call
            betas=["server-side-fallback-2026-07-01"], model_kwargs={"fallbacks": "default"})
    t0 = time.time()
    reply = model.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_message(pack))])
    info = reply.response_metadata or {}
    usage = reply.usage_metadata or {}
    stop = info.get("stop_reason")
    meta = {"provider": "anthropic", "requested_model": cfg["LLM_MODEL"], "served_by": info.get("model_name") or info.get("model"),
            "stop_reason": stop, "seconds": round(time.time() - t0, 1),
            "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
            "request_id": info.get("id")}
    if stop == "refusal":
        raise RuntimeError(f"Model refused: {info.get('stop_details')}")
    if stop == "max_tokens":
        raise RuntimeError("Answer cut off at max_tokens; raise LLM_MAX_TOKENS")
    text = text_of(reply.content)
    if not text.strip():
        raise RuntimeError(f"Empty answer from the model (stop_reason={stop}); raise LLM_MAX_TOKENS")
    return json.loads(text), meta


# ------------------------------------------------------------------ open models (OpenAI-compatible HTTP)
def _post_chat(requests, url, headers, body, stream):
    """POST a chat completion. Returns {content, finish_reason, model, provider, usage},
    or None on HTTP 400 (so the caller can retry without JSON mode). Raises on other errors."""
    if not stream:
        r = requests.post(url, headers=headers, json=body, timeout=900)
        if r.status_code == 400:
            return None
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code} from {url}: {r.text[:500]}")
        js = r.json()
        if "error" in js:                                         # e.g. OpenRouter rate limit / upstream timeout
            raise RuntimeError(f"Endpoint error: {json.dumps(js['error'])[:500]}")
        ch = js["choices"][0]
        return {"content": (ch.get("message") or {}).get("content"), "finish_reason": ch.get("finish_reason"),
                "model": js.get("model"), "provider": js.get("provider"), "usage": js.get("usage")}

    body = {**body, "stream": True, "stream_options": {"include_usage": True}}
    with requests.post(url, headers=headers, json=body, stream=True, timeout=(30, 300)) as r:
        if r.status_code == 400:
            return None
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code} from {url}: {r.text[:500]}")
        parts, out = [], {"finish_reason": None, "model": None, "provider": None, "usage": None}
        for raw in r.iter_lines(decode_unicode=True):
            if not raw or raw.startswith(":"):                     # blank lines / keep-alive comments
                continue
            if not raw.startswith("data:"):
                continue
            data = raw[5:].strip()
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            if "error" in chunk:
                raise RuntimeError(f"Endpoint error: {json.dumps(chunk['error'])[:500]}")
            out["model"] = chunk.get("model") or out["model"]
            out["provider"] = chunk.get("provider") or out["provider"]
            if chunk.get("usage"):
                out["usage"] = chunk["usage"]
            for ch in chunk.get("choices") or []:
                piece = (ch.get("delta") or {}).get("content")
                if piece:
                    parts.append(piece)
                if ch.get("finish_reason"):
                    out["finish_reason"] = ch["finish_reason"]
        out["content"] = "".join(parts)
        return out


def _openai_compatible(cfg: dict, pack: dict):
    import requests

    base = cfg.get("LLM_BASE_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("LLM_BASE_URL is empty (e.g. https://<id>.ngrok-free.app/v1)")
    if not cfg.get("LLM_MODEL"):
        raise RuntimeError("LLM_MODEL is empty (the model name served by your endpoint)")
    headers = {"Content-Type": "application/json", "ngrok-skip-browser-warning": "true", "X-Title": "Location Agent"}
    if cfg.get("LLM_API_KEY"):
        headers["Authorization"] = f"Bearer {cfg['LLM_API_KEY']}"
    json_mode = str(cfg.get("LLM_JSON_MODE", "true")).lower() not in ("false", "0", "no")
    body = {
        "model": cfg["LLM_MODEL"],
        "messages": [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + schema_instruction()},
                     {"role": "user", "content": user_message(pack)}],
        "temperature": float(cfg.get("LLM_TEMPERATURE", 0.2)),
        "max_tokens": int(cfg["LLM_MAX_TOKENS"]),
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    # Provider-specific extras as JSON, merged into the request body. OpenRouter example:
    # LLM_EXTRA_BODY={"reasoning": {"enabled": true}, "provider": {"only": ["nvidia"], "allow_fallbacks": false}}
    if cfg.get("LLM_EXTRA_BODY"):
        try:
            body.update(json.loads(cfg["LLM_EXTRA_BODY"]))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"LLM_EXTRA_BODY is not valid JSON: {e}") from e
    # Streaming (default) keeps the connection alive while slow / reasoning models think, which avoids
    # gateway timeouts (e.g. OpenRouter 504) on long generations. LLM_STREAM=false sends one blocking request.
    stream = str(cfg.get("LLM_STREAM", "true")).lower() not in ("false", "0", "no")
    t0 = time.time()
    url = f"{base}/chat/completions"
    res = _post_chat(requests, url, headers, body, stream)
    if res is None and "response_format" in body:                  # endpoint/model without JSON mode: retry once without it
        body.pop("response_format")
        res = _post_chat(requests, url, headers, body, stream)
    if res is None:
        raise RuntimeError(f"HTTP 400 from {url} (bad request)")
    usage = res["usage"] or {}
    meta = {"provider": "openai_compatible", "requested_model": cfg["LLM_MODEL"], "served_by": res["model"],
            "upstream_provider": res["provider"], "stop_reason": res["finish_reason"], "streamed": stream,
            "seconds": round(time.time() - t0, 1), "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "base_url_host": re.sub(r"^https?://", "", base).split("/")[0], "json_mode": "response_format" in body}
    if res["finish_reason"] == "length":
        raise RuntimeError(f"Answer cut off at max_tokens={body['max_tokens']} (output tokens {meta['output_tokens']}, "
                           f"of which reasoning {meta['reasoning_tokens']}; answer text so far {len(res['content'] or '')} chars, "
                           f"{meta['seconds']} s). Raise LLM_MAX_TOKENS or lower the reasoning effort in LLM_EXTRA_BODY.")
    content = res["content"]
    if not content:
        raise RuntimeError(f"Empty answer from the model (finish_reason={res['finish_reason']}); "
                           "with reasoning enabled, raise LLM_MAX_TOKENS")
    return _extract_json(content), meta


# ------------------------------------------------------------------ mock (offline pipeline test)
def _mock(cfg: dict, pack: dict):
    b = pack["building_blocks"]
    veer = b["2_persistent_shift"]["evidence"]["race_day"]["veer_deg_per_h_12_17"]
    adv = b["8_start_line_bias"]["evidence"]["at_race_day_wind"]["upwind_advantage_m"]
    reason = lambda txt, blk, val, unit, path: {"text": txt, "blocks": blk,
                                                "evidence": [{"value": val, "unit": unit, "pack_path": path}]}
    ans = {
        "q1_favoured_side": {"side": "right", "confidence": "low", "reasons": [
            reason("MOCK answer for pipeline testing only.", ["2"], veer, "deg/h",
                   "building_blocks.2_persistent_shift.evidence.race_day.veer_deg_per_h_12_17")]},
        "q2_shift_pattern": {"pattern": "unclear", "cycle_or_rate": "mock", "reasons": []},
        "q3_start": {"favoured_end": "south_left_end", "reasons": [
            reason("MOCK", ["8"], adv, "m", "building_blocks.8_start_line_bias.evidence.at_race_day_wind.upwind_advantage_m")]},
        "q4_contingencies": [{"scenario": "mock", "signs_to_watch": "mock", "then": "mock"}],
        "first_beat_plan": "MOCK - not a real strategy",
        "action_plan": {   # MOCK: a fixed, simple plan so the simulator / evaluator can be tested offline
            "start": {"line_position": 0.2 if adv and adv > 0 else 0.5, "first_tack": "starboard", "hold_first_tack_s": 60},
            "upwind": {"target_side": "right" if veer and veer > 0 else "left", "max_lateral_m": 300,
                       "tack_on_header_deg": 8, "header_hold_s": 20, "layline_overstand_m": 30},
            "downwind": {"target_side": "middle", "max_lateral_m": 250, "gybe_on_lift_deg": 10},
            "triggers": [{"condition": "wind_speed_below_kn", "value": 7, "then_target_side": "middle",
                          "then_tack_on_header_deg": 6, "why": "mock: light air, play the shifts"}],
        },
        "block_readings": {k: "mock" for k in OUTPUT_SCHEMA["properties"]["block_readings"]["required"]},
        "briefing_card_markdown": "**MOCK** - run with a real provider for a strategy.",
        "data_gaps_and_uncertainty": ["mock provider - no model was called"],
    }
    return ans, {"provider": "mock", "requested_model": "mock", "served_by": "mock", "stop_reason": "end_turn", "seconds": 0}


PROVIDERS = {"anthropic": _anthropic, "openai_compatible": _openai_compatible, "mock": _mock}


def generate(pack: dict, cfg: dict, model=None):
    """(answer, meta). ``model``: a LangChain chat model to use instead of the configured one (anthropic only)."""
    p = cfg["LLM_PROVIDER"]
    if p not in PROVIDERS:
        raise ValueError(f"Unknown LLM_PROVIDER '{p}'. Use one of {list(PROVIDERS)}")
    return PROVIDERS[p](cfg, pack, model) if (model is not None and p == "anthropic") else PROVIDERS[p](cfg, pack)
