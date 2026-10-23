"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const state = { name: "", role: "student", pin: "", skills: {}, qid: null };

  const show = (el, on) => { el.hidden = !on; };
  const text = (el, t) => { el.textContent = t; };

  async function api(path, opts = {}) {
    const headers = Object.assign({ "X-Demo-User": state.name, "X-Demo-Role": state.role }, opts.headers || {});
    if (state.role === "teacher") headers["X-Demo-Pin"] = state.pin;
    const res = await fetch(path, Object.assign({}, opts, { headers }));
    let data = null;
    try { data = await res.json(); } catch (_) { /* non-JSON error body */ }
    if (!res.ok) throw new Error((data && data.detail && (typeof data.detail === "string" ? data.detail : "Please check your input.")) || "Something went wrong.");
    return data;
  }

  // ---- sign in ------------------------------------------------------------------------
  document.querySelectorAll('input[name="role"]').forEach((r) =>
    r.addEventListener("change", () => show($("pin-row"), r.value === "teacher" && r.checked)));

  $("signin-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    text($("signin-error"), "");
    state.name = $("name").value.trim();
    state.role = document.querySelector('input[name="role"]:checked').value;
    state.pin = $("pin").value;
    try {
      await api("/api/me");
    } catch (err) { text($("signin-error"), err.message); return; }
    show($("signin"), false);
    show($("session"), true);
    text($("whoami"), `${state.name} (${state.role})`);
    if (state.role === "teacher") { show($("teacher"), true); loadTeacher(); }
    else { show($("student"), true); loadSkills(); }
  });

  $("signout").addEventListener("click", () => {
    state.name = ""; state.pin = ""; state.qid = null;
    ["student", "teacher", "session"].forEach((id) => show($(id), false));
    show($("signin"), true);
    $("pin").value = "";
  });

  fetch("/api/health").then((r) => r.json()).then((h) => {
    if (!h.gemini) { show($("photo-hint"), true); }
  }).catch(() => {});

  // ---- student: check work -------------------------------------------------------------
  $("example").addEventListener("click", () => {
    $("question").value = "2x + 3 = 11";
    $("steps").value = "2x = 11 + 3\nx = 7";
  });

  $("photo").addEventListener("change", () => {
    const f = $("photo").files[0];
    text($("photo-label"), f ? `Photo: ${f.name}` : "Use a photo of your work instead");
  });

  function renderReview(res) {
    const list = $("review");
    list.replaceChildren();
    (res.review || []).forEach((s) => {
      const li = document.createElement("li");
      const mk = document.createElement("span"); mk.className = "mk";
      const tx = document.createElement("span"); tx.className = "tx";
      tx.textContent = s.text;
      if (s.ok === true) { li.className = "ok"; mk.textContent = "✓"; mk.setAttribute("aria-label", "correct"); }
      else if (s.ok === false) { li.className = "bad"; mk.textContent = "✗"; mk.setAttribute("aria-label", "first mistake"); }
      else { li.className = "skip"; mk.textContent = "·"; mk.setAttribute("aria-label", "not checked"); }
      li.append(mk, tx);
      list.append(li);
    });
  }

  $("check").addEventListener("click", async () => {
    text($("diag-error"), "");
    const q = $("question").value.trim();
    const steps = $("steps").value;
    const photo = $("photo").files[0];
    if (!q) { text($("diag-error"), "Add the equation you were given."); return; }
    const fd = new FormData();
    fd.append("question", q);
    fd.append("steps", steps);
    if (photo) fd.append("image", photo);
    const btn = $("check"); btn.disabled = true; btn.textContent = "Checking…";
    try {
      const res = await api("/api/diagnose", { method: "POST", body: fd });
      show($("pen-empty"), false); show($("pen-result"), true);
      renderReview(res);
      const v = $("verdict");
      if (res.status === "ok" && res.is_correct) { v.className = "verdict good"; text(v, res.complete ? "All correct." : "Correct so far."); }
      else if (res.status === "ok") { v.className = "verdict bad"; text(v, `Line ${res.first_error_step}: ${res.misconception.title}`); }
      else { v.className = "verdict bad"; text(v, "I could not check that."); }
      text($("message"), res.message || "");
      const meta = [];
      if (res.status === "ok") meta.push(`Confidence ${Math.round(res.confidence * 100)}%`);
      if (res.source) meta.push(res.source === "checker" ? "Checked by the step checker" : "Photo read by Gemini, checked by the step checker");
      text($("meta"), meta.join(". "));
      if (res.needs_teacher) {
        const b = document.createElement("span"); b.className = "badge"; b.textContent = "Flagged for your teacher";
        $("meta").append(" ", b);
      }
      loadSkills();
    } catch (err) { text($("diag-error"), err.message); }
    finally { btn.disabled = false; btn.textContent = "Check my work"; }
  });

  // ---- student: practice ------------------------------------------------------------------
  $("pr-next").addEventListener("click", async () => {
    text($("pr-error"), ""); text($("pr-result"), "");
    try {
      const q = await api("/api/practice/next");
      state.qid = q.question_id;
      show($("pr-empty"), false); show($("pr-box"), true); show($("pr-check"), true);
      text($("pr-q"), q.question);
      text($("pr-meta"), `${state.skillNames[q.skill] || q.skill}, ${q.level} level`);
      $("pr-a").value = ""; $("pr-a").focus();
      text($("pr-next"), "Skip to another");
    } catch (err) { text($("pr-error"), err.message); }
  });

  $("pr-check").addEventListener("click", async () => {
    text($("pr-error"), "");
    if (!state.qid) return;
    try {
      const r = await api("/api/practice/answer", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question_id: state.qid, answer: $("pr-a").value }),
      });
      state.qid = null; show($("pr-check"), false);
      text($("pr-result"), r.correct ? "Right. The next one will adapt to you." : `Not quite. The answer was x = ${r.answer}.`);
      text($("pr-next"), "Next question");
      loadSkills();
    } catch (err) { text($("pr-error"), err.message); }
  });

  $("pr-a").addEventListener("keydown", (e) => { if (e.key === "Enter") $("pr-check").click(); });

  state.skillNames = {};
  fetch("/api/health").then((r) => r.json()).then((h) => { state.skillNames = h.skills || {}; }).catch(() => {});

  function bar(label, right, pct, cls) {
    const li = document.createElement("li");
    const lab = document.createElement("div"); lab.className = "lab";
    const a = document.createElement("span"); a.textContent = label;
    const b = document.createElement("span"); b.textContent = right;
    lab.append(a, b);
    const track = document.createElement("div"); track.className = "track";
    track.setAttribute("role", "img"); track.setAttribute("aria-label", `${label}: ${right}`);
    const fill = document.createElement("div"); fill.className = `fill ${cls || ""}`;
    fill.style.width = `${Math.max(3, Math.min(100, pct))}%`;
    track.append(fill); li.append(lab, track);
    return li;
  }
  const tone = (s) => (s < 0.4 ? "warn" : s < 0.75 ? "mid" : "");

  async function loadSkills() {
    try {
      const { skills } = await api("/api/mastery");
      const list = $("skills"); list.replaceChildren();
      const keys = Object.keys(skills);
      show($("sk-empty"), keys.length === 0);
      keys.forEach((k) => {
        const m = skills[k];
        list.append(bar(state.skillNames[k] || k, `${m.correct}/${m.attempts} right`, m.score * 100, tone(m.score)));
      });
    } catch (_) { /* leave the list as it was */ }
  }

  // ---- teacher ---------------------------------------------------------------------------------
  async function loadTeacher() {
    text($("t-error"), "");
    try {
      const s = await api("/api/teacher/summary");
      text($("t-students"), s.students); text($("t-checks"), s.checks); text($("t-flag"), s.needs_teacher);
      const mis = $("t-mis"); mis.replaceChildren();
      const top = s.misconceptions.length ? s.misconceptions[0].count : 1;
      s.misconceptions.forEach((m) => mis.append(bar(m.title, `${m.count}×`, (m.count / top) * 100, "warn")));
      show($("t-mis-empty"), s.misconceptions.length === 0);
      const sk = $("t-skills"); sk.replaceChildren();
      const keys = Object.keys(s.skills);
      keys.forEach((k) => sk.append(bar(state.skillNames[k] || k, `${Math.round(s.skills[k] * 100)}%`, s.skills[k] * 100, tone(s.skills[k]))));
      show($("t-skills-empty"), keys.length === 0);
      text($("t-lesson"), s.mini_lesson || "Once students submit work, a suggestion shows up here.");
    } catch (err) { text($("t-error"), err.message); }
  }
  $("t-refresh").addEventListener("click", loadTeacher);
})();
