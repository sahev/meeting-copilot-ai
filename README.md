# Meeting Copilot CLI

Meeting Copilot CLI captures real Windows output audio through WASAPI Loopback, transcribes Brazilian Portuguese audio locally with `faster-whisper` or `Vosk`, and displays the live transcript in CMD/PowerShell using `rich`.

## Requirements

- Windows.
- Python 3.10 to 3.12. Python 3.14 is not recommended because PyAudioWPatch and ML runtime wheels may not be published for it yet.
- A working Windows output device.
- CPU or GPU resources for local transcription.

The app does not require external `.exe`, `.msi`, drivers, or desktop software. Python packages are installed with `pip`.

## Install

From this folder:

```powershell
pip install -r requirements.txt
```

Copy the example environment file if you want to customize settings:

```powershell
Copy-Item .env.example .env
```

## Run

From this folder:

```powershell
python -m app.main
```

Choose `start meeting` to start real WASAPI Loopback capture immediately. Press `Ctrl+C` while the live screen is running to finish the current meeting and return to the menu.

Logs are written to `meeting_copilot.log`.

Meeting data is written to `meeting_copilot.db`. Final summaries are written to the `summaries` folder.

Use `check env` from the menu to check Python version, installed packages, prompt files, AI provider configuration, SQLite write access, summary write access, and WASAPI Loopback device detection before starting a real meeting.

## Configuration

All settings are optional unless noted.

```env
MEETING_TOPIC=
AUDIO_CHUNK_SECONDS=5
AUDIO_FRAMES_PER_BUFFER=1024
AUDIO_SILENCE_RMS_THRESHOLD=120
WHISPER_MODEL_SIZE=small
TRANSCRIPTION_PROVIDER=faster_whisper
WHISPER_LANGUAGE=pt
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
VOSK_MODEL_PATH=models/vosk-model-small-pt-0.3
AI_PROVIDER=stackspot
STACKSPOT_AUTH_URL=https://idm.stackspot.com/YOUR_ACCOUNT_REALM/oidc/oauth/token
STACKSPOT_CLIENT_ID=
STACKSPOT_CLIENT_SECRET=
STACKSPOT_AGENT_URL=https://genai-inference-app.stackspot.com
STACKSPOT_AGENT_ID=
STACKSPOT_USE_CONVERSATION=false
STACKSPOT_STREAMING=false
DEVIN_API_URL=
DEVIN_API_KEY=
GEMINI_API_URL=https://generativelanguage.googleapis.com/v1beta
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
GROQ_API_URL=https://api.groq.com/openai/v1/chat/completions
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
QUESTION_GENERATION_INTERVAL_SECONDS=30
DATABASE_PATH=meeting_copilot.db
SUMMARIES_DIR=summaries
```

### Transcription provider

Use `TRANSCRIPTION_PROVIDER=faster_whisper` for best quality when the faster-whisper model can be downloaded or copied locally.

Use `TRANSCRIPTION_PROVIDER=vosk` when Hugging Face or large model files are blocked in your environment. Vosk runs offline with a much smaller Portuguese/Brazilian Portuguese model:

```env
TRANSCRIPTION_PROVIDER=vosk
VOSK_MODEL_PATH=models/vosk-model-small-pt-0.3
```

Download `vosk-model-small-pt-0.3.zip`, extract it, and point `VOSK_MODEL_PATH` to the extracted folder. The official Vosk model list reports this small pt-BR model at about 31 MB.

### Whisper model

Set `WHISPER_MODEL_SIZE` to a faster or more accurate model supported by faster-whisper, such as `tiny`, `base`, `small`, `medium`, or `large-v3`.

Set `WHISPER_LANGUAGE` to the language code used by faster-whisper. The default is `pt` for Brazilian Portuguese meetings. Examples: `pt`, `en`, `es`.
The app automatically builds a generic technical-meeting prompt using `WHISPER_LANGUAGE`, for example Brazilian Portuguese for `pt`, English for `en`, or Spanish for `es`.

CPU example:

```env
WHISPER_MODEL_SIZE=small
WHISPER_LANGUAGE=pt
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

CUDA example:

```env
WHISPER_MODEL_SIZE=medium
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
```

### Audio chunk size

`AUDIO_CHUNK_SECONDS` controls how much audio is captured before a transcription pass. The default is `10`.

### Silence filtering

`AUDIO_SILENCE_RMS_THRESHOLD` ignores low-volume chunks before sending audio to Whisper. Raise it if background noise is transcribed. Lower it if quiet speakers are ignored.

### AI providers

Structured context and generated questions require a real AI provider. If no matching provider URL, API key, and model are configured, the app displays an error and stops instead of running a simulated path.

```env
AI_PROVIDER=stackspot
STACKSPOT_AUTH_URL=https://idm.stackspot.com/YOUR_ACCOUNT_REALM/oidc/oauth/token
STACKSPOT_CLIENT_ID=
STACKSPOT_CLIENT_SECRET=
STACKSPOT_AGENT_URL=https://genai-inference-app.stackspot.com
STACKSPOT_AGENT_ID=
STACKSPOT_USE_CONVERSATION=false
STACKSPOT_STREAMING=false
```

Select Devin by setting:

```env
AI_PROVIDER=devin
DEVIN_API_URL=
DEVIN_API_KEY=
```

Select Gemini by setting:

```env
AI_PROVIDER=gemini
GEMINI_API_URL=https://generativelanguage.googleapis.com/v1beta
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
```

Select Groq by setting:

```env
AI_PROVIDER=groq
GROQ_API_URL=https://api.groq.com/openai/v1/chat/completions
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
```

StackSpot uses the official Agent API flow: it exchanges `STACKSPOT_CLIENT_ID` and `STACKSPOT_CLIENT_SECRET` for an access token at `STACKSPOT_AUTH_URL`, then calls:

```text
POST {STACKSPOT_AGENT_URL}/v1/agent/{STACKSPOT_AGENT_ID}/chat
```

The request sends `user_prompt`, `stackspot_knowledge`, `return_ks_in_response`, and `streaming`. Keep `STACKSPOT_STREAMING=false` unless you adapt the app to consume SSE streams. Set `STACKSPOT_USE_CONVERSATION=true` if you want the provider to store the returned `conversation_id` and reuse it on later calls in the same process.

Devin uses the generic JSON provider shape and sends:

```json
{
  "prompt": "...",
  "payload": {}
}
```

The Devin endpoint must return either raw text or JSON containing one of these text fields: `output`, `content`, `text`, `message`, `answer`, or `response`.

Gemini uses the Google `generateContent` REST shape. Groq uses the OpenAI-compatible chat completions shape.

### Question generation interval

`QUESTION_GENERATION_INTERVAL_SECONDS` controls how often the app asks the AI provider for new useful questions after context changes. The default is `30`.

### Persistence

`DATABASE_PATH` controls where SQLite data is saved. The database stores meetings, transcriptions, structured context snapshots, generated questions, and final summaries.

`SUMMARIES_DIR` controls where final Markdown summary files are written after the meeting ends.

## Current limitations

- Requires Windows WASAPI Loopback.
- Transcription quality depends on meeting audio quality.
- Local transcription consumes CPU or GPU.
- The first Whisper run may download model files through faster-whisper.
- Vosk is lighter and easier to move through restricted networks, but transcription quality is usually lower than Whisper.
- The generic Devin endpoint contract may need small adaptation depending on the exact API shape you use.
