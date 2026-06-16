# JASS

**JASS** (Just Another Smart Shell) is a modular, production-oriented local AI assistant for Linux—especially [Kali Linux](https://www.kali.org/)—that combines wake-word voice control, Ollama (Llama 3) reasoning, desktop automation, vision-driven empathy cues, SQLite memory, PyQt6 UI, and a FastAPI bridge for a mobile companion named **NED**.

## Features

- **Voice**: Wake word **“JASS”** via [Vosk](https://alphacephei.com/vosk/) + [PyAudio](https://people.csail.mit.edu/hubert/pyaudio/); STT via [SpeechRecognition](https://pypi.org/project/SpeechRecognition/) (Google Web API by default). TTS uses **pyttsx3** with a female-voice preference (Piper can be wired in as an alternate backend).
- **Brain**: [Ollama](https://ollama.com/) with **`llama3`** (configurable) for NL → structured actions (shell, visible UI automation, headless browser, spoken reply).
- **Habits**: Repeated commands (3×) auto-create **shortcuts** in SQLite.
- **Automation**: **Manual** mode ([PyAutoGUI](https://pyautogui.readthedocs.io/)—visible mouse/keyboard) vs **Background** mode ([Playwright](https://playwright.dev/python/) / HTTP).
- **Learning mode**: “JASS start learning” / “JASS stop learning” records **pynput** events to `tasks/*.json`; replay by name.
- **Vision**: Webcam loop ([OpenCV](https://opencv.org/)) + [DeepFace](https://github.com/serengil/deepface) / [MediaPipe](https://google.github.io/mediapipe/) for face/emotion; empathetic TTS on negative affect (rate-limited).
- **Memory**: SQLite tables `command_history`, `shortcuts`, `tasks`, `habits`, `knowledge`.
- **UI**: Animated **orb** (idle / listening / processing / speaking), top-center; **Ctrl+Space** starts listening if the mic path fails from wake-only flows; **dashboard** for status and logs.
- **Mobile sync**: FastAPI on **8756** — `GET /health`, **`GET /status`** (full diagnostics JSON), commands, WebSocket, uploads.
- **Bootstrap**: `main.py` runs `core/dep_bootstrap.py` to **pip-install** missing core wheels into the current interpreter (best-effort).
- **Concurrency**: Priority **task queue**, background workers, **psutil** monitoring.

## Requirements

- **Python 3.11+**
- **Linux** desktop with audio input, display (for PyQt6 orb), optional webcam.
- **[Ollama](https://ollama.com/)** installed and running, with a pulled model (e.g. `ollama pull llama3`).
- **Vosk model** for wake word: unpack under **`./vosk-model`** in the project root **or** set `JASS_VOSK_MODEL` to that directory. If missing, JASS shows an error dialog but you can still use **Ctrl+Space** or tray **Listen**.

### System packages (Debian / Kali examples)

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-pyaudio portaudio19-dev \
  libportaudio2 libasound2-dev ffmpeg \
  libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev
```

`PyAudio` wheels may be missing for your exact Python build; if `pip install PyAudio` fails, install `portaudio19-dev` (headers) first, or use the distro package `python3-pyaudio` inside your venv with `pip install --upgrade` only for other deps.

For Playwright browsers:

```bash
playwright install chromium
```

## Installation

```bash
cd jass
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Optional — heavier ML stack for DeepFace-based emotions:
# pip install -r requirements-vision-ml.txt
```

Wake listening (pick one):

```bash
# Option A — default path (directory must exist next to main.py)
mkdir -p vosk-model && unzip vosk-model-small-en-us-0.15.zip -d vosk-model

# Option B — env override
export JASS_VOSK_MODEL=/path/to/vosk-model-small-en-us-0.15
```

Optional:

```bash
export JASS_LANG=en          # en | hi | mr | ja
export JASS_OLLAMA_MODEL=llama3
export JASS_MOBILE_PORT=8756
export GITHUB_TOKEN=...      # for GitHub plugin
```

## Text-to-speech (replies)

If you see **`aplay: not found`** in the terminal, **pyttsx3** cannot play audio. JASS will **fall back to `espeak-ng`** automatically when that binary exists.

```bash
sudo apt install espeak-ng
# optional: force espeak and skip pyttsx3
export JASS_TTS_BACKEND=espeak
```

Replies are also logged as **`Assistant reply: …`** and shown in a **tray notification**.

## Speech-to-text (after “JASS”)

If the log shows **“Audio source must be entered before listening”**, update JASS — that bug is fixed by using the correct `with microphone as source:` pattern.

If you get **“could not understand audio”** or **no text**:

1. **English (online)** — default engine is **Google**. You need **Internet**. Speak clearly after the wake beep/listening state.
2. **Hindi / Marathi / Japanese** — set `JASS_LANG` to `hi`, `mr`, or `ja` (Google STT).
3. **Offline / same language as your Vosk model** — use Vosk for commands too:

   ```bash
   export JASS_STT_ENGINE=vosk
   ```

   Your `./vosk-model` must match the language you speak (e.g. English small model → English commands only).

## Run

```bash
source .venv/bin/activate
python main.py
```

### Typed commands (no microphone)

Open the **Dashboard** (tray icon) — top box **Command** + **Send**. Same brain as voice.

One-shot from terminal (no GUI; needs Ollama):

```bash
python main.py --text "what is 2+2"
# quiet audio:
JASS_NO_TTS=1 python main.py --text "hello"
```

Smoke test:

```bash
python tools/verify_jass.py
```

- The **floating orb** shows state; **tray icon** opens the dashboard and **Listen once**.
- With `./vosk-model` or `JASS_VOSK_MODEL`, the assistant listens for **“JASS”** in the Vosk stream; otherwise use **Ctrl+Space**, **Listen**, or the **NED** API.
- **NED** API: `GET /health`, **`GET /status`**, `POST /v1/command` (`{"text":"..."}`), `GET /v1/tasks`, `POST /v1/files/upload`, `ws://<host>:8756/ws`.

Logs: `~/.jass/logs/jass.log`  
Database: `~/.jass/jass.db`  
NED uploads: `~/.jass/ned_uploads/`

## Project layout

See the repository tree: `core/`, `voice/`, `brain/`, `automation/`, `vision/`, `memory/`, `plugins/`, `mobile_sync/`, `ui/`, `tasks/`, and `main.py`.

## Security note

The **security tools** plugin only allows a fixed set of CLI prefixes and rejects shell metacharacters. Still run JASS only in environments you trust; voice and mobile interfaces can trigger shell commands after LLM interpretation.

## License

Use and modify according to your organization’s policy; third-party libraries retain their own licenses.
