"""Shared review page: one player with a scene timeline. The reviewer pauses or keeps playing, comments on any
frame, and clicks Send. The server persists notes and keeps playing; an agent polls and acknowledges batches.
Keep this file identical everywhere it is bundled."""
import html, json, os, re, subprocess, sys, threading, time, webbrowser, uuid
from urllib.request import urlopen
from urllib.parse import urlsplit
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

CSS = """
:root, :root[data-theme="dark"] {
  --canvas: #171614; --rail: #1f1e1b; --card: #262420; --card-border: #34322d; --hair: #2f2d29;
  --strong-border: #403d37; --txt: #eae7e0; --strong-txt: #f4f1ea; --mute: #9c968a; --faint: #6e6961;
  --soft: #2c2a26; --chip: #2e2c27; --input-bg: #1c1b18; --focus: #4d4941; --danger: #d9705f;
  --btn-bg: #f0ede6; --btn-fg: #1b1a16; --band: #2a2825; --band-alt: #24221f; --band-cur: #3a3631; --pin: #e0a800;
}
:root[data-theme="light"] {
  --canvas: #eceae4; --rail: #fbfaf7; --card: #ffffff; --card-border: #e9e7e0; --hair: #e4e2db;
  --strong-border: #d9d5c9; --txt: #26241e; --strong-txt: #1b1a16; --mute: #8b877d; --faint: #b6b2a8;
  --soft: #f2f0ea; --chip: #f4f2ec; --input-bg: #fdfcfa; --focus: #c2beb4; --danger: #b23b2e;
  --btn-bg: #1b1a16; --btn-fg: #fbfaf7; --band: #dfdcd4; --band-alt: #e6e3dc; --band-cur: #cfcbc1; --pin: #c99500;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
button, textarea { font: inherit; color: inherit; }
html, body { height: 100%; overflow: hidden; }
body { background: var(--canvas); color: var(--txt); font: 13px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, sans-serif; -webkit-font-smoothing: antialiased; display: flex; }
.stage { flex: 1; min-width: 0; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; gap: 12px; padding: 20px 28px; }
.player { --ratio: 1.777778; position: relative; flex: none; width: min(100%, calc((100vh - 145px) * var(--ratio))); aspect-ratio: var(--ratio); background: #000; border-radius: 10px; overflow: hidden; }
.player video, .player canvas, .player img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; }
.player video { opacity: 0; pointer-events: none; }
.player canvas { cursor: pointer; }
.player img { pointer-events: none; }
.media-status { color: var(--danger); min-height: 0; }
.media-status:empty { display: none; }
.controls { width: min(100%, 860px); display: flex; flex-direction: column; gap: 8px; }
.row { display: flex; align-items: center; gap: 10px; }
.play { width: 30px; height: 30px; border-radius: 50%; border: 1px solid var(--strong-border); background: var(--card); display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 11px; }
.play:hover { border-color: var(--focus); }
.tc { font: 12px ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--strong-txt); }
.tc span { color: var(--faint); }
.chip { padding: 2px 8px; border-radius: 999px; background: var(--chip); color: var(--mute); font-size: 11px; font-weight: 600; }
#bar { position: relative; height: 28px; border-radius: 6px; overflow: hidden; background: var(--band); cursor: pointer; user-select: none; }
.band { position: absolute; top: 0; bottom: 0; background: var(--band); border-right: 1px solid var(--canvas); font: 10px ui-monospace, monospace; color: var(--faint); padding: 7px 0 0 5px; overflow: hidden; white-space: nowrap; }
.band:nth-child(even) { background: var(--band-alt); }
.band.cur { background: var(--band-cur); color: var(--strong-txt); }
.band.nolabel { color: transparent; }
.pin { position: absolute; top: 2px; width: 8px; height: 8px; margin-left: -4px; border-radius: 50%; background: var(--pin); z-index: 4; cursor: pointer; }
.pin:hover { transform: scale(1.4); }
#head { position: absolute; top: 0; bottom: 0; width: 2px; margin-left: -1px; background: var(--strong-txt); pointer-events: none; z-index: 3; }
.rail { flex: none; width: 352px; display: flex; flex-direction: column; border-left: 1px solid var(--hair); background: var(--rail); }
.rail-scroll { flex: 1; min-height: 0; overflow-y: auto; padding: 16px 12px 12px; }
.rail-head { display: flex; align-items: center; gap: 7px; padding: 0 4px 10px; }
.section { font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--mute); }
.dim { color: var(--faint); font-size: 11px; }
.icon-btn { width: 26px; height: 26px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--hair); border-radius: 7px; background: var(--soft); font-size: 12.5px; line-height: 1; cursor: pointer; }
.icon-btn:hover { border-color: var(--strong-border); color: var(--strong-txt); }
.push { margin-left: auto; }
.speed { padding: 3px 22px 3px 10px; border: 1px solid var(--strong-border); border-radius: 999px; background: var(--card) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='5'%3E%3Cpath d='M0 0l4 5 4-5z' fill='%239c968a'/%3E%3C/svg%3E") no-repeat right 9px center; font: 600 11.5px ui-monospace, monospace; color: var(--strong-txt); cursor: pointer; appearance: none; -webkit-appearance: none; }
.speed:hover { border-color: var(--focus); }
.controls { position: relative; }
.keys { position: absolute; right: 0; bottom: 74px; z-index: 10; width: 250px; padding: 10px 12px; border: 1px solid var(--strong-border); border-radius: 8px; background: var(--card); box-shadow: 0 8px 24px -10px rgba(0, 0, 0, 0.45); color: var(--mute); font-size: 12px; }
.keys div { display: flex; justify-content: space-between; gap: 12px; padding: 3px 0; }
kbd { font: 10.5px ui-monospace, monospace; padding: 1px 5px; border: 1px solid var(--hair); border-radius: 4px; background: var(--soft); color: var(--txt); }
.compose { margin-bottom: 12px; padding: 13px 14px; border: 1px solid var(--strong-border); border-radius: 8px; background: var(--card); box-shadow: 0 4px 14px -8px rgba(27, 26, 22, 0.3); }
.compose-head { display: flex; align-items: center; gap: 7px; margin-bottom: 9px; }
textarea { width: 100%; padding: 8px 10px; border: 1px solid var(--hair); border-radius: 6px; background: var(--input-bg); font-size: 13px; line-height: 1.5; resize: none; outline: none; }
textarea:focus { border-color: var(--focus); background: var(--card); }
#note { min-height: 72px; }
.compose-foot { display: flex; align-items: center; gap: 8px; margin-top: 9px; }
.btn { padding: 6px 12px; border: 1px solid var(--btn-bg); border-radius: 6px; background: var(--btn-bg); color: var(--btn-fg); font-size: 12px; font-weight: 500; cursor: pointer; }
.btn:disabled { border-color: var(--hair); background: var(--soft); color: var(--faint); cursor: default; }
.cards { display: flex; flex-direction: column; gap: 8px; }
.empty { padding: 8px 4px; color: var(--faint); font-size: 12px; }
.comment { padding: 11px 12px; border: 1px solid var(--card-border); border-radius: 8px; background: var(--card); cursor: pointer; }
.comment:hover { border-color: var(--strong-border); }
.comment.now { border-color: var(--pin); }
.comment .del { opacity: 0; transition: opacity .12s; }
.comment:hover .del { opacity: 1; }
.comment-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.comment p { font-size: 13px; line-height: 1.5; white-space: pre-wrap; }
.del { margin-left: auto; border: 0; background: none; color: var(--faint); font-size: 11px; cursor: pointer; }
.del:hover { color: var(--danger); }
.rail-foot { flex: none; padding: 12px; border-top: 1px solid var(--hair); display: flex; flex-direction: column; gap: 8px; }
#overall { min-height: 38px; max-height: 120px; font-size: 12.5px; }
.key { margin-left: 6px; opacity: .6; font-size: 11px; }
.btn:not(:disabled) { cursor: pointer; }
.send { width: 100%; padding: 10px 12px; border: 1px solid var(--btn-bg); border-radius: 6px; background: var(--btn-bg); color: var(--btn-fg); font-size: 12.5px; font-weight: 500; cursor: pointer; }
#status { min-height: 16px; color: var(--mute); font-size: 11.5px; text-align: center; }
@media (max-aspect-ratio: 4/5) {   /* phone or portrait window: video and timeline on top, comments below */
  body { flex-direction: column; }
  .stage { flex: none; padding: 12px 14px 6px; gap: 8px; }
  .player { width: min(100%, calc(46vh * var(--ratio))); }
  .rail { width: 100%; flex: 1; min-height: 0; border-left: 0; border-top: 1px solid var(--hair); }
}
"""

