document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page || "";
  if (page === "quiz") initQuizPage();
  if (page === "admin") initAdminPage();
});

function $(sel, parent = document) { return parent.querySelector(sel); }
function $all(sel, parent = document) { return Array.from(parent.querySelectorAll(sel)); }

/* ============ QUIZ PAGE ============ */
function initQuizPage() {
  const quizId = document.body.dataset.quizId;
  const total = parseInt(document.body.dataset.total || "0", 10);
  let timerSeconds = parseInt(document.body.dataset.timerSeconds || "0", 10);

  const questionArea = $("#questionArea");
  const progressText = $("#progressText");
  const progressBar = $("#progressBar");
  const timerEl = $("#timer");
  const prevBtn = $("#prevBtn");
  const nextBtn = $("#nextBtn");
  const submitBtn = $("#submitBtn");

  if (!quizId || total === 0) return;

  let questions = [];
  let currentIndex = 0;
  let answers = {}; // {questionId: optionText}

  fetch(`/api/quiz/${quizId}`)
    .then(r => r.json())
    .then(data => {
      questions = data.questions || [];
      if (!Array.isArray(questions) || questions.length === 0) {
        questionArea.innerHTML = `<div class="muted">No questions could be loaded.</div>`;
        return;
      }
      renderQuestion();
      startTimer();
    })
    .catch(() => {
      questionArea.innerHTML = `<div class="muted">Error loading questions.</div>`;
    });

  function renderQuestion() {
    const q = questions[currentIndex];
    if (!q) return;

    const selected = answers[q.id] || null;
    const letters = ["A", "B", "C", "D"];

    questionArea.innerHTML = `
      <div class="qa-q"><span class="q-num">Q${currentIndex + 1}.</span> ${q.question}</div>
      <div class="options">
        ${q.options.map((opt, i) => `
        <label class="option">
          <span class="label">${letters[i]}</span>
          <input type="radio" name="option" value="${escapeHtml(opt)}" ${selected === opt ? "checked" : ""} />
          <div>${escapeHtml(opt)}</div>
        </label>`).join("")}
      </div>
    `;

    progressText.textContent = `Question ${currentIndex + 1} of ${questions.length}`;
    const pct = Math.round(((currentIndex) / questions.length) * 100);
    progressBar.style.width = `${pct}%`;

    prevBtn.disabled = currentIndex === 0;
    nextBtn.style.display = currentIndex < questions.length - 1 ? "inline-flex" : "none";
    submitBtn.style.display = currentIndex === questions.length - 1 ? "inline-flex" : "none";

    $all('input[name="option"]').forEach(radio => {
      radio.addEventListener("change", (e) => {
        answers[q.id] = e.target.value;
      });
    });
  }

  prevBtn.addEventListener("click", () => {
    if (currentIndex > 0) {
      currentIndex--;
      renderQuestion();
    }
  });

  nextBtn.addEventListener("click", () => {
    if (currentIndex < questions.length - 1) {
      currentIndex++;
      renderQuestion();
    }
  });

  submitBtn.addEventListener("click", submitQuiz);

  function submitQuiz() {
    const payload = { quiz_id: quizId, answers: {} };
    questions.forEach(q => {
      if (answers[q.id]) payload.answers[String(q.id)] = answers[q.id];
    });

    fetch("/submit", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    }).then(r => r.json())
      .then(data => {
        if (data.ok && data.redirect) {
          window.location.href = data.redirect;
        } else {
          alert(data.error || "Submission failed.");
        }
      }).catch(() => alert("Network error while submitting."));
  }

  function startTimer() {
    updateTimerDisplay();
    const iv = setInterval(() => {
      timerSeconds--;
      if (timerSeconds <= 0) {
        clearInterval(iv);
        submitQuiz();
      } else {
        updateTimerDisplay();
      }
    }, 1000);
  }

  function updateTimerDisplay() {
    timerEl.textContent = formatDuration(timerSeconds);
    if (timerSeconds < 30) {
      timerEl.style.background = "#fee2e2";
      timerEl.style.color = "#991b1b";
      timerEl.style.borderColor = "#fecaca";
    }
  }
}

