"""Forgiving JSON extraction for models that wrap JSON in prose / code fences."""
import json
import re


def extract_json(text: str):
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    start = t.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(t)):
            ch = t[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    chunk = t[start:i + 1]
                    for cand in (chunk, re.sub(r",\s*([}\]])", r"\1", chunk)):
                        try:
                            return json.loads(cand)
                        except Exception:
                            pass
                    break
        start = t.find("{", start + 1)
    return None
