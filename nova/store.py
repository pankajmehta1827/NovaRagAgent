"""Runtime persistence: ops settings, FAQ overrides, turn logs, feedback.

Deliberately file-based JSON/JSONL so the reference implementation runs with no
infrastructure. In production these are the analytics warehouse (FR-6.2), the
knowledge CMS (FR-5.1) and the config service (FR-3.1).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import config


def _ensure_runtime() -> None:
    config.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    _ensure_runtime()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_jsonl(path: Path, record: dict) -> None:
    _ensure_runtime()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path, limit: int | None = None) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records[-limit:] if limit else records


# --- settings (FR-3.1, FR-3.8, FR-4.7) ---------------------------------------


def load_settings() -> dict:
    stored = _read_json(config.SETTINGS_PATH, {})
    settings = dict(config.DEFAULT_SETTINGS)
    settings.update({key: value for key, value in stored.items() if key in config.DEFAULT_SETTINGS})
    return settings


def save_settings(settings: dict) -> None:
    _write_json(config.SETTINGS_PATH, settings)


# --- FAQ overrides (FR-5.1, FR-5.5) ------------------------------------------


def load_faq_overrides() -> dict[str, dict]:
    return _read_json(config.FAQ_OVERRIDES_PATH, {})


def save_faq_override(faq_id: str, entry: dict) -> None:
    overrides = load_faq_overrides()
    entry = dict(entry)
    entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
    overrides[str(faq_id)] = entry
    _write_json(config.FAQ_OVERRIDES_PATH, overrides)


def delete_faq_override(faq_id: str) -> None:
    """Roll back one console edit, restoring the underlying source row (FR-5.5)."""
    overrides = load_faq_overrides()
    overrides.pop(str(faq_id), None)
    _write_json(config.FAQ_OVERRIDES_PATH, overrides)


# --- logs (FR-6.2, FR-5.6) ---------------------------------------------------


def log_turn(record: dict) -> None:
    record.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
    _append_jsonl(config.TURNS_LOG_PATH, record)


def log_feedback(record: dict) -> None:
    record.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
    _append_jsonl(config.FEEDBACK_LOG_PATH, record)


def log_escalation(record: dict) -> None:
    record.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
    _append_jsonl(config.ESCALATIONS_LOG_PATH, record)


def read_turns(limit: int | None = None) -> list[dict]:
    return _read_jsonl(config.TURNS_LOG_PATH, limit)


def read_feedback(limit: int | None = None) -> list[dict]:
    return _read_jsonl(config.FEEDBACK_LOG_PATH, limit)


def read_escalations(limit: int | None = None) -> list[dict]:
    return _read_jsonl(config.ESCALATIONS_LOG_PATH, limit)


# --- derived views -----------------------------------------------------------


def unanswered_queue(days: int = 30) -> list[dict]:
    """Questions Nova could not answer, newest first (FR-5.6).

    Every refusal, low-confidence answer and thumbs-down becomes a content
    backlog item. This is the single most valuable output of the system after
    the answers themselves.
    """
    cutoff = datetime.now() - timedelta(days=days)
    negative_feedback = {
        item.get("turn_id")
        for item in read_feedback()
        if item.get("rating") == "down"
    }

    items: list[dict] = []
    for turn in read_turns():
        try:
            when = datetime.fromisoformat(turn.get("timestamp", ""))
        except ValueError:
            continue
        if when < cutoff:
            continue
        thumbs_down = turn.get("turn_id") in negative_feedback
        unanswered = turn.get("status") in {"NO_VERIFIED_ANSWER", "ERROR"} or turn.get("escalated")
        low_confidence = turn.get("confidence", 1.0) < turn.get("threshold", 0.45)
        if not (thumbs_down or unanswered or low_confidence):
            continue
        items.append(
            {
                "timestamp": turn.get("timestamp"),
                "question": turn.get("question", ""),
                "status": turn.get("status"),
                "confidence": round(turn.get("confidence", 0.0), 3),
                "reason_code": turn.get("reason_code", ""),
                "thumbs_down": thumbs_down,
                "top_source": turn.get("top_source", ""),
            }
        )
    items.sort(key=lambda item: item["timestamp"] or "", reverse=True)
    return items


def metrics(days: int = 30) -> dict:
    """The §6 dashboard numbers (FR-6.3)."""
    cutoff = datetime.now() - timedelta(days=days)
    turns = []
    for turn in read_turns():
        try:
            if datetime.fromisoformat(turn.get("timestamp", "")) >= cutoff:
                turns.append(turn)
        except ValueError:
            continue

    sessions: dict[str, list[dict]] = {}
    for turn in turns:
        sessions.setdefault(turn.get("session_id", "?"), []).append(turn)

    escalated_sessions = {
        session_id for session_id, session in sessions.items() if any(t.get("escalated") for t in session)
    }
    contained = len(sessions) - len(escalated_sessions)

    feedback = [f for f in read_feedback() if f.get("rating") in {"up", "down"}]
    thumbs_up = sum(1 for f in feedback if f["rating"] == "up")

    cost = 0.0
    for turn in turns:
        for usage in turn.get("usage", []):
            price = config.PRICE_PER_MTOK.get(usage.get("model"), {})
            cost += usage.get("input_tokens", 0) / 1_000_000 * price.get("input", 0)
            cost += usage.get("output_tokens", 0) / 1_000_000 * price.get("output", 0)

    answered = [t for t in turns if t.get("status") == "ANSWERED"]
    latencies = sorted(t.get("latency_ms", 0) for t in turns if t.get("latency_ms"))

    def percentile(values: list[float], fraction: float) -> float:
        if not values:
            return 0.0
        return values[min(len(values) - 1, int(len(values) * fraction))]

    return {
        "turns": len(turns),
        "sessions": len(sessions),
        "contained_sessions": contained,
        "containment_rate": contained / len(sessions) if sessions else 0.0,
        "escalated_sessions": len(escalated_sessions),
        "answered_rate": len(answered) / len(turns) if turns else 0.0,
        "refusal_rate": sum(1 for t in turns if t.get("status") == "NO_VERIFIED_ANSWER") / len(turns) if turns else 0.0,
        "thumbs_up_rate": thumbs_up / len(feedback) if feedback else 0.0,
        "feedback_count": len(feedback),
        "total_cost_usd": cost,
        "cost_per_session": cost / len(sessions) if sessions else 0.0,
        "p50_latency_ms": percentile(latencies, 0.50),
        "p95_latency_ms": percentile(latencies, 0.95),
    }
