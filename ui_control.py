#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Voice control of the Lamsa page: tools that open, show and highlight parts of it.

The tools run in the bot, so they cannot touch the browser. Each one sends the
page a ``server-message`` over the RTVI data channel (``{"kind": "screen",
"action": ...}``) and the page carries it out in place, without navigating or
reloading, which would drop the WebRTC call. The page reports what is on screen
in a ``ui-state`` client message whenever that changes, so each tool decides for
itself whether anything needs to change. Every tool returns a ``hint`` telling
the model what to say next.
"""

from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame
from pipecat.services.llm_service import FunctionCallParams

# Settings the page can scroll to and highlight, with how to name them aloud.
SETTINGS = {
    "language": "لغة الواجهة",
    "microphone": "اختيار الميكروفون",
    "volume": "صوت المساعد",
    "show_conversation": "إظهار المحادثة",
    "live_captions": "الكتابة أثناء الكلام",
    "start_muted": "البدء والميكروفون مكتوم",
    "conversation_history": "تنزيل المحادثة ومسحها",
}

LANGUAGES = {"ar": "العربية", "en": "الإنجليزية"}


class ScreenController:
    """Tracks what the page shows and exposes the tools that change it."""

    def __init__(self):
        """Initialize with the page's state at load, until it reports its own."""
        self._state = {"settings_open": False, "chat_visible": True, "has_messages": False, "lang": "ar"}

    def update(self, state: dict | None):
        """Record the page's latest ``ui-state`` report."""
        if isinstance(state, dict):
            self._state.update({k: v for k, v in state.items() if k in self._state})

    async def _send(self, params: FunctionCallParams, action: str, **data):
        await params.llm.push_frame(RTVIServerMessageFrame(data={"kind": "screen", "action": action, **data}))

    async def _ensure_settings(self, params: FunctionCallParams):
        if not self._state["settings_open"]:
            await self._send(params, "open_settings")
            self._state["settings_open"] = True

    async def _ensure_main(self, params: FunctionCallParams):
        if self._state["settings_open"]:
            await self._send(params, "close_settings")
            self._state["settings_open"] = False

    @property
    def tools(self) -> list:
        """The tool functions to list in the LLM context."""

        async def open_settings(params: FunctionCallParams):
            """Open the settings, when the customer asks to go to the settings or options, or asks what they can change."""
            if self._state["settings_open"]:
                await self._send(params, "open_settings")
                hint = "الإعدادات مفتوحة أصلاً وتم تمييزها. قل ذلك باختصار."
            else:
                await self._ensure_settings(params)
                hint = "فُتحت الإعدادات على الشاشة. قل ذلك واذكر خيارين فقط: صوت المساعد والميكروفون."
            await params.result_callback({"done": True, "hint": hint})

        async def close_settings(params: FunctionCallParams):
            """Close the settings, when the customer asks to close them, go back, or return to the main screen."""
            if not self._state["settings_open"]:
                hint = "الإعدادات مغلقة أصلاً والعميل على الشاشة الرئيسية. قل ذلك باختصار."
            else:
                await self._ensure_main(params)
                hint = "أُغلقت الإعدادات. أكّد ذلك بكلمتين واسأل كيف تساعده."
            await params.result_callback({"done": True, "hint": hint})

        async def show_setting(params: FunctionCallParams, setting: str):
            """Show and highlight one option in the settings, when the customer asks where or how to change it.

            Args:
                setting (str): One of: "language" (interface language), "microphone" (which microphone), "volume" (assistant volume), "show_conversation" (show or hide the written conversation), "live_captions" (text appears while speaking), "start_muted" (start with the microphone muted), "conversation_history" (download or clear the conversation).
            """
            if setting not in SETTINGS:
                names = "، ".join(SETTINGS.values())
                hint = f"هذا الخيار غير موجود. قل للعميل بصراحة إنه غير متاح، والخيارات الموجودة: {names}."
                await params.result_callback({"done": False, "hint": hint})
                return
            await self._ensure_settings(params)
            await self._send(params, "show_setting", setting=setting)
            hint = f"خيار «{SETTINGS[setting]}» ظاهر ومميّز على الشاشة. قل له أين هو وكيف يغيّره بجملة واحدة."
            await params.result_callback({"done": True, "hint": hint})

        async def show_conversation(params: FunctionCallParams):
            """Show the written conversation, when the customer asks where the text of the conversation is or wants to see it."""
            if not self._state["chat_visible"]:
                await self._ensure_settings(params)
                await self._send(params, "show_setting", setting="show_conversation")
                hint = "المحادثة المكتوبة مخفية من الإعدادات. ظهر خيار «إظهار المحادثة» مميّزاً؛ قل له أن يفعّله ليراها."
            else:
                await self._ensure_main(params)
                await self._send(params, "show_conversation")
                hint = "المحادثة المكتوبة ظاهرة ومميّزة على الشاشة. قل ذلك باختصار."
            await params.result_callback({"done": True, "hint": hint})

        async def download_conversation(params: FunctionCallParams):
            """Download the written conversation as a file, when the customer asks for a copy of it."""
            if not self._state["has_messages"]:
                hint = "لا يوجد كلام مكتوب بعد لتنزيله. قل ذلك باختصار."
                await params.result_callback({"done": False, "hint": hint})
                return
            await self._send(params, "download_conversation")
            hint = "بدأ تنزيل ملف المحادثة في المتصفح. قل ذلك باختصار."
            await params.result_callback({"done": True, "hint": hint})

        async def clear_conversation(params: FunctionCallParams, confirmed: bool):
            """Clear the written conversation from the screen, when the customer asks to clear or delete it.

            Args:
                confirmed (bool): True only after the customer clearly said yes when you asked them to confirm. Otherwise False.
            """
            if not self._state["has_messages"]:
                hint = "المحادثة فارغة أصلاً. قل ذلك باختصار."
                await params.result_callback({"done": False, "hint": hint})
                return
            if not confirmed:
                hint = "لم يُمسح شيء. اسأل العميل: أكيد بدك تمسح المحادثة؟ وإذا وافق استدعِ الأداة مرة أخرى مع confirmed = true."
                await params.result_callback({"done": False, "hint": hint})
                return
            await self._ensure_main(params)
            await self._send(params, "clear_conversation")
            self._state["has_messages"] = False
            hint = "مُسحت المحادثة من الشاشة. أكّد ذلك بكلمتين."
            await params.result_callback({"done": True, "hint": hint})

        async def change_language(params: FunctionCallParams, language: str):
            """Change the language of the page's text, when the customer asks for the interface in Arabic or English.

            Args:
                language (str): "ar" for Arabic or "en" for English.
            """
            if language not in LANGUAGES:
                hint = "الواجهة متاحة بالعربية والإنجليزية فقط. قل ذلك باختصار."
                await params.result_callback({"done": False, "hint": hint})
                return
            if self._state["lang"] == language:
                hint = f"الواجهة أصلاً باللغة {LANGUAGES[language]}. قل ذلك باختصار."
                await params.result_callback({"done": True, "hint": hint})
                return
            await self._send(params, "change_language", lang=language)
            self._state["lang"] = language
            hint = f"صارت كتابة الواجهة باللغة {LANGUAGES[language]}. قل ذلك، وتابع الحديث بالعربية."
            await params.result_callback({"done": True, "hint": hint})

        return [
            open_settings,
            close_settings,
            show_setting,
            show_conversation,
            download_conversation,
            clear_conversation,
            change_language,
        ]
