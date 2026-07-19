"""Vision LLM placement validator. Spec Section 11.

Sends the rendered screenshot + intended relation to a local Qwen2.5-VL via
Ollama's OpenAI-compatible endpoint and returns a closed-form pass/fail.
"""
from __future__ import annotations

import json
import os
import re

from openai import OpenAI

from schemas import ValidateRequest, ValidateResponse

VISION_PROMPT = """You are inspecting a rendered 3D scene. The user intended to place the {object}
{relation_phrase} the {target}.
Look at the image and judge ONLY these three things:
1. Contact/position: is the {object} actually {relation_phrase} the {target},
   with no visible floating gap and no interpenetration?
2. Scale: is the {object} a plausible real-world size relative to the {target}?
3. Nothing else.
Respond with JSON ONLY:
{{"pass": true|false, "reason": "<one short sentence>",
 "suggestion": "move_up|move_down|move_left|move_right|scale_up|scale_down|none"}}
"pass" is true ONLY if position AND scale are both correct."""


def _client() -> OpenAI:
    return OpenAI(
        base_url=os.environ.get("VISION_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.environ.get("VISION_API_KEY", "ollama") or "ollama",
        timeout=30.0,
        max_retries=1,
    )


def _model() -> str:
    return os.environ.get("VISION_MODEL", "qwen2.5vl:3b")


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON in vision output")
    return json.loads(m.group(0))


def validate_placement(req: ValidateRequest) -> ValidateResponse:
    client = _client()
    prompt = VISION_PROMPT.format(
        object=req.object, relation_phrase=req.relation_phrase, target=req.target
    )
    # image_base64 is a full data URL (data:image/jpeg;base64,...).
    try:
        resp = client.chat.completions.create(
            model=_model(),
            temperature=0,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": req.image_base64}},
                    ],
                }
            ],
        )
        raw = resp.choices[0].message.content or ""
        data = _extract_json(raw)
        return ValidateResponse(
            **{
                "pass": bool(data.get("pass", False)),
                "reason": str(data.get("reason", "")),
                "suggestion": data.get("suggestion", "none"),
            }
        )
    except Exception as e:  # never crash the placement flow on a vision hiccup
        return ValidateResponse(**{"pass": False, "reason": f"Vision error: {e}", "suggestion": "none"})