/* ============ ADMIN PAGE ============ */
function initAdminPage() {
  const app = $("#adminApp");
  if (!app) return;

  const filter = $("#filterSubject");
  const refreshBtn = $("#refreshBtn");
  const tableBody = $("#questionsBody");
  const addForm = $("#addForm");

  function loadQuestions() {
    const subj = filter.value || "All";
    fetch(`/api/admin/questions?subject=${encodeURIComponent(subj)}`)
      .then(r => r.json())
      .then(data => {
        const questions = data.questions || [];
        renderTable(questions);
      }).catch(() => {
        tableBody.innerHTML = `<tr><td colspan="8">Error loading questions</td></tr>`;
      });
  }

  function renderTable(rows) {
    if (!rows.length) {
      tableBody.innerHTML = `<tr><td colspan="8" class="muted">No questions found.</td></tr>`;
      return;
    }
    tableBody.innerHTML = rows.map(q => {
      const opts = (q.options || []).map((opt, i) => `${"ABCD"[i]}) ${escapeHtml(opt)}`).join("<br>");
      return `
      <tr data-id="${q.id}">
        <td>${q.id}</td>
        <td>${escapeHtml(q.subject)}</td>
        <td>${escapeHtml(q.question)}</td>
        <td>${opts}</td>
        <td>${escapeHtml(q.answer)}</td>
        <td>${escapeHtml(q.difficulty || "Medium")}</td>
        <td>${escapeHtml(q.explanation || "")}</td>
        <td>
          <button class="btn-outline" data-action="edit">Edit</button>
          <button class="btn-outline danger" data-action="delete">Delete</button>
        </td>
      </tr>`;
    }).join("");

    $all("button[data-action='delete']", tableBody).forEach(btn => {
      btn.addEventListener("click", onDelete);
    });
    $all("button[data-action='edit']", tableBody).forEach(btn => {
      btn.addEventListener("click", onEdit);
    });
  }

  function onDelete(e) {
    const tr = e.target.closest("tr");
    const id = parseInt(tr.dataset.id, 10);
    if (!confirm(`Delete question #${id}?`)) return;
    fetch("/admin/delete_question", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ id })
    }).then(r => r.json())
      .then(data => {
        if (data.ok) loadQuestions();
        else alert(data.error || "Delete failed");
      }).catch(() => alert("Network error"));
  }

  function onEdit(e) {
    const tr = e.target.closest("tr");
    const id = parseInt(tr.dataset.id, 10);
    const tds = tr.querySelectorAll("td");
    const subject = tds[1].textContent.trim();
    const question = tds[2].textContent.trim();
    const optionsText = tds[3].innerHTML;
    const answer = tds[4].textContent.trim();
    const difficulty = tds[5].textContent.trim();
    const explanation = tds[6].textContent.trim();

    const opts = extractOptionsFromHtml(optionsText);

    tr.innerHTML = `
      <td>${id}</td>
      <td>
        <select class="edit-subject">
          <option ${subject==="Physics"?"selected":""}>Physics</option>
          <option ${subject==="Chemistry"?"selected":""}>Chemistry</option>
          <option ${subject==="Botany"?"selected":""}>Botany</option>
          <option ${subject==="Zoology"?"selected":""}>Zoology</option>
          <option ${subject==="Mental Agility Test"?"selected":""}>Mental Agility Test</option>
        </select>
      </td>
      <td><textarea class="edit-question">${escapeTextarea(question)}</textarea></td>
      <td>
        <div class="form">
          <input class="edit-opt" data-idx="0" value="${escapeAttr(opts[0]||"")}" />
          <input class="edit-opt" data-idx="1" value="${escapeAttr(opts[1]||"")}" />
          <input class="edit-opt" data-idx="2" value="${escapeAttr(opts[2]||"")}" />
          <input class="edit-opt" data-idx="3" value="${escapeAttr(opts[3]||"")}" />
        </div>
      </td>
      <td>
        <select class="edit-answer">
          ${["A","B","C","D"].map((L,i)=>`<option ${((opts[i]||"")===answer)?"selected":""} value="${escapeAttr(opts[i]||"")}">${L}</option>`).join("")}
        </select>
      </td>
      <td>
        <select class="edit-difficulty">
          <option ${difficulty==="Easy"?"selected":""}>Easy</option>
          <option ${difficulty==="Medium"?"selected":""}>Medium</option>
          <option ${difficulty==="Hard"?"selected":""}>Hard</option>
        </select>
      </td>
      <td><textarea class="edit-expl">${escapeTextarea(explanation||"")}</textarea></td>
      <td>
        <button class="btn-primary" data-action="save">Save</button>
        <button class="btn-outline" data-action="cancel">Cancel</button>
      </td>
    `;

    tr.querySelector("button[data-action='cancel']").addEventListener("click", () => loadQuestions());
    tr.querySelector("button[data-action='save']").addEventListener("click", () => {
      const newSubject = tr.querySelector(".edit-subject").value;
      const newQuestion = tr.querySelector(".edit-question").value.trim();
      const newOpts = $all(".edit-opt", tr).sort((a,b)=>a.dataset.idx-b.dataset.idx).map(inp => inp.value.trim());
      const ansSel = tr.querySelector(".edit-answer");
      const newAnswer = ansSel.value;
      const newDiff = tr.querySelector(".edit-difficulty").value;
      const newExpl = tr.querySelector(".edit-expl").value;

      if (newOpts.length !== 4 || newOpts.some(x=>!x)) {
        alert("Please provide four options.");
        return;
      }
      if (!newQuestion) {
        alert("Question cannot be empty.");
        return;
      }
      if (!newOpts.includes(newAnswer)) {
        alert("Correct answer must match an option.");
        return;
      }

      fetch("/admin/update_question", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          id,
          subject: newSubject,
          question: newQuestion,
          options: newOpts,
          answer: newAnswer,
          difficulty: newDiff,
          explanation: newExpl
        })
      }).then(r => r.json())
        .then(data => {
          if (data.ok) loadQuestions();
          else alert(data.error || "Update failed");
        }).catch(() => alert("Network error"));
    });
  }

  addForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const fd = new FormData(addForm);
    const subject = fd.get("subject");
    const difficulty = fd.get("difficulty");
    const question = (fd.get("question") || "").trim();
    const optA = (fd.get("optA") || "").trim();
    const optB = (fd.get("optB") || "").trim();
    const optC = (fd.get("optC") || "").trim();
    const optD = (fd.get("optD") || "").trim();
    const answerLetter = fd.get("answer");
    const explanation = (fd.get("explanation") || "").trim();

    const options = [optA, optB, optC, optD];
    const answer = options[["A","B","C","D"].indexOf(answerLetter)] || "";

    if (!question || options.some(x => !x) || !answer) {
      alert("Please fill question, all four options, and correct answer.");
      return;
    }

    fetch("/admin/add_question", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ subject, question, options, answer, difficulty, explanation })
    }).then(r => r.json())
      .then(data => {
        if (data.ok) {
          addForm.reset();
          loadQuestions();
        } else alert(data.error || "Add failed");
      }).catch(() => alert("Network error"));
  });

  // CSV Import
  const csvForm = $("#csvForm");
  const csvFile = $("#csvFile");
  const csvResult = $("#csvResult");

  if (csvForm) {
    csvForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const file = csvFile?.files?.[0];
      if (!file) {
        alert("Please choose a CSV file.");
        return;
      }
      const fd = new FormData();
      fd.append("file", file);

      csvResult.textContent = "Uploading and importing...";
      fetch("/admin/upload_csv", { method: "POST", body: fd })
        .then(r => r.json())
        .then(data => {
          if (data.ok) {
            csvResult.textContent = `Imported: ${data.added} added, ${data.skipped} skipped.` +
              (data.errors && data.errors.length ? ` Errors: ${data.errors.slice(0,3).join(" | ")}${data.errors.length>3?" ...":""}` : "");
            loadQuestions();
          } else {
            csvResult.textContent = data.error || "Import failed.";
          }
        })
        .catch(() => csvResult.textContent = "Network error during upload.");
    });
  }

  refreshBtn.addEventListener("click", loadQuestions);
  filter.addEventListener("change", loadQuestions);

  loadQuestions();
}

/* Utilities */
function escapeHtml(str) {
  if (str == null) return "";
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
function escapeAttr(str) {
  return escapeHtml(str).replaceAll("'", "&#39;");
}
function escapeTextarea(str) {
  return (str || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function formatDuration(totalSec) {
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  return (h > 0 ? `${h}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}` : `${m}:${String(s).padStart(2,"0")}`);
}
function extractOptionsFromHtml(html) {
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  const text = tmp.textContent || tmp.innerText || "";
  const parts = text.split(/\s*[A-D]KATEX_INLINE_CLOSE\s/).filter(Boolean);
  if (parts.length === 4) return parts.map(p => p.trim());
  return text.split(/\s*[\r\n]+/).map(s => s.replace(/^[A-D]KATEX_INLINE_CLOSE\s*/, "")).filter(Boolean).slice(0,4);
}