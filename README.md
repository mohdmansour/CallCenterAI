# CallCenterAI

An Arabic voice assistant for **Lamsa (لمسة)**, a design and digital-marketing studio. Customers talk to it in the browser and it answers out loud, using the company information in `knowledge.txt`. Built with [Pipecat](https://github.com/pipecat-ai/pipecat) and OpenAI (speech-to-text, GPT-4.1, text-to-speech).

> Lamsa is a fictional company. All the company data in this project is made up for demo purposes.

## Features

- Real-time voice conversation in Arabic (Levantine-friendly), with interruptions
- Answers only from `knowledge.txt`, and says so when it doesn't know
- Custom Lamsa web interface (`ui/`):
  - live written transcript of both sides of the conversation
  - mute / unmute button (shortcut: `M`)
  - settings: language (Arabic / English), microphone, assistant volume, transcript options
  - download or clear the conversation

## Project files

| File | Purpose |
| --- | --- |
| `demo_openai1.py` | The voice bot and the web server |
| `knowledge.txt` | Everything the assistant knows about the company |
| `ui/` | The Lamsa web interface |
| `start-lamsa.bat` | Starts the bot and opens the browser (Windows) |
| `test_knowledge.py` | Text-only check of the assistant's answers, no microphone needed |
| `lamsa-brand.md` | Brand brief: colours, typography, voice |
| `marketing/` | Social media post and story images |

## Setup

Requires Python 3.11 or newer.

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Then open `.env` and put your OpenAI API key after `OPENAI_API_KEY=`.

## Run

Double-click `start-lamsa.bat`, or run:

```bash
.venv\Scripts\python.exe demo_openai1.py
```

Then open <http://localhost:7860> and press **ابدأ المحادثة**. Pipecat's own developer interface stays available at <http://localhost:7860/client>.

To check the assistant's answers without talking to it:

```bash
.venv\Scripts\python.exe test_knowledge.py
```

## Changing what the assistant knows

Edit `knowledge.txt` and restart the bot. No code changes are needed.
