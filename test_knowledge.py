"""Text-only check of the Lamsa voice bot's brain.

Sends written questions to the same model (gpt-4.1) with the same system
instruction the bot uses, then prints the answers. No microphone needed.

Run from the folder that holds demo_openai1.py, knowledge.txt and .env:
    .venv\\Scripts\\python.exe test_knowledge.py
"""

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
load_dotenv(HERE / ".env", override=True)

# Reuse the exact prompt the bot builds from knowledge.txt.
bot_module = "demo_openai1" if (HERE / "demo_openai1.py").exists() else "demo_openai"
SYSTEM_INSTRUCTION = __import__(bot_module).SYSTEM_INSTRUCTION

# (question, words that should appear in a correct answer; empty = just read it)
QUESTIONS = [
    ("كم سعر تصميم شعار؟", ["350"]),
    ("متى ساعات الدوام؟", ["التاسعة", "9", "الخامسة", "5"]),
    ("هل عندكم خصم للمشاريع الناشئة؟", ["15"]),
    ("وين مقركم؟", ["الجاردنز", "عمّان", "عمان"]),
    ("مين مديرة الشركة؟", ["ليلى"]),
    ("هل عندكم فرع في دبي؟", []),
    ("كم عدد العملاء الذين تعاملتم معهم؟", []),
]


def ask(client: httpx.Client, question: str) -> str:
    response = client.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={
            "model": "gpt-4.1",
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": question},
            ],
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is empty. Put your key in the .env file first.")

    passed = 0
    checked = 0
    with httpx.Client() as client:
        for question, expected in QUESTIONS:
            answer = ask(client, question)
            if expected:
                checked += 1
                ok = any(word in answer for word in expected)
                passed += ok
                mark = "OK  " if ok else "FAIL"
            else:
                mark = "READ"
            print(f"[{mark}] السؤال: {question}\n       الجواب: {answer}\n")
    print(f"Checked answers: {passed}/{checked} contain the expected fact.")
    print("Lines marked READ have no fixed answer; read them yourself.")


if __name__ == "__main__":
    main()
