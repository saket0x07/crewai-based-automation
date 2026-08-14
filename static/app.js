function initApp() {
  // Application State
  let currentInterviewId = null;
  let currentDocumentId = null;
  let totalQuestions = 5;
  let currentQuestionIndex = 0;
  
  // MediaRecorder & SpeechRecognition state
  let mediaRecorder = null;
  let audioChunks = [];
  let recordingTimerInterval = null;
  let recordingSeconds = 0;
  let whisperWorker = null;
  let capturedLiveTranscript = "";
  let audioContext = null;

  // Initialize browser SpeechRecognition
  let recognition = null;
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onresult = (event) => {
      let fullTranscript = '';
      for (let i = 0; i < event.results.length; ++i) {
        fullTranscript += event.results[i][0].transcript + ' ';
      }
      const combined = fullTranscript.trim();
      if (combined) {
        capturedLiveTranscript = combined;
        transcriptText.textContent = `"${capturedLiveTranscript}"`;
        transcriptContainer.classList.remove("hidden");
      }
    };

    recognition.onend = () => {
      if (btnMic && btnMic.classList.contains("recording")) {
        try {
          recognition.start();
        } catch (e) {
          // Already started
        }
      }
    };

    recognition.onerror = (event) => {
      console.warn("Speech recognition error:", event.error);
    };
  }

  // Initialize Whisper Web Worker
  whisperWorker = new Worker('/static/whisper-worker.js', { type: 'module' });
  whisperWorker.onmessage = (event) => {
    const { type, text, isFinal, data } = event.data;
    if (type === 'result' && text) {
      // Only set from worker if SpeechRecognition didn't produce a better transcript
      if (!capturedLiveTranscript) {
        capturedLiveTranscript = text.trim();
        transcriptText.textContent = `"${capturedLiveTranscript}"`;
        transcriptContainer.classList.remove("hidden");
      }
    } else if (type === 'progress') {
      if (data.status === 'progress') {
         recordingStatus.textContent = `Loading AI Model... ${Math.round(data.progress)}%`;
      } else if (data.status === 'ready') {
         recordingStatus.textContent = "AI Model Ready. 🎙️ Recording Audio Answer... Speak now!";
      }
    }
  };

  // DOM Elements
  const stepSetup = document.getElementById("step-setup");
  const stepQuestion = document.getElementById("step-question");
  const stepEvaluation = document.getElementById("step-evaluation");

  const candidateSelect = document.getElementById("candidate-select");
  const resumeFileInput = document.getElementById("resume-file");
  const targetRoleInput = document.getElementById("target-role");
  const numQuestionsSelect = document.getElementById("num-questions");
  const difficultySelect = document.getElementById("difficulty-level");
  const focusSelect = document.getElementById("focus-area");
  const btnStartInterview = document.getElementById("btn-start-interview");

  const questionCategory = document.getElementById("question-category");
  const questionProgress = document.getElementById("question-progress");
  const progressBar = document.getElementById("progress-bar");
  const questionText = document.getElementById("question-text");

  const btnMic = document.getElementById("btn-mic");
  const btnStopVoice = document.getElementById("btn-stop-voice");
  const btnSkip = document.getElementById("btn-skip");
  const recordingStatus = document.getElementById("recording-status");
  const recordingTimer = document.getElementById("recording-timer");

  const transcriptContainer = document.getElementById("transcript-container");
  const transcriptText = document.getElementById("transcript-text");
  
  const textAnswerInput = document.getElementById("text-answer-input");
  const btnSubmitText = document.getElementById("btn-submit-text");

  const evalScore = document.getElementById("eval-score");
  const evalStrengths = document.getElementById("eval-strengths");
  const evalWeaknesses = document.getElementById("eval-weaknesses");
  const evalAreas = document.getElementById("eval-areas");
  const evalReport = document.getElementById("eval-report");
  const btnRestart = document.getElementById("btn-restart");

  // 1. Fetch Existing Candidates
  async function loadCandidates() {
    try {
      const res = await fetch("/api/v1/resumes/");
      if (!res.ok) throw new Error(await res.text());
      const candidates = await res.json();
      
      if (Array.isArray(candidates) && candidates.length > 0) {
        candidateSelect.innerHTML = candidates.map(c => 
          `<option value="${c.document_id}">${c.candidate_name} (${c.filename})</option>`
        ).join("");
      } else {
        candidateSelect.innerHTML = `<option value="">-- No saved candidates found. Upload a resume below --</option>`;
      }
    } catch (e) {
      console.warn("Error loading candidates from backend:", e);
      candidateSelect.innerHTML = `<option value="">-- No saved candidates found. Upload a resume below --</option>`;
    }
  }
  loadCandidates();
  if (candidateSelect) {
    candidateSelect.addEventListener("focus", loadCandidates, { once: true });
  }



  // 2. Handle Resume File Upload
  async function uploadResumeFile() {
    const file = resumeFileInput.files[0];
    if (!file) return null;

    const formData = new FormData();
    formData.append("file", file);

    btnStartInterview.disabled = true;
    btnStartInterview.textContent = "⏳ Uploading & Parsing Resume...";

    try {
      const res = await fetch("/api/v1/resumes/upload", {
        method: "POST",
        body: formData
      });

      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      return data.document_id;
    } catch (e) {
      alert("Error uploading resume: " + e.message);
      return null;
    } finally {
      btnStartInterview.disabled = false;
      btnStartInterview.textContent = "🚀 Start Mock Interview Session";
    }
  }

  // 3. Start Mock Interview Session
  btnStartInterview.addEventListener("click", async () => {
    let docId = candidateSelect.value;
    
    if (resumeFileInput.files.length > 0) {
      const uploadedId = await uploadResumeFile();
      if (!uploadedId) return;
      docId = uploadedId;
    } else if (!docId || docId.startsWith("mock-")) {
      // Re-fetch candidates from backend to get a valid real document_id
      try {
        const res = await fetch("/api/v1/resumes/");
        if (res.ok) {
          const candidates = await res.json();
          if (Array.isArray(candidates) && candidates.length > 0) {
            docId = candidates[0].document_id;
          }
        }
      } catch (e) {
        console.warn("Fallback candidate fetch failed:", e);
      }
    }

    if (!docId || docId.startsWith("mock-")) {
      alert("No saved candidate resume found in system. Please upload a resume file (.pdf, .docx, .txt) below to start!");
      return;
    }

    currentDocumentId = docId;
    const targetRole = targetRoleInput.value.trim() || "AI Engineer";
    totalQuestions = parseInt(numQuestionsSelect.value, 10);
    const difficultyLevel = difficultySelect ? difficultySelect.value : "Mid";
    const focusArea = focusSelect ? focusSelect.value : "Full Mix";

    btnStartInterview.disabled = true;
    btnStartInterview.textContent = "⚙️ Generating Customized Questions via CrewAI...";

    try {
      const res = await fetch("/api/v1/interview/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_id: currentDocumentId,
          num_questions: totalQuestions,
          target_role: targetRole,
          difficulty_level: difficultyLevel,
          focus_area: focusArea
        })
      });

      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      currentInterviewId = data.interview_id;
      totalQuestions = data.total_questions;

      stepSetup.classList.add("hidden");
      stepQuestion.classList.remove("hidden");

      loadNextQuestion();
    } catch (e) {
      alert("Failed to start interview: " + e.message);
    } finally {
      btnStartInterview.disabled = false;
      btnStartInterview.textContent = "🚀 Start Mock Interview Session";
    }
  });

  // 4. Fetch Next Question State
  async function loadNextQuestion() {
    resetRecordingUI();
    transcriptContainer.classList.add("hidden");
    textAnswerInput.value = "";

    try {
      const res = await fetch(`/api/v1/interview/${currentInterviewId}/next`);
      if (!res.ok) throw new Error(await res.text());
      const qData = await res.json();

      if (qData.is_completed) {
        finalizeAndShowEvaluation();
        return;
      }

      currentQuestionIndex = qData.question_number;
      questionCategory.textContent = (qData.question_category || "Technical").toUpperCase();
      questionProgress.textContent = `Question ${currentQuestionIndex} of ${totalQuestions}`;
      questionText.textContent = qData.question_text;

      const progressPercent = (currentQuestionIndex / totalQuestions) * 100;
      progressBar.style.width = `${progressPercent}%`;
    } catch (e) {
      alert("Error loading question: " + e.message);
    }
  }


  // 5. Microphone Recording Logic
  btnMic.addEventListener("click", startRecording);
  btnStopVoice.addEventListener("click", stopAndSubmitVoiceRecording);

  async function processAudioBuffer(audioBlob, isFinal) {
    if (!audioContext) audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    try {
      const arrayBuffer = await audioBlob.arrayBuffer();
      const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
      const float32Array = audioBuffer.getChannelData(0);
      whisperWorker.postMessage({ type: 'transcribe', audio: float32Array, isFinal });
    } catch (err) {
      console.warn("Audio decode warning:", err);
    }
  }

  async function startRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      alert("Microphone access is not supported in your browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      capturedLiveTranscript = "";
      
      // Start browser SpeechRecognition if available
      if (recognition) {
        try {
          recognition.start();
        } catch (recognitionError) {
          console.warn("SpeechRecognition start error:", recognitionError);
        }
      }

      mediaRecorder = new MediaRecorder(stream);

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
           audioChunks.push(event.data);
        }
      };

      mediaRecorder.start(100);

      // UI state during recording
      btnMic.classList.add("recording");
      btnStopVoice.classList.remove("hidden");
      recordingStatus.textContent = "🎙️ Recording Audio Answer... Speak now!";
      recordingStatus.style.color = "var(--danger)";

      recordingSeconds = 0;
      recordingTimer.textContent = "00:00";
      clearInterval(recordingTimerInterval);
      recordingTimerInterval = setInterval(() => {
        recordingSeconds++;
        const mins = String(Math.floor(recordingSeconds / 60)).padStart(2, '0');
        const secs = String(recordingSeconds % 60).padStart(2, '0');
        recordingTimer.textContent = `${mins}:${secs}`;
      }, 1000);

    } catch (e) {
      alert("Microphone permission denied or unavailable: " + e.message);
    }
  }

  function resetRecordingUI() {
    if (recognition) {
      try {
        recognition.stop();
      } catch (recognitionError) {
        // Already stopped or not started
      }
    }
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
      if (mediaRecorder.stream) {
        mediaRecorder.stream.getTracks().forEach(track => track.stop());
      }
    }
    clearInterval(recordingTimerInterval);
    btnMic.classList.remove("recording");
    btnStopVoice.classList.add("hidden");
    recordingStatus.textContent = "Click Mic to Start Answering";
    recordingStatus.style.color = "var(--text-main)";
    recordingTimer.textContent = "00:00";
  }

  async function stopAndSubmitVoiceRecording() {
    if (!mediaRecorder || mediaRecorder.state === "inactive") return;

    recordingStatus.textContent = "⚡ Processing & Saving Speech Transcript...";
    recordingStatus.style.color = "var(--accent)";
    btnStopVoice.disabled = true;

    // Stop SpeechRecognition to finalize the transcript
    if (recognition) {
      try {
        recognition.stop();
      } catch (recognitionError) {
        console.warn("SpeechRecognition stop error:", recognitionError);
      }
    }

    mediaRecorder.stop();
    if (mediaRecorder.stream) {
      mediaRecorder.stream.getTracks().forEach(track => track.stop());
    }
    clearInterval(recordingTimerInterval);

    const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
    recordingStatus.textContent = "⚡ Finalizing Speech Transcript...";
    
    // Process final audio buffer with Whisper worker
    processAudioBuffer(audioBlob, true);

    // Wait for the transcript to be captured (up to 1.5 seconds) before sending to server
    let checks = 0;
    const intervalId = setInterval(async () => {
      checks++;
      if (capturedLiveTranscript || checks >= 15) {
        clearInterval(intervalId);
        
        const formData = new FormData();
        formData.append("file", audioBlob, `answer_q${currentQuestionIndex}.webm`);
        if (capturedLiveTranscript) {
          formData.append("live_transcript", capturedLiveTranscript);
        }

        try {
          const res = await fetch(`/api/v1/interview/${currentInterviewId}/answer/voice`, {
            method: "POST",
            body: formData
          });

          if (!res.ok) throw new Error(await res.text());
          const data = await res.json();

          // Render Real-Time Transcript in UI
          transcriptText.textContent = `"${data.transcript}"`;
          transcriptContainer.classList.remove("hidden");

          btnStopVoice.disabled = false;
          resetRecordingUI();

          // Proceed to next question after 1.5 seconds so user reads transcript
          setTimeout(() => {
            if (data.has_next) {
              loadNextQuestion();
            } else {
              finalizeAndShowEvaluation();
            }
          }, 1500);

        } catch (e) {
          alert("Error submitting voice answer: " + e.message);
          btnStopVoice.disabled = false;
          resetRecordingUI();
        }
      }
    }, 100);
  }


  // 6. Text Answer Submit (Fallback)
  btnSubmitText.addEventListener("click", async () => {
    const text = textAnswerInput.value.trim();
    if (!text) return;

    try {
      const res = await fetch(`/api/v1/interview/${currentInterviewId}/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ response_text: text, proceed: true })
      });

      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();

      if (data.has_next) {
        loadNextQuestion();
      } else {
        finalizeAndShowEvaluation();
      }
    } catch (e) {
      alert("Error submitting text answer: " + e.message);
    }
  });

  // 7. Skip Question
  btnSkip.addEventListener("click", async () => {
    try {
      const res = await fetch(`/api/v1/interview/${currentInterviewId}/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ response_text: "", proceed: false })
      });

      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();

      if (data.has_next) {
        loadNextQuestion();
      } else {
        finalizeAndShowEvaluation();
      }
    } catch (e) {
      alert("Error skipping question: " + e.message);
    }
  });

  // 8. Finalize Interview & Render Scorecard Evaluation Report
  async function finalizeAndShowEvaluation() {
    stepQuestion.classList.add("hidden");
    stepEvaluation.classList.remove("hidden");

    evalScore.textContent = "--";
    evalReport.textContent = "CrewAI InterviewEvaluatorAgent is scoring transcript... Please wait.";

    try {
      const res = await fetch(`/api/v1/interview/${currentInterviewId}/finalize`, {
        method: "POST"
      });

      if (!res.ok) throw new Error(await res.text());
      const report = await res.json();

      const rawScore = Number(report.overall_score) || 8.0;
      const normalizedScore = rawScore <= 10.0 ? Math.round(rawScore * 10) : Math.round(rawScore);
      evalScore.textContent = normalizedScore;
      
      renderList(evalStrengths, report.strengths, "icon-green", "✔");
      renderList(evalWeaknesses, report.weaknesses, "icon-red", "✖");
      renderList(evalAreas, report.areas_of_improvement, "icon-yellow", "📌");

      evalReport.textContent = report.detailed_report || "Candidate transcript evaluated successfully.";
      renderTranscripts(document.getElementById("eval-transcript-list"), report.qa_transcript);
    } catch (e) {
      evalReport.textContent = "Error finalizing evaluation: " + e.message;
    }
  }

  function renderTranscripts(container, transcriptItems) {
    if (!container) return;
    container.innerHTML = "";
    if (!Array.isArray(transcriptItems) || transcriptItems.length === 0) {
      container.innerHTML = `<div style="color: var(--text-muted); font-style: italic;">No transcript logs recorded.</div>`;
      return;
    }

    transcriptItems.forEach(item => {
      const card = document.createElement("div");
      card.style.cssText = "background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 10px; padding: 1rem; display: flex; flex-direction: column; gap: 0.5rem;";
      
      const cat = (item.category || "Technical").toUpperCase();
      const userResp = item.user_response || "Skipped / No Answer";
      const isSkipped = item.skipped || userResp.includes("Skipped");

      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="font-size: 0.8rem; font-weight: 700; color: var(--accent);">Q${item.question_number} • ${cat}</span>
          ${isSkipped ? '<span style="font-size: 0.75rem; color: var(--warning); background: rgba(245, 158, 11, 0.15); padding: 0.2rem 0.5rem; border-radius: 4px;">Skipped</span>' : '<span style="font-size: 0.75rem; color: var(--success); background: rgba(16, 185, 129, 0.15); padding: 0.2rem 0.5rem; border-radius: 4px;">Answered</span>'}
        </div>
        <div style="font-weight: 600; font-size: 1rem; color: var(--text-main); margin-top: 0.25rem;">${item.question_text}</div>
        <div style="background: rgba(6, 182, 212, 0.08); border-left: 3px solid var(--accent); padding: 0.75rem; border-radius: 6px; margin-top: 0.5rem;">
          <div style="font-size: 0.8rem; font-weight: 700; color: var(--accent); margin-bottom: 0.25rem;">🎙️ Candidate Spoken Voice Answer / Real-Time Transcript:</div>
          <div style="font-size: 0.95rem; font-style: italic; color: var(--text-main); line-height: 1.5;">"${userResp}"</div>
        </div>
      `;
      container.appendChild(card);
    });
  }


  function renderList(container, items, colorClass, symbol) {
    container.innerHTML = "";
    const list = Array.isArray(items) ? items : [items];
    list.forEach(item => {
      if (item) {
        const div = document.createElement("div");
        div.className = "list-item";
        div.innerHTML = `<span class="${colorClass}">${symbol}</span> <span>${item}</span>`;
        container.appendChild(div);
      }
    });
  }

  // Restart Button
  btnRestart.addEventListener("click", () => {
    stepEvaluation.classList.add("hidden");
    stepSetup.classList.remove("hidden");
    loadCandidates();
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initApp);
} else {
  initApp();
}

