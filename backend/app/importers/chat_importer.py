"""
Chat history importer for Claude and Gemini AI exports.
Extracts race predictions from exported chat conversations.
"""
import json
import re
from typing import Dict, Any
from backend.app.config import get_supabase


async def import_claude_chat(content: bytes) -> Dict[str, Any]:
    """Import predictions from Claude.ai exported chat JSON."""
    sb = get_supabase()
    imported = 0
    skipped = 0

    try:
        data = json.loads(content)
        conversations = data if isinstance(data, list) else [data]

        for conv in conversations:
            messages = conv.get("chat_messages", [])
            for msg in messages:
                if msg.get("sender") != "assistant":
                    continue

                text = ""
                for part in msg.get("content", []):
                    if isinstance(part, dict) and part.get("type") == "text":
                        text += part.get("text", "")

                result = _extract_prediction_from_text(text, "claude")
                if result:
                    success = _save_prediction(sb, result)
                    if success:
                        imported += 1
                    else:
                        skipped += 1

    except Exception as e:
        return {"imported": imported, "skipped": skipped, "error": str(e)}

    return {"imported": imported, "skipped": skipped}


async def import_gemini_chat(content: bytes) -> Dict[str, Any]:
    """Import predictions from Gemini exported chat JSON."""
    sb = get_supabase()
    imported = 0
    skipped = 0

    try:
        data = json.loads(content)
        messages = data.get("messages", []) if isinstance(data, dict) else []

        for msg in messages:
            if msg.get("role") != "model":
                continue

            text = ""
            for part in msg.get("parts", []):
                if isinstance(part, dict):
                    text += part.get("text", "")

            result = _extract_prediction_from_text(text, "gemini")
            if result:
                success = _save_prediction(sb, result)
                if success:
                    imported += 1
                else:
                    skipped += 1

    except Exception as e:
        return {"imported": imported, "skipped": skipped, "error": str(e)}

    return {"imported": imported, "skipped": skipped}


def _extract_prediction_from_text(text: str, source: str) -> Dict[str, Any]:
    """Extract prediction data from LLM response text."""
    json_match = re.search(r'\{[^{}]*"trifecta"[^{}]*\}', text, re.DOTALL)
    if not json_match:
        return None

    try:
        data = json.loads(json_match.group())
        data["source"] = source
        return data
    except Exception:
        return None


def _save_prediction(sb, prediction: Dict[str, Any]) -> bool:
    """Save prediction to database. Returns True if saved, False if skipped."""
    try:
        race_id = prediction.get("race_id")
        if not race_id:
            return False

        sb.table("predictions").insert(prediction).execute()
        return True
    except Exception:
        return False