JS = r"""
const $ = (id) => document.getElementById(id);
const v = $("v"), bar = $("bar"), note = $("note");
const fmt = (t) => `${Math.floor(t / 60)}:${(t % 60).toFixed(2).padStart(5, "0")}`;
// Scene ids like "s01" display as "s1".
const short = (id) => String(id).replace(/^s0+(?=\d)/, "s");
const sceneAt = (t) => SCENES.find((s) => t >= s.start && t < s.end) || SCENES[SCENES.length - 1];
const store = (k, val) => { try { if (val === undefined) return localStorage.getItem(k); localStorage.setItem(k, val); } catch {} };
const KEY = "review:" + location.pathname;
let state; try { state = JSON.parse(store(KEY)) || { comments: [] }; } catch { state = { comments: [] }; }
state.overall = state.overall || "";
const save = () => store(KEY, JSON.stringify(state));

// Start in the light theme; preserve choices made in this version.
const setTheme = (t) => { document.documentElement.dataset.theme = t; $("theme").textContent = t === "dark" ? "☀" : "☾"; store("review:theme:v2", t); };
setTheme(store("review:theme:v2") || "light");
$("theme").onclick = () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
$("keysbtn").onclick = (e) => { e.stopPropagation(); $("keys").hidden = !$("keys").hidden; };
addEventListener("click", (e) => { if (!$("keys").contains(e.target)) $("keys").hidden = true; });
addEventListener("keydown", (e) => { if (e.key === "Escape") $("keys").hidden = true; });

SCENES.forEach((s) => {
  const b = document.createElement("div");
  b.className = "band"; b.dataset.id = s.id; b.textContent = short(s.id);
  b.style.left = (s.start / DUR) * 100 + "%"; b.style.width = ((s.end - s.start) / DUR) * 100 + "%";
  b.title = `${short(s.id)} · ${s.layout} · ${s.visual}\n“${s.spoken}”`;
  bar.appendChild(b);
});
const fitLabels = () => document.querySelectorAll(".band").forEach((b) => b.classList.toggle("nolabel", b.offsetWidth < 34));
window.addEventListener("resize", fitLabels); fitLabels();

const seek = (t) => { v.currentTime = Math.max(0, Math.min(DUR - 0.001, t)); };
function tick() {
  const t = v.currentTime, s = sceneAt(t);
  $("tc").innerHTML = `${fmt(t)} <span>/ ${fmt(DUR)}</span>`;
  $("scene").textContent = `${short(s.id)} · ${s.layout}`;
  $("at").textContent = `${fmt(t)} · ${short(s.id)}`;
  $("head").style.left = (t / DUR) * 100 + "%";
  document.querySelectorAll(".band").forEach((b) => b.classList.toggle("cur", b.dataset.id === s.id));
  $("play").textContent = v.paused ? "▶" : "❚❚";
}
["timeupdate", "seeked", "play", "pause"].forEach((e) => v.addEventListener(e, tick));
(function loop() { if (!v.paused) tick(); requestAnimationFrame(loop); })();
const toggle = () => {
  if (v.paused) v.play().catch(() => { $("media-status").textContent = "Playback could not start. Reload the page or open the video directly."; });
  else v.pause();
};
// Playback speed: click to cycle, or < and > to step; remembered per browser.
const SPEEDS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];
const setSpeed = (r) => { v.playbackRate = r; $("speed").value = String(r); store("review:speed", String(r)); };
setSpeed(Number(store("review:speed")) || 1);
const stepSpeed = (d) => { const i = SPEEDS.indexOf(v.playbackRate); setSpeed(SPEEDS[Math.max(0, Math.min(SPEEDS.length - 1, (i < 0 ? 2 : i) + d))]); };
$("speed").onchange = (e) => { setSpeed(Number(e.target.value)); e.target.blur(); };
// Paint decoded frames onto a canvas. Some embedded webviews lose the native video layer.
const canvas = $("picture"), context = canvas.getContext("2d", { alpha: false });
function paint() {
  if (v.readyState < 2 || !v.videoWidth) return;
  if (canvas.width !== v.videoWidth || canvas.height !== v.videoHeight) {
    canvas.width = v.videoWidth; canvas.height = v.videoHeight;
    $("player").style.setProperty("--ratio", v.videoWidth / v.videoHeight);
  }
  try { context.drawImage(v, 0, 0, canvas.width, canvas.height); $("poster").hidden = true; }
  catch { return; }
}
function nextFrame() { paint(); if (v.requestVideoFrameCallback) v.requestVideoFrameCallback(nextFrame); else requestAnimationFrame(nextFrame); }
nextFrame();
["loadeddata", "seeked", "pause"].forEach(e => v.addEventListener(e, paint));
v.addEventListener("error", () => { $("media-status").textContent = "The video could not load. Your notes are safe. Reload or open the video directly."; });
canvas.onclick = toggle;
v.addEventListener("ratechange", () => { if (Number($("speed").value) !== v.playbackRate) $("speed").value = String(v.playbackRate); });
v.onclick = toggle; $("play").onclick = toggle;
let drag = false;
const scrub = (e) => { const r = bar.getBoundingClientRect(); seek(((e.clientX - r.left) / r.width) * DUR); };
bar.addEventListener("mousedown", (e) => { drag = true; v.pause(); scrub(e); });
addEventListener("mousemove", (e) => drag && scrub(e));
addEventListener("mouseup", () => (drag = false));

function render() {
  document.querySelectorAll(".pin").forEach((p) => p.remove());
  state.comments.sort((a, b) => a.t - b.t);
  $("count").textContent = state.comments.length || "";
  const list = $("list");
  list.innerHTML = "";
  state.comments.forEach((c, i) => {
    const pin = document.createElement("div");
    pin.className = "pin"; pin.style.left = (c.t / DUR) * 100 + "%"; bar.appendChild(pin);
    const el = document.createElement("div");
    el.className = "comment";
    el.innerHTML = `<div class="comment-head"><span class="chip">${fmt(c.t)} · ${short(c.scene)}</span><button class="del">Delete</button></div><p></p>`;
    el.querySelector("p").textContent = c.note;
    el.onclick = () => seek(c.t);
    pin.title = c.note; pin.onclick = (e) => { e.stopPropagation(); seek(c.t); };
    el.dataset.t = c.t;
    el.querySelector(".del").onclick = (e) => { e.stopPropagation(); state.comments.splice(i, 1); save(); render(); };
    list.appendChild(el);
  });
  updateSend();
}
const hasNotes = () => state.comments.length > 0 || state.overall.trim() !== "";
const updateSend = () => { $("send").textContent = hasNotes() || note.value.trim() ? "Send notes" : "Looks good"; };
$("overall").value = state.overall;
$("overall").oninput = () => { state.overall = $("overall").value; save(); updateSend(); };
// Highlight the comment nearest the playhead.
v.addEventListener("timeupdate", () => document.querySelectorAll(".comment").forEach((el) => el.classList.toggle("now", Math.abs(+el.dataset.t - v.currentTime) < 1.5)));
function add() {
  const text = note.value.trim();
  if (!text) return;
  const t = +(+(note.dataset.t ?? v.currentTime)).toFixed(3), s = sceneAt(t); delete note.dataset.t;
  state.comments.push({ t, scene: s.id, scene_start: s.start, scene_end: s.end, note: text });
  note.value = ""; $("add").disabled = true; save(); render(); note.blur();
}
// Commenting never pauses: the note keeps the time you started typing.
note.onfocus = () => { if (!note.value.trim()) note.dataset.t = v.currentTime; };
note.oninput = () => { $("add").disabled = !note.value.trim(); updateSend(); };
note.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); add(); } if (e.key === "Escape") { note.value = ""; delete note.dataset.t; $("add").disabled = true; note.blur(); } };
$("overall").onkeydown = (e) => { if (e.key === "Escape") $("overall").blur(); };
$("add").onclick = add;

addEventListener("keydown", (e) => {
  if (e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;
  const step = e.shiftKey ? 1 : 1 / FPS;
  if (e.code === "Space") { e.preventDefault(); toggle(); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); v.pause(); seek(v.currentTime - step); }
  else if (e.key === "ArrowRight") { e.preventDefault(); v.pause(); seek(v.currentTime + step); }
  else if (e.key === "c") { e.preventDefault(); note.focus(); }
  else if (e.key === "<" || e.key === ",") { e.preventDefault(); stepSpeed(-1); }
  else if (e.key === ">" || e.key === ".") { e.preventDefault(); stepSpeed(1); }
});

$("send").onclick = async () => {
  if (note.value.trim()) add();
  $("send").disabled = true; $("status").textContent = "Sending…";
  try {
    const r = await fetch("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video: v.getAttribute("src").split("?")[0], comments: state.comments, overall: state.overall.trim() }) });
    if (!r.ok) throw new Error(r.status);
    const approved = !hasNotes();
    state = { comments: [], overall: "" }; $("overall").value = ""; save(); render();
    const delivery = await r.json();
    $("status").textContent = delivery.agent === "listening" ? (approved ? "Approval sent to the listening agent." : "Sent to the listening agent. Edits will appear here.") : "Saved. Agent is not listening yet; your notes are queued.";
    $("send").disabled = false;
  } catch { $("status").textContent = "Couldn't reach your agent. Ask it to reopen the review page; your notes are saved here."; render(); $("send").disabled = false; }
};

async function listenerStatus() {
  try {
    const data = await (await fetch("/api/status")).json();
    $("agent-status").textContent = data.state === "listening" ? "Agent listening" : data.state === "received" ? "Feedback received by agent" : "Agent not listening · Notes are saved";
  } catch { $("agent-status").textContent = "Review connection lost · Unsent notes stay in this browser"; }
}
listenerStatus(); setInterval(listenerStatus, 2000);
// Reload when the page is rebuilt, unless unsent comments are waiting.
let version = null;
setInterval(async () => {
  try {
    const { version: now } = await (await fetch("/api/version")).json();
    if (version === null) version = now;
    else if (now !== version && !hasNotes() && !note.value.trim()) location.reload();
  } catch {}
}, 3000);
render(); tick();
"""


