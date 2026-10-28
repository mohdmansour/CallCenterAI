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
| `Dockerfile` | Builds the bot for hosting (Railway or any Docker host) |
| `vercel.json` | Publishes the `ui/` folder on Vercel |

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

## Deploy online

The project is split across three services:

| Part | Where | Why |
| --- | --- | --- |
| Page (`ui/`) | Vercel (optional) | Static files. The bot also serves the page itself, so Vercel only adds a separate address. |
| Bot | Railway | Needs a process that stays running for the whole call. Built from the `Dockerfile`. |
| Voice | A TURN server | Railway only lets web traffic in, so the call audio is relayed through TURN. |

### 1. TURN server

Create an account with any TURN provider (for example Metered or Cloudflare Realtime TURN) and note its server addresses, username and password.

The bot hands these settings to every visitor's browser, which needs them to connect. Anyone who opens the page can read them, so use credentials meant for this, and keep an eye on the provider's usage limits.

### 2. Bot on Railway

1. In Railway, create a project with **Deploy from GitHub repo** and pick this repository. Railway builds it from the `Dockerfile`.
2. Under **Variables**, add:
   - `OPENAI_API_KEY`: your OpenAI key
   - `PIPECAT_ICE_SERVERS`: the TURN settings as a JSON array, on one line, for example:

     ```json
     [{"urls":"stun:stun.example.com:3478"},{"urls":["turn:turn.example.com:80","turn:turn.example.com:443?transport=tcp"],"username":"YOUR_USERNAME","credential":"YOUR_PASSWORD"}]
     ```

3. Under **Settings → Networking**, click **Generate Domain**.
4. Open that address. The Lamsa page loads, and the call should connect.

### 3. Page on Vercel (optional)

1. In `ui/index.html`, put the Railway address in the `lamsa-bot-url` meta tag, for example `content="https://your-bot.up.railway.app"`, then commit and push.
2. In Vercel, **Add New → Project**, import this repository and deploy. `vercel.json` publishes only the `ui/` folder; nothing else is built.

Without step 1 the page still loads, but it can't find the bot. For a quick test, add `?bot=https://your-bot.up.railway.app` to the Vercel address instead.
