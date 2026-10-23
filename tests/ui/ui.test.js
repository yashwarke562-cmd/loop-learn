const { JSDOM } = require("jsdom");
const fs = require("fs");
const BASE = process.env.BASE || "http://127.0.0.1:8765";
const root = require("path").join(__dirname, "..", "..", "static") + "/";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let failed = 0;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) failed++; };

async function boot() {
  const html = fs.readFileSync(root + "index.html", "utf8").replace(/<script src[^>]*><\/script>/, "").replace(/<link[^>]*>/, "");
  const dom = new JSDOM(html, { runScripts: "outside-only", url: BASE + "/" });
  const w = dom.window;
  w.fetch = (u, o) => fetch(BASE + u, o);
  w.FormData = FormData;
  w.eval(fs.readFileSync(root + "app.js", "utf8"));
  return w;
}
const click = (w, id) => w.document.getElementById(id).dispatchEvent(new w.Event("click", { bubbles: true }));
const val = (w, id, v) => { w.document.getElementById(id).value = v; };
const txt = (w, id) => w.document.getElementById(id).textContent;
const hidden = (w, id) => w.document.getElementById(id).hidden;

(async () => {
  let w = await boot();
  // bad teacher pin is rejected
  val(w, "name", "ms_rao"); w.document.querySelector('input[value="teacher"]').checked = true;
  val(w, "pin", "wrong");
  w.document.getElementById("signin-form").dispatchEvent(new w.Event("submit", { cancelable: true }));
  await sleep(400);
  ok(/PIN/i.test(txt(w, "signin-error")) && !hidden(w, "signin"), "wrong teacher PIN shows an error and stays on sign-in");

  // student flow
  w = await boot();
  val(w, "name", "maya_8b");
  w.document.getElementById("signin-form").dispatchEvent(new w.Event("submit", { cancelable: true }));
  await sleep(400);
  ok(!hidden(w, "student") && hidden(w, "signin"), "student signs in and sees the notebook");
  click(w, "example");
  ok(w.document.getElementById("question").value === "2x + 3 = 11", "example button fills the equation");
  click(w, "check"); await sleep(600);
  const lis = [...w.document.querySelectorAll("#review li")];
  ok(lis.length === 2 && lis[0].className === "bad" && lis[1].className === "skip", "red pen circles line 1 and leaves line 2 unchecked");
  ok(/Sign slip/i.test(txt(w, "verdict")), "verdict names the misconception: " + txt(w, "verdict"));
  ok(/Confidence 90%/.test(txt(w, "meta")), "confidence shown: " + txt(w, "meta"));

  // XSS: work text must render as text, never as markup
  val(w, "steps", "<img src=x onerror=alert(1)>"); click(w, "check"); await sleep(500);
  ok(w.document.querySelectorAll("#review img, #message img").length === 0, "markup in input never becomes elements");

  // validation message from API surfaces
  val(w, "question", "hello"); click(w, "check"); await sleep(400);
  ok(/equation/i.test(txt(w, "diag-error")), "bad equation shows API error: " + txt(w, "diag-error"));

  // practice
  click(w, "pr-next"); await sleep(500);
  ok(!hidden(w, "pr-box") && txt(w, "pr-q").includes("="), "practice question appears: " + txt(w, "pr-q"));
  ok(/moving|x on both|Dividing|Brackets|arithmetic|Mixed/i.test(txt(w, "pr-meta")), "skill label shown: " + txt(w, "pr-meta"));
  val(w, "pr-a", "banana"); click(w, "pr-check"); await sleep(400);
  ok(/number/i.test(txt(w, "pr-error")), "non-number answer rejected with guidance");
  val(w, "pr-a", "9999"); click(w, "pr-check"); await sleep(500);
  ok(/Not quite/.test(txt(w, "pr-result")), "wrong answer feedback: " + txt(w, "pr-result"));
  ok(w.document.querySelectorAll("#skills li").length >= 1 && hidden(w, "sk-empty"), "skills bars rendered");

  // modal & accessibility controls
  click(w, "btn-help");
  ok(!hidden(w, "help-modal"), "help dialog opens on clicking 'How it works'");
  click(w, "help-close");
  ok(hidden(w, "help-modal"), "help dialog closes on close button");
  click(w, "toggle-paper");
  ok(w.document.getElementById("steps").classList.contains("plain"), "paper toggle toggles plain paper class");

  // teacher flow
  w = await boot();
  val(w, "name", "ms_rao"); w.document.querySelector('input[value="teacher"]').checked = true; val(w, "pin", process.env.TEACHER_PIN || "2468");
  w.document.getElementById("signin-form").dispatchEvent(new w.Event("submit", { cancelable: true }));
  await sleep(700);
  ok(!hidden(w, "teacher") && hidden(w, "student"), "teacher sees the class overview only");
  ok(Number(txt(w, "t-checks")) >= 1, "class stats loaded, checks=" + txt(w, "t-checks"));
  ok(w.document.querySelectorAll("#t-mis li").length >= 1 && /sign slip/i.test(txt(w, "t-lesson")), "top mistake and mini-lesson shown");
  ok(!/maya/i.test(w.document.getElementById("teacher").textContent), "no student names on teacher view");
  process.exit(failed ? 1 : 0);
})();