def words_between(words, a, b):
    return " ".join(w["text"] for w in words if w["end"] > a + 0.04 and w["start"] < b - 0.04)


def short(scene_id):
    """Display "s01" as "s1"."""
    return re.sub(r"^s0+(?=\d)", "s", str(scene_id))


def fmt(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"



def probe(video):
    """Duration in seconds and frame rate of a video, via ffprobe."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate:format=duration",
                          "-of", "json", video], capture_output=True, text=True, check=True).stdout
    info = json.loads(out)
    num, den = info["streams"][0]["r_frame_rate"].split("/")
    return float(info["format"]["duration"]), round(int(num) / int(den))


def write_page(root, page, video, scenes):
    """Write the review page for video. scenes: [{id, start, end, layout, visual, spoken}] covering the whole video."""
    dur, fps = probe(video)
    src = "/" + os.path.relpath(video, root) + f"?v={int(os.path.getmtime(video))}"
    os.makedirs(os.path.dirname(page), exist_ok=True)
    poster = os.path.join(os.path.dirname(page), "poster.jpg")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-frames:v", "1", "-q:v", "3", poster], check=True)
    poster_src = "/" + os.path.relpath(poster, root) + f"?v={os.stat(video).st_mtime_ns}"
    content = PAGE.format(css=CSS, js=JS, src=html.escape(src), poster=html.escape(poster_src), scenes=json.dumps(scenes), dur=dur, fps=fps)
    atomic_text(page, content)


def save_frames(data, video, out_dir):
    """Save the frame under each comment, so the agent sees what the reviewer paused on. Returns {index: path}."""
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        os.remove(os.path.join(out_dir, f))
    frames = {}
    for i, c in enumerate(data.get("comments", [])):
        path = os.path.join(out_dir, f"{i + 1:02d}-{c['t']:.2f}.jpg")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{c['t']:.3f}", "-i", video, "-frames:v", "1",
                            "-vf", "scale=540:-2", "-q:v", "4", path], capture_output=True)
        if r.returncode == 0 and os.path.exists(path):
            frames[i] = path
    return frames


def notes_markdown(data, scenes, video, frames=None, words=None):
    by_id = {s["id"]: s for s in scenes}
    frames = frames or {}
    lines = [f"# Review notes: {os.path.basename(video)}", ""]
    for i, c in enumerate(data.get("comments", [])):
        s = by_id.get(c["scene"], {})
        lines += [f"## {fmt(c['t'])} · {short(c['scene'])} ({s.get('layout', '')}, {s.get('visual', '')})",
                  f"Says: “{words_between(words, c['t'] - 5, c['t'] + 2) if words else s.get('spoken', '')}”"] + ([f"Frame: {frames[i]}"] if i in frames else []) + ["", c["note"], ""]
    if data.get("overall"):
        lines += ["## Overall", data["overall"], ""]
    if len(lines) == 2:
        lines.append("Looks good. No notes.")
    return "\n".join(lines).strip() + "\n"


def atomic_text(path, content):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = str(path) + f".{uuid.uuid4().hex}.tmp"
    with open(tmp, "w") as f:
        f.write(content)
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def pending_batches(work):
    acked = set(read_json(os.path.join(work, "acknowledged.json"), []))
    folder = os.path.join(work, "feedback-batches")
    if not os.path.isdir(folder):
        return []
    return [os.path.join(folder, name) for name in sorted(os.listdir(folder))
            if name.endswith(".json") and name[:-5] not in acked]


def agent_status(work):
    lease = read_json(os.path.join(work, "listener.json"), {})
    received = read_json(os.path.join(work, "received.json"), {})
    pending = pending_batches(work)
    listening = time.time() - lease.get("at", 0) < 10
    state = "listening" if listening else "received" if pending and time.time() - received.get("at", 0) < 1800 else "idle"
    return {"state": state, "pending": len(pending)}


def poll_feedback(work, timeout=3600):
    """Block in the active agent's shell; a saved file alone cannot wake an ended turn."""
    work = os.path.abspath(work)
    os.makedirs(work, exist_ok=True)
    lease_path = os.path.join(work, "listener.json")
    lease = read_json(lease_path, {})
    if time.time() - lease.get("at", 0) < 10:
        raise RuntimeError("Another agent is already listening for this review.")
    token = uuid.uuid4().hex
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            atomic_text(lease_path, json.dumps({"token": token, "at": time.time()}))
            pending = pending_batches(work)
            if pending:
                batch = read_json(pending[0])
                if batch:
                    atomic_text(os.path.join(work, "received.json"), json.dumps({"batch_id": batch["batch_id"], "at": time.time()}))
                    return batch
            time.sleep(0.5)
        return {"status": "timeout"}
    finally:
        if read_json(lease_path, {}).get("token") == token:
            try:
                os.remove(lease_path)
            except OSError:
                pass


def acknowledge(work, batch_id):
    if not re.fullmatch(r"[0-9]+-[a-f0-9]{8}", batch_id):
        raise ValueError("Invalid feedback batch ID")
    if not os.path.isfile(os.path.join(work, "feedback-batches", batch_id + ".json")):
        raise ValueError("Feedback batch does not exist")
    path = os.path.join(work, "acknowledged.json")
    acked = set(read_json(path, [])); acked.add(batch_id)
    atomic_text(path, json.dumps(sorted(acked)))
    return {"status": "acknowledged", "batch_id": batch_id}


def handle_review_control():
    """Shared poll/ack CLI for both generic video review and standalone video-short."""
    if not any(arg in sys.argv for arg in ("--poll", "--ack", "--status")):
        return False
    import argparse
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--poll", metavar="WORK")
    group.add_argument("--ack", nargs=2, metavar=("WORK", "BATCH_ID"))
    group.add_argument("--status", metavar="WORK")
    ap.add_argument("--timeout", type=float, default=3600)
    a = ap.parse_args()
    result = poll_feedback(a.poll, a.timeout) if a.poll else acknowledge(*a.ack) if a.ack else agent_status(a.status)
    print(json.dumps(result), flush=True)
    return True


def build_server(root, page, feedback, scenes, video, port, words=None):
    work = os.path.dirname(os.path.abspath(feedback))

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=root, **k)

        def log_message(self, *a):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        def reply(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/api/feedback":
                return self.send_error(404)
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                return self.send_error(403)
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 1048576:
                    return self.send_error(413)
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict) or not isinstance(data.get("comments", []), list) or not isinstance(data.get("overall", ""), str):
                    raise ValueError("Invalid feedback")
                for c in data.get("comments", []):
                    if not isinstance(c, dict) or not isinstance(c.get("t"), (int, float)) or not isinstance(c.get("note"), str) or not isinstance(c.get("scene"), str):
                        raise ValueError("Invalid comment")
            except (ValueError, TypeError):
                return self.send_error(400)
            batch_id = f"{time.time_ns()}-{uuid.uuid4().hex[:8]}"
            context = read_json(os.path.join(work, "review-context.json"), {})
            current_video = context.get("video", video)
            frames = save_frames(data, current_video, os.path.join(work, "review-frames", batch_id))
            markdown = notes_markdown(data, context.get("scenes", scenes), current_video, frames, context.get("words", words))
            folder = os.path.join(work, "feedback-batches")
            markdown_path = os.path.join(folder, batch_id + ".md")
            atomic_text(markdown_path, markdown)
            batch = {"status": "feedback", "batch_id": batch_id, "feedback_path": markdown_path,
                     "feedback": markdown, "approved": not data.get("comments") and not data.get("overall", "").strip()}
            atomic_text(os.path.join(folder, batch_id + ".json"), json.dumps(batch))
            atomic_text(feedback, markdown)
            self.reply({"ok": True, "batch_id": batch_id, "agent": agent_status(work)["state"]})
            print(f"Feedback saved: {markdown_path}", flush=True)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/api/version":
                return self.reply({"version": os.stat(page).st_mtime_ns})
            if path == "/api/health":
                return self.reply({"work": work})
            if path == "/api/status":
                return self.reply(agent_status(work))
            file, rng = self.translate_path(path), self.headers.get("Range")
            if not rng or not os.path.isfile(file):
                return super().do_GET()
            size = os.path.getsize(file)
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng)
            if not m or not any(m.groups()):
                return self.range_error(size)
            if not m.group(1):
                start, end = max(0, size - int(m.group(2))), size - 1
            else:
                start = int(m.group(1))
                end = min(int(m.group(2)) if m.group(2) else size - 1, size - 1)
            if start > end or start >= size:
                return self.range_error(size)
            self.send_response(206)
            self.send_header("Content-Type", self.guess_type(file))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            with open(file, "rb") as f:
                f.seek(start); left = end - start + 1
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    left -= len(chunk)

        def range_error(self, size):
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(root, page, feedback, scenes, video, port, open_browser, timeout, words=None):
    """Keep media available across submissions; the agent listens with a separate foreground poll."""
    work = os.path.dirname(os.path.abspath(feedback))
    atomic_text(os.path.join(work, "review-context.json"), json.dumps({"video": video, "scenes": scenes, "words": words}))
    info_path = os.path.join(work, "review-server.json")
    info = read_json(info_path, {})
    existing = info.get("url", "")
    if existing.startswith("http://127.0.0.1:"):
        try:
            health = json.load(urlopen(existing.split("/review/")[0] + "/api/health", timeout=1))
            if health.get("work") == work:
                print(f"Review page: {existing}\nReused running review server. Poll for feedback with --poll {work}", flush=True)
                if open_browser:
                    webbrowser.open(existing)
                return
        except (OSError, ValueError):
            pass
    try:
        server = build_server(root, page, feedback, scenes, video, port, words)
    except OSError:
        server = build_server(root, page, feedback, scenes, video, 0, words)
    url = f"http://127.0.0.1:{server.server_port}/" + os.path.relpath(page, root)
    atomic_text(info_path, json.dumps({"url": url, "pid": os.getpid()}))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Review page: {url}\nMedia stays available after Send. Listen with --poll {work}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        threading.Event().wait(timeout)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown(); server.server_close()


PAGE = """<!DOCTYPE html>
<html data-theme="light"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Video review</title>
<style>{css}</style></head>
<body>
  <main class="stage">
    <div class="player" id="player">
      <video id="v" src="{src}" playsinline preload="auto"></video>
      <canvas id="picture" aria-label="Video preview"></canvas>
      <img id="poster" src="{poster}" alt="Video loading" />
    </div>
    <div id="media-status" class="media-status" role="status"></div>
    <div class="controls">
      <div class="row"><button id="play" class="play" type="button" aria-label="Play or pause">▶</button><span id="tc" class="tc"></span><span id="scene" class="chip"></span><select id="speed" class="speed" aria-label="Playback speed"><option value="0.25">0.25×</option><option value="0.5">0.5×</option><option value="0.75">0.75×</option><option value="1">Normal</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="1.75">1.75×</option><option value="2">2×</option></select><button id="keysbtn" class="icon-btn push" type="button" aria-label="Keyboard shortcuts">?</button></div>
      <div id="keys" class="keys" hidden>
        <div><span>Play or pause</span><kbd>Space</kbd></div>
        <div><span>One frame</span><span><kbd>←</kbd> <kbd>→</kbd></span></div>
        <div><span>One second</span><span><kbd>Shift</kbd> + arrows</span></div>
        <div><span>Playback speed</span><span><kbd>&lt;</kbd> <kbd>&gt;</kbd></span></div>
        <div><span>Comment on this frame</span><kbd>C</kbd></div>
        <div><span>Add comment</span><kbd>Enter</kbd></div>
        <div><span>Back to the video</span><kbd>Esc</kbd></div>
      </div>
      <div id="bar"><div id="head"></div></div>
    </div>
  </main>
  <aside class="rail">
    <div class="rail-scroll">
      <div class="rail-head"><span class="section">Video review</span><span id="count" class="dim"></span>
        <button id="theme" class="icon-btn push" type="button" aria-label="Toggle light or dark mode">☀</button></div>
      <div class="compose">
        <div class="compose-head"><span class="chip" id="at">0:00.00</span></div>
        <textarea id="note" placeholder="What should change here?"></textarea>
        <div class="compose-foot"><button id="add" class="btn push" type="button" disabled>Add comment<span class="key">⏎</span></button></div>
      </div>
      <div id="list" class="cards"></div>
    </div>
    <div class="rail-foot">
      <textarea id="overall" placeholder="Overall note (optional)"></textarea>
      <button id="send" class="send" type="button">Looks good</button>
      <div id="agent-status" class="dim" role="status"></div>
      <div id="status" role="status"></div>
    </div>
  </aside>
  <script>
    const SCENES = {scenes};
    const DUR = {dur}, FPS = {fps};
    {js}
  </script>
</body></html>"""


