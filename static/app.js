document.addEventListener("DOMContentLoaded", () => {
  // Application State
  let currentInterviewId = null;
  let currentDocumentId = null;
  let totalQuestions = 5;
  let currentQuestionIndex = 0;
  
  // MediaRecorder state
  let mediaRecorder = null;
  let audioChunks = [];
  let recordingTimerInterval = null;
  let recordingSeconds = 0;

  // DOM Elements
  const stepSetup = document.getElementById("step-setup");
  const stepQuestion = document.getElementById("step-question");
  const stepEvaluation = document.getElementById("step-evaluation");

  const candidateSelect = document.getElementById("candidate-select");
  const resumeFileInput = document.getElementById("resume-file");
  const targetRoleInput = document.getElementById("target-role");
  const numQuestionsSelect = document.getElementById("num-questions");
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
    } else if (!docId) {
      docId = "doc-" + Math.random().toString(36).substr(2, 9);
    }

    currentDocumentId = docId;
    const targetRole = targetRoleInput.value.trim() || "AI Engineer";
    totalQuestions = parseInt(numQuestionsSelect.value, 10);

    btnStartInterview.disabled = true;
    btnStartInterview.textContent = "⚙️ Generating Customized Questions via CrewAI...";

    try {
      const res = await fetch("/api/v1/interview/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_id: currentDocumentId,
          num_questions: totalQuestions,
          target_role: targetRole
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

  async function startRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      alert("Microphone access is not supported in your browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream);

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunks.push(event.data);
      };

      mediaRecorder.start(100);

      // UI state during recording
      btnMic.classList.add("recording");
      btnStopVoice.classList.remove("hidden");
      recordingStatus.textContent = "🎙️ Recording Audio Answer...";
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

    recordingStatus.textContent = "⚡ Transcribing Speech via OpenAI Whisper...";
    recordingStatus.style.color = "var(--accent)";
    btnStopVoice.disabled = true;

    mediaRecorder.stop();
    if (mediaRecorder.stream) {
      mediaRecorder.stream.getTracks().forEach(track => track.stop());
    }
    clearInterval(recordingTimerInterval);

    // Give small delay for last audio chunk
    setTimeout(async () => {
      const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
      const formData = new FormData();
      formData.append("file", audioBlob, `answer_q${currentQuestionIndex}.webm`);

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
    }, 300);
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

      evalScore.textContent = Math.round(report.overall_score || 80);
      
      renderList(evalStrengths, report.strengths, "icon-green", "✔");
      renderList(evalWeaknesses, report.weaknesses, "icon-red", "✖");
      renderList(evalAreas, report.areas_of_improvement, "icon-yellow", "📌");

      evalReport.textContent = report.detailed_report || "Candidate transcript evaluated successfully.";
    } catch (e) {
      evalReport.textContent = "Error finalizing evaluation: " + e.message;
    }
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
  });
});
