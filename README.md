# Meeting Copilot CLI

Meeting Copilot CLI captures real Windows output audio through WASAPI Loopback, transcribes Brazilian Portuguese audio locally with `faster-whisper`, and displays the live transcript in CMD/PowerShell using `rich`.

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
WHISPER_MODEL_PATH=models/faster-whisper-small
TRANSCRIPTION_PROVIDER=faster_whisper
WHISPER_LANGUAGE=pt
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
AI_PROVIDER=stackspot
STACKSPOT_AUTH_URL=https://idm.stackspot.com/YOUR_ACCOUNT_REALM/oidc/oauth/token
STACKSPOT_CLIENT_ID=
STACKSPOT_CLIENT_SECRET=
STACKSPOT_AGENT_URL=https://genai-inference-app.stackspot.com
STACKSPOT_AGENT_ID=
STACKSPOT_USE_CONVERSATION=false
STACKSPOT_STREAMING=false
GROQ_API_URL=https://api.groq.com/openai/v1/chat/completions
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
CONTEXT_REFRESH_INTERVAL_SECONDS=30
QUESTION_CONTEXT_SNAPSHOT_LIMIT=3
DATABASE_PATH=meeting_copilot.db
SUMMARIES_DIR=summaries
```

### Transcription provider

Use `TRANSCRIPTION_PROVIDER=faster_whisper` for best quality with the local faster-whisper model copied into `models/faster-whisper-small`.

### Whisper model

Set `WHISPER_MODEL_PATH` to a local faster-whisper model folder, such as `models/faster-whisper-small`.
`WHISPER_MODEL_SIZE` is still accepted as a fallback for faster-whisper model names such as `tiny`, `base`, `small`, `medium`, or `large-v3`.

Set `WHISPER_LANGUAGE` to the language code used by faster-whisper. The default is `pt` for Brazilian Portuguese meetings. Examples: `pt`, `en`, `es`.
The app automatically builds a generic technical-meeting prompt using `WHISPER_LANGUAGE`, for example Brazilian Portuguese for `pt`, English for `en`, or Spanish for `es`.

CPU example:

```env
WHISPER_MODEL_PATH=models/faster-whisper-small
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

Groq uses the OpenAI-compatible chat completions shape.

### Context and question generation

`CONTEXT_REFRESH_INTERVAL_SECONDS` controls how often the app sends the accumulated transcript text to the AI provider to update the structured meeting context. The default is `30`.

Questions are generated only on demand. While a meeting is running, press `F8` or `Ctrl+G` to send the recent structured context to the AI provider. The `STATUS` panel shows when the context was sent and when questions return.

`QUESTION_CONTEXT_SNAPSHOT_LIMIT` controls how many recent context snapshots are used for on-demand question generation. The default is `3`.

`QUESTION_GENERATION_INTERVAL_SECONDS` is still accepted as a fallback for older `.env` files, but question generation itself is no longer automatic.

### Persistence

`DATABASE_PATH` controls where SQLite data is saved. The database stores meetings, transcriptions, structured context snapshots, generated questions, and final summaries.

`SUMMARIES_DIR` controls where final Markdown summary files are written after the meeting ends.

## Current limitations

- Requires Windows WASAPI Loopback.
- Transcription quality depends on meeting audio quality.
- Local transcription consumes CPU or GPU.
- The first Whisper run may download model files through faster-whisper only when using `WHISPER_MODEL_SIZE` instead of `WHISPER_MODEL_PATH`.
