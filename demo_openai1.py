#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from call_monitor import CallRecorder
from knowledge_gaps import KnowledgeGapReporter
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.stt import OpenAISTTService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner
from ui_control import ScreenController

import turn_fix  # noqa: F401  (lets calls connect through a TURN relay)

load_dotenv(override=True)

# The company knowledge base is a plain text file next to this script.
KNOWLEDGE_PATH = Path(__file__).resolve().parent / "knowledge.txt"
KNOWLEDGE = KNOWLEDGE_PATH.read_text(encoding="utf-8")

SYSTEM_INSTRUCTION = f"""أنت مساعد صوتي لشركة "لمسة". تتحدث مع العملاء بالعربية بلهجة بسيطة وودودة.
ردودك تُنطق بصوت عالٍ، لذلك اجعلها قصيرة (جملة إلى ثلاث جمل) وبدون رموز أو قوائم أو إيموجي.
أجب عن أسئلة العميل اعتماداً على المعلومات التالية فقط. إذا لم تجد الجواب فيها، قل بصراحة إنك لا تملك هذه المعلومة واقترح التواصل مع فريق الشركة، ولا تخترع معلومات.
عندما يسأل العميل سؤالاً عن الشركة أو خدماتها أو أسعارها أو طريقة عملها ولا تجد جوابه في المعلومات التالية، استدعِ الأداة report_unanswered_question مرة واحدة لهذا السؤال قبل أن ترد، ثم أخبر العميل أنك لا تملك المعلومة. لا تستدعها للتحيات أو الأسئلة البعيدة عن الشركة أو الأسئلة التي أجبت عنها، ولا تذكر الأداة للعميل.
عندما يطلب العميل الذهاب إلى جزء من الصفحة أو تتحدث عن جزء منها، استدعِ أداة العرض المناسبة حتى يراه على الشاشة، ثم اتبع الـ hint في نتيجتها.

معلومات الشركة:
{KNOWLEDGE}
"""

# We use lambdas to defer transport parameter creation until the transport
# type is selected at runtime.
transport_params = {
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting bot")

    stt = OpenAISTTService(api_key=os.environ["OPENAI_API_KEY"])

    tts = OpenAITTSService(api_key=os.environ["OPENAI_API_KEY"])

    llm = OpenAILLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        settings=OpenAILLMService.Settings(
            system_instruction=SYSTEM_INSTRUCTION,
        ),
    )

    # Records the call's transcript and sends it to the n8n call-monitoring
    # webhook when the call ends.
    recorder = CallRecorder()

    # Sends questions the knowledge base can't answer to the n8n knowledge-gaps
    # webhook, in the background.
    gaps = KnowledgeGapReporter(recorder.call_id)
    last_customer_words = ""

    async def report_unanswered_question(params: FunctionCallParams, question: str, topic: str):
        """Report a customer question that the company information does not answer.

        Args:
            question (str): The customer's question, restated clearly in Arabic as one sentence.
            topic (str): A short Arabic category for the question, such as "الخدمات" or "الأسعار" or "الدوام" or "التواصل".
        """
        gaps.report(question, customer_words=last_customer_words, topic=topic)
        await params.result_callback({"recorded": True})

    # Lets the customer move around the page by voice.
    screen = ScreenController()

    context = LLMContext(tools=[report_unanswered_question, *screen.tools])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    @user_aggregator.event_handler("on_user_turn_stopped")
    async def on_user_turn_stopped(aggregator, strategy, message):
        nonlocal last_customer_words
        last_customer_words = message.content or ""
        recorder.add_message("customer", message.content, message.timestamp)

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(aggregator, message):
        recorder.add_message(
            "agent", message.content, message.timestamp, interrupted=message.interrupted
        )

    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            stt,
            user_aggregator,  # User responses
            llm,  # LLM
            tts,  # TTS
            transport.output(),  # Transport bot output
            assistant_aggregator,  # Assistant spoken responses
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)

    await runner.add_workers(worker)

    @worker.rtvi.event_handler("on_client_message")
    async def on_client_message(rtvi, message):
        if message.type == "ui-state":
            screen.update(message.data)

    @worker.event_handler("on_idle_timeout")
    async def on_idle_timeout(worker):
        recorder.end_reason = "idle_timeout"

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        recorder.start()
        # Kick off the conversation.
        context.add_message(
            {
                "role": "developer",
                "content": "رحّب بالعميل بالعربية باختصار، وعرّف بنفسك كمساعد شركة لمسة، ثم قل حرفياً: تنبيه: نص المحادثة يُحفظ لأغراض تحسين الخدمة. ثم اسأله كيف تساعده.",
            }
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        recorder.end_reason = "client_disconnected"
        await runner.cancel()

    try:
        await runner.run()
    except Exception:
        recorder.end_reason = "error"
        raise
    finally:
        await gaps.flush()
        await recorder.send()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from fastapi.responses import RedirectResponse
    from fastapi.staticfiles import StaticFiles

    from pipecat.runner.run import app, main

    # Serve the custom interface from the bot's own server. Routes registered here
    # come before the runner's own, so "/" opens the custom page while the stock
    # interface stays available at /client. Without a ui folder nothing changes.
    UI_DIR = Path(__file__).resolve().parent / "ui"
    if UI_DIR.is_dir():

        @app.get("/", include_in_schema=False)
        async def home():
            return RedirectResponse(url="/ui/")

        app.mount("/ui", StaticFiles(directory=UI_DIR, html=True), name="lamsa-ui")

    main()
