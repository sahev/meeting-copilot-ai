# Meeting Copilot CLI

Meeting Copilot CLI captures real Windows output audio through WASAPI Loopback, transcribes Brazilian Portuguese audio locally with `faster-whisper`, and displays the live transcript in CMD/PowerShell using `rich`.

## Requirements

- Windows.
- Python 3.10 to 3.12. Python 3.14 is not recommended because PyAudioWPatch and ML runtime wheels may not be published for it yet.
- A working Windows output device.
- CPU or GPU resources for local Whisper transcription.

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
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
AI_PROVIDER=stackspot
STACKSPOT_API_URL=
STACKSPOT_API_KEY=
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

### Whisper model

Set `WHISPER_MODEL_SIZE` to a faster or more accurate model supported by faster-whisper, such as `tiny`, `base`, `small`, `medium`, or `large-v3`.

CPU example:

```env
WHISPER_MODEL_SIZE=small
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
STACKSPOT_API_URL=
STACKSPOT_API_KEY=
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

StackSpot and Devin use the generic JSON provider shape and send:

```json
{
  "prompt": "...",
  "payload": {}
}
```

Those endpoints must return either raw text or JSON containing one of these text fields: `output`, `content`, `text`, `message`, `answer`, or `response`.

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
- The generic StackSpot or Devin endpoint contract may need small adaptation depending on the exact API shape you use.
