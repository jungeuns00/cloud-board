"""욕설 필터 Lambda (Function URL 로 호출).

요청:  POST {"title": "...", "content": "..."}
응답:  {"title": "...", "content": "...", "filtered": true|false}
"""
import json
import os
import re

DEFAULT_WORDS = "바보,멍청이,stupid,idiot"
BANNED = [w.strip() for w in os.getenv("BANNED_WORDS", DEFAULT_WORDS).split(",") if w.strip()]
PATTERN = re.compile("|".join(re.escape(w) for w in sorted(BANNED, key=len, reverse=True)), re.IGNORECASE)


def mask(text: str) -> str:
    return PATTERN.sub(lambda m: "*" * len(m.group()), text)


def lambda_handler(event, context):
    try:
        body = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            import base64
            body = base64.b64decode(body).decode("utf-8")
        data = json.loads(body)
        title, content = str(data.get("title", "")), str(data.get("content", ""))
    except (ValueError, AttributeError):
        return {"statusCode": 400, "body": json.dumps({"error": "invalid JSON"})}

    new_title, new_content = mask(title), mask(content)
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(
            {"title": new_title, "content": new_content,
             "filtered": (new_title, new_content) != (title, content)},
            ensure_ascii=False,
        ),
    }
