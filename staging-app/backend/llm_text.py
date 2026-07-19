"""Text LLM command parser. Spec Section 10.

Calls an OpenAI-compatible chat model (NVIDIA NIM / HF / local Ollama), extracts
the first JSON object, validates it against the Command pydantic model, and
repairs once on invalid JSON.
"""
from __future__ import annotations

import json
import os
import re
from typing import List

from openai import OpenAI

from schemas import Command, ObjectRef

SYSTEM_PROMPT = """You convert a user's natural-language instruction about arranging a 3D room into ONE JSON command.
Output JSON ONLY. No prose, no markdown, no code fences.

Valid actions: "place", "add", "remove", "scale", "clear", "error".
Valid relations (for "place"): on_floor, on_top_of, against_wall, left_of, right_of,
  in_front_of, behind, near, center_of_room.
Rules:
- "object" and "target" MUST be labels drawn from the provided object list (match case-insensitively).
  If the user names something not in the list, return action "error" with a helpful message.
- Never output numeric coordinates. Positions are decided by relations only.
- "align" is optional: center|left|right (default center).
- "targetHeight" is optional meters, only if the user specifies a size.

Object list: {OBJECTS}
Room present: {HAS_ROOM}

Return exactly one JSON object."""

FEW_SHOT = [
    (
        'put the lamp on the coffee table',
        '{"action":"place","object":"lamp","relation":"on_top_of","target":"coffee table","align":"center","targetHeight":null}',
    ),
    (
        'move the sofa against the wall',
        '{"action":"place","object":"sofa","relation":"against_wall","target":"wall"}',
    ),
    ("remove the plant", '{"action":"remove","object":"plant"}'),
    (
        "put the giraffe on the table",
        '{"action":"error","message":"No object called \'giraffe\' is in the scene."}',
    ),
]


def _client() -> OpenAI:
    return OpenAI(
        base_url=os.environ.get("TEXT_LLM_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.environ.get("TEXT_LLM_API_KEY", "EMPTY") or "EMPTY",
        timeout=30.0,
        max_retries=1,
    )


def _model() -> str:
    return os.environ.get("TEXT_LLM_MODEL", "llama3.1:8b")


def _extract_json(text: str) -> dict:
    """Pull the first balanced {...} block and json.loads it."""
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in output")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    # fall back to a greedy regex if unbalanced
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("unbalanced JSON")
    return json.loads(m.group(0))


def _build_messages(text: str, objects: List[ObjectRef], has_room: bool) -> list:
    obj_labels = ", ".join(o.label for o in objects) or "(none)"
    system = SYSTEM_PROMPT.replace("{OBJECTS}", obj_labels).replace(
        "{HAS_ROOM}", "yes" if has_room else "no"
    )
    messages = [{"role": "system", "content": system}]
    for user, assistant in FEW_SHOT:
        messages.append({"role": "user", "content": user})
        messages.append({"role": "assistant", "content": assistant})
    messages.append({"role": "user", "content": text})
    return messages


def parse_command(text: str, objects: List[ObjectRef], has_room: bool) -> Command:
    client = _client()
    model = _model()
    messages = _build_messages(text, objects, has_room)

    def call(msgs: list) -> str:
        resp = client.chat.completions.create(
            model=model, messages=msgs, temperature=0, max_tokens=256
        )
        return resp.choices[0].message.content or ""

    # First attempt.
    try:
        raw = call(messages)
        return Command(**_extract_json(raw))
    except Exception:
        pass

    # One repair retry.
    try:
        repair = messages + [
            {"role": "assistant", "content": raw if "raw" in dir() else ""},
            {
                "role": "user",
                "content": "Your last output was not valid JSON. Return JSON only, one object.",
            },
        ]
        raw2 = call(repair)
        return Command(**_extract_json(raw2))
    except Exception:
        return Command(action="error", message="Could not parse that.")
