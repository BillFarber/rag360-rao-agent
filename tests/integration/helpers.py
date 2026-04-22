import json


def extract_answer(body: str) -> str:
    """Extract the final answer from an NDJSON streaming response."""
    for line in body.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        answer = obj.get("answer")
        if answer is not None:
            return str(answer)
    return ""
