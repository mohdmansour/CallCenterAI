#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Call transcript recording and delivery to the n8n call-monitoring webhook.

A ``CallRecorder`` collects one call's customer and agent messages with their
offset from the start of the call. When the call ends, ``send()`` posts the
whole call to the webhook named by ``LAMSA_N8N_WEBHOOK_URL``, authenticated with
the ``X-Lamsa-Token`` header (``LAMSA_N8N_WEBHOOK_TOKEN``). Delivery never
raises: after the retries are spent the payload is written to ``failed_calls/``
so it can be resent by hand. Transcripts are never logged.
"""

import asyncio
import datetime
import json
import os
import uuid
from pathlib import Path

import aiohttp
from loguru import logger

FAILED_CALLS_DIR = Path(__file__).resolve().parent / "failed_calls"

SEND_ATTEMPTS = 3
SEND_TIMEOUT_SECS = 10
RETRY_DELAYS_SECS = (1, 3)

SPEAKER_LABELS = {"customer": "العميل", "agent": "لمسة"}


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _iso(dt: datetime.datetime) -> str:
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class CallRecorder:
    """Records one call's transcript and delivers it to n8n once the call ends."""

    def __init__(self):
        """Initialize the recorder with a fresh call ID."""
        self.call_id = f"CALL-{uuid.uuid4().hex[:8].upper()}"
        self.started_at: datetime.datetime | None = None
        self.end_reason = "ended"
        self._messages: list[dict] = []
        self._sent = False

    def start(self):
        """Mark the start of the call; message offsets are measured from here."""
        if self.started_at is None:
            self.started_at = _now()

    def add_message(self, speaker: str, text: str | None, timestamp: str | None, **extra):
        """Record one message.

        Args:
            speaker: ``"customer"`` or ``"agent"``.
            text: What was said. Empty messages are ignored.
            timestamp: ISO 8601 time the message started, from the turn event.
                The current time is used when it is missing or unparseable.
            **extra: Additional fields stored with the message (e.g. ``interrupted``).
        """
        text = (text or "").strip()
        if not text or self.started_at is None:
            return
        try:
            at = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            at = _now()
        offset = max(0.0, (at - self.started_at).total_seconds())
        self._messages.append(
            {"speaker": speaker, "text": text, "offset_seconds": round(offset, 1), **extra}
        )

    def payload(self) -> dict:
        """Build the webhook body for the call so far."""
        ended_at = _now()
        messages = sorted(self._messages, key=lambda m: m["offset_seconds"])
        for index, message in enumerate(messages, start=1):
            message["index"] = index
            message["offset_mmss"] = _mmss(message["offset_seconds"])
        transcript = "\n".join(
            f"#{m['index']} [{m['offset_mmss']}] {SPEAKER_LABELS[m['speaker']]}: {m['text']}"
            for m in messages
        )
        return {
            "schema_version": 1,
            "call_id": self.call_id,
            "started_at": _iso(self.started_at),
            "ended_at": _iso(ended_at),
            "duration_seconds": round((ended_at - self.started_at).total_seconds(), 1),
            "end_reason": self.end_reason,
            "message_count": len(messages),
            "transcript": transcript,
            "messages": messages,
        }

    async def send(self):
        """Deliver the call to n8n once. Never raises.

        Does nothing when the call never started or when ``LAMSA_N8N_WEBHOOK_URL``
        is unset. A 2xx response counts as delivered; anything else is retried.
        """
        if self._sent or self.started_at is None:
            return
        self._sent = True

        url = os.getenv("LAMSA_N8N_WEBHOOK_URL")
        if not url:
            logger.debug("Call monitoring disabled: LAMSA_N8N_WEBHOOK_URL is not set")
            return

        try:
            body = self.payload()
            headers = {"X-Lamsa-Token": os.getenv("LAMSA_N8N_WEBHOOK_TOKEN", "")}
            timeout = aiohttp.ClientTimeout(total=SEND_TIMEOUT_SECS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for attempt in range(1, SEND_ATTEMPTS + 1):
                    try:
                        async with session.post(url, json=body, headers=headers) as response:
                            if 200 <= response.status < 300:
                                logger.info(f"Call {self.call_id} sent to n8n")
                                return
                            error = f"HTTP {response.status}"
                    except (TimeoutError, aiohttp.ClientError) as e:
                        error = type(e).__name__
                    logger.warning(
                        f"Call {self.call_id} send attempt {attempt}/{SEND_ATTEMPTS} failed: {error}"
                    )
                    if attempt < SEND_ATTEMPTS:
                        await asyncio.sleep(RETRY_DELAYS_SECS[attempt - 1])
            self._save_failed(body)
        except Exception as e:
            logger.error(f"Call {self.call_id} could not be sent: {type(e).__name__}")

    def _save_failed(self, body: dict):
        FAILED_CALLS_DIR.mkdir(exist_ok=True)
        path = FAILED_CALLS_DIR / f"{self.call_id}.json"
        path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.error(f"Call {self.call_id} not delivered; saved to {path.name} for resending")
