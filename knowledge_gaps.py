#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Delivery of unanswered caller questions to the n8n knowledge-gaps webhook.

When the bot cannot answer a question from ``knowledge.txt`` it calls the
``report_unanswered_question`` tool, and a ``KnowledgeGapReporter`` posts the
question to the webhook named by ``LAMSA_N8N_UNANSWERED_WEBHOOK_URL``,
authenticated with the ``X-Lamsa-Token`` header (``LAMSA_N8N_WEBHOOK_TOKEN``).
Each report is sent in the background so the conversation never waits on n8n.
Every report carries a ``report_id`` that n8n upserts on, so a retry never
creates a second row. Delivery never raises: after the retries are spent the
report is written to ``failed_questions/`` so it can be resent by hand.
"""

import asyncio
import datetime
import json
import os
import uuid
from pathlib import Path

import aiohttp
from loguru import logger

FAILED_QUESTIONS_DIR = Path(__file__).resolve().parent / "failed_questions"

SEND_ATTEMPTS = 3
SEND_TIMEOUT_SECS = 10
RETRY_DELAYS_SECS = (1, 3)
FLUSH_TIMEOUT_SECS = 30


def _now_iso() -> str:
    now = datetime.datetime.now(datetime.UTC)
    return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class KnowledgeGapReporter:
    """Sends one call's unanswered questions to n8n without blocking the call."""

    def __init__(self, call_id: str):
        """Initialize the reporter.

        Args:
            call_id: The call the questions belong to, shared with the call recorder.
        """
        self.call_id = call_id
        self._tasks: set[asyncio.Task] = set()

    def report(self, question: str, customer_words: str = "", topic: str = "") -> str | None:
        """Queue a question for delivery and return its report ID.

        Returns ``None`` without sending anything when the question is empty or
        ``LAMSA_N8N_UNANSWERED_WEBHOOK_URL`` is unset.

        Args:
            question: The caller's question, as the LLM restated it.
            customer_words: What the caller actually said, from the transcription.
            topic: A short category chosen by the LLM, such as "الأسعار".
        """
        question = (question or "").strip()
        url = os.getenv("LAMSA_N8N_UNANSWERED_WEBHOOK_URL")
        if not question:
            return None
        if not url:
            logger.debug("Knowledge gaps disabled: LAMSA_N8N_UNANSWERED_WEBHOOK_URL is not set")
            return None

        body = {
            "schema_version": 1,
            "report_id": f"Q-{uuid.uuid4().hex[:8].upper()}",
            "call_id": self.call_id,
            "question": question,
            "customer_words": (customer_words or "").strip(),
            "topic": (topic or "").strip(),
            "asked_at": _now_iso(),
        }
        task = asyncio.create_task(self._send(url, body))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return body["report_id"]

    async def flush(self):
        """Wait for reports still being sent, so hanging up doesn't drop them. Never raises."""
        if not self._tasks:
            return
        _, pending = await asyncio.wait(set(self._tasks), timeout=FLUSH_TIMEOUT_SECS)
        for task in pending:
            task.cancel()

    async def _send(self, url: str, body: dict):
        report_id = body["report_id"]
        try:
            headers = {"X-Lamsa-Token": os.getenv("LAMSA_N8N_WEBHOOK_TOKEN", "")}
            timeout = aiohttp.ClientTimeout(total=SEND_TIMEOUT_SECS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for attempt in range(1, SEND_ATTEMPTS + 1):
                    try:
                        async with session.post(url, json=body, headers=headers) as response:
                            if 200 <= response.status < 300:
                                logger.info(f"Unanswered question {report_id} sent to n8n")
                                return
                            error = f"HTTP {response.status}"
                    except (TimeoutError, aiohttp.ClientError) as e:
                        error = type(e).__name__
                    logger.warning(
                        f"Unanswered question {report_id} send attempt "
                        f"{attempt}/{SEND_ATTEMPTS} failed: {error}"
                    )
                    if attempt < SEND_ATTEMPTS:
                        await asyncio.sleep(RETRY_DELAYS_SECS[attempt - 1])
            self._save_failed(body)
        except Exception as e:
            logger.error(f"Unanswered question {report_id} could not be sent: {type(e).__name__}")

    def _save_failed(self, body: dict):
        FAILED_QUESTIONS_DIR.mkdir(exist_ok=True)
        path = FAILED_QUESTIONS_DIR / f"{body['report_id']}.json"
        path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.error(f"Unanswered question {body['report_id']} not delivered; saved to {path.name}")
