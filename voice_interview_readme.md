# Voice-Based Mock Interview System

This documentation describes the architecture, data flow, and fallback systems implemented for the real-time voice recording and speech-to-text (STT) capabilities within the Mock Interview module.

---

## 1. Architectural Components

```
┌────────────────────────────────────────────────────────┐
│                      Client Browser                    │
│   ├── UI (static/app.js)                               │
│   ├── Audio Recorder (MediaRecorder API)               │
│   └── local Worker (static/whisper-worker.js)          │
└──────────────────────────┬─────────────────────────────┘
                           │ POST /api/v1/interview/{id}/answer/voice
                           ▼
┌────────────────────────────────────────────────────────┐
│                     FastAPI Server                     │
│   └── Route Handler (routes/interviews.py)             │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│                Audio Transcriber Service               │
│   └── services/audio_transcriber.py                    │
└──────────────────────────┬─────────────────────────────┘
                           │
             ┌─────────────┴─────────────┐
             ▼ (If OPENAI_API_KEY set)    ▼ (If Whisper offline/unset)
┌──────────────────────────┐   ┌──────────────────────────┐
│    OpenAI Whisper API    │   │  Local Browser Fallback  │
│    (whisper-1 Cloud)     │   │  (In-Browser Transcript) │
└──────────────────────────┘   └──────────────────────────┘
```

The system comprises three key layers:
1. **Frontend (Browser Client)**: Handles user media permission access, microphone recording, local real-time transcription, and payload bundling.
2. **Backend API Router**: Exposes structured API endpoints for processing audio forms and updating database sessions.
3. **Audio Transcriber Service**: Implements transcription routing logic to balance accuracy (cloud Whisper) and zero-cost offline availability (client-side worker).

---

## 2. Interactive Data Flow

### 1. Recording Session Initialization
- The user selects a candidate profile, role, and clicks **Start Interview**.
- When the first question loads, clicking the **🎙️ Mic** icon requests permission for the audio input stream:
  ```javascript
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  ```

### 2. Live Local Transcription & Recording
- A `MediaRecorder` instance captures audio chunks in `audio/webm` format.
- Every **~3 seconds**, current audio chunks are compiled into a temporary Blob and sent to a local Web Worker (`static/whisper-worker.js`) running a browser-based ONNX model (Transformers.js) for real-time transcription.
- The UI updates dynamically to show the candidate what they are saying in real time.

### 3. Stop and Upload
- When the candidate clicks **Stop Voice Answer**:
  - The recording stops and compiles the final audio Blob.
  - The frontend formats a `FormData` object containing the complete audio file (`answer_q<index>.webm`) and the locally captured text transcript (`live_transcript`).
  - It triggers a `POST` request to `/api/v1/interview/{interview_id}/answer/voice`.

### 4. Server-Side Processing & Fallback Routing
Upon receiving the payload, the backend routes execution to [services/audio_transcriber.py](file:///d:/Fxis.ai/Crewai/services/audio_transcriber.py):
- **Condition A (Cloud Transcription)**: If `OPENAI_API_KEY` is present in the environment (and is a valid OpenAI key, not an OpenRouter proxy key):
  - The audio bytes are saved to a temporary local file.
  - The file is sent directly to the OpenAI Whisper API (`whisper-1`).
  - Silent/noisy audio hallucinations (e.g. *"thank you"* or *"thank you for watching"*) are cleaned and rejected.
- **Condition B (Local Fallback)**: If no OpenAI key is set, the API request fails, or network is offline:
  - The transcriber service logs a warning and falls back to using the `live_transcript` provided by the browser's client-side transcription engine.

### 5. DB Ingestion & Sequence Step
- The finalized transcript text is stored in the `user_response` field of the `interview_qa_logs` table for the corresponding question.
- The state machine advances `current_index` on the `mock_interviews` session.
- The API replies with a `VoiceAnswerResponse` JSON containing the resolved transcript text and state progression flag `has_next`.

---

## 3. API Reference

### Submit Voice Answer
Submit an audio recording for the current question in an active interview session.

- **URL**: `/api/v1/interview/{interview_id}/answer/voice`
- **Method**: `POST`
- **Content-Type**: `multipart/form-tdata`

#### Parameters:
| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `file` | Binary Blob | Yes | The `.webm` or `.wav` audio recording file. |
| `live_transcript` | String | No | The client-side transcribed text (for fallback). |

#### Response Schema (`VoiceAnswerResponse`):
```json
{
  "status": "RECORDED",
  "interview_id": "8fa7d45c-2834-45fb-a872-9b2ee3d12d45",
  "question_number": 2,
  "transcript": "In my previous role, I designed a microservices architecture using FastAPI...",
  "has_next": true,
  "next_question_number": 3
}
```

---

## 4. Key Files to Reference

- **Frontend Controller**: [static/app.js](file:///d:/Fxis.ai/Crewai/static/app.js) - Manages recording buttons, MediaRecorder event loop, and UI state.
- **Web Worker**: [static/whisper-worker.js](file:///d:/Fxis.ai/Crewai/static/whisper-worker.js) - Instantiates browser-based Transformers.js Whisper.
- **Route Handler**: [routes/interviews.py](file:///d:/Fxis.ai/Crewai/routes/interviews.py) - Exposes `/answer/voice`.
- **Transcriber Service**: [services/audio_transcriber.py](file:///d:/Fxis.ai/Crewai/services/audio_transcriber.py) - Core logic for routing audio to Whisper vs local fallbacks.
