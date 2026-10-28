"""Shared review page: one player with a scene timeline. The reviewer pauses or keeps playing, comments on any
frame, and clicks Send. serve() saves the notes as markdown, prints them, and exits.
Keep this file identical everywhere it is bundled."""
import html, json, os, re, subprocess, sys, threading, time, webbrowser
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
.stage { flex: 1; min-width: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 20px 28px; }
video { max-height: calc(100vh - 140px); max-width: 100%; width: auto; height: auto; background: #000; border-radius: 10px; cursor: pointer; display: block; }   /* the video's own shape: vertical Shorts and landscape videos both fit */
.stage video.wide { width: 100%; height: auto; }
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
  video { max-height: 46vh; }
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

// Theme: dark by default, remembered per browser.
const setTheme = (t) => { document.documentElement.dataset.theme = t; $("theme").textContent = t === "dark" ? "☀" : "☾"; store("review:theme", t); };
setTheme(store("review:theme") || "dark");
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
const toggle = () => (v.paused ? v.play() : v.pause());
// Playback speed: click to cycle, or < and > to step; remembered per browser.
const SPEEDS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];
const setSpeed = (r) => { v.playbackRate = r; $("speed").value = String(r); store("review:speed", String(r)); };
setSpeed(Number(store("review:speed")) || 1);
const stepSpeed = (d) => { const i = SPEEDS.indexOf(v.playbackRate); setSpeed(SPEEDS[Math.max(0, Math.min(SPEEDS.length - 1, (i < 0 ? 2 : i) + d))]); };
$("speed").onchange = (e) => { setSpeed(Number(e.target.value)); e.target.blur(); };
// A landscape video fills the stage width; a vertical one keeps its height.
v.addEventListener("loadedmetadata", () => v.classList.toggle("wide", v.videoWidth > v.videoHeight));
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
const updateSend = () => { $("send").textContent = hasNotes() ? "Send notes" : "Looks good"; };
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
note.oninput = () => ($("add").disabled = !note.value.trim());
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
  if (note.value.trim()) add();   // a typed note not yet added is still a note, not an approval
  $("send").disabled = true; $("status").textContent = "Sending…";
  try {
    const r = await fetch("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video: v.getAttribute("src").split("?")[0], comments: state.comments, overall: state.overall.trim() }) });
    if (!r.ok) throw new Error(r.status);
    const approved = !hasNotes();
    state = { comments: [], overall: "" }; $("overall").value = ""; save(); render();
    $("status").textContent = approved ? "Approved. Your agent has it." : "Sent. This page reloads when the next draft is ready.";
    $("send").disabled = false;
  } catch { $("status").textContent = "Couldn't reach your agent. Ask it to reopen the review page; your notes are saved here."; render(); $("send").disabled = false; }
};

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
                          "-of", "json", video], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout
    info = json.loads(out)
    num, den = info["streams"][0]["r_frame_rate"].split("/")
    return float(info["format"]["duration"]), round(int(num) / int(den))


def write_page(root, page, video, scenes):
    """Write the review page for video. scenes: [{id, start, end, layout, visual, spoken}] covering the whole video."""
    dur, fps = probe(video)
    src = "/" + os.path.relpath(video, root) + f"?v={int(os.path.getmtime(video))}"
    os.makedirs(os.path.dirname(page), exist_ok=True)
    open(page, "w", encoding="utf-8").write(PAGE.format(css=CSS, js=JS, src=html.escape(src), scenes=json.dumps(scenes), dur=dur, fps=fps))


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


def notes_markdown(data, scenes, video, frames=None):
    by_id = {s["id"]: s for s in scenes}
    frames = frames or {}
    lines = [f"# Review notes: {os.path.basename(video)}", ""]
    for i, c in enumerate(data.get("comments", [])):
        s = by_id.get(c["scene"], {})
        lines += [f"## {fmt(c['t'])} · {short(c['scene'])} ({s.get('layout', '')}, {s.get('visual', '')})",
                  f"Says: “{s.get('spoken', '')}”"] + ([f"Frame: {frames[i]}"] if i in frames else []) + ["", c["note"], ""]
    if data.get("overall"):
        lines += ["## Overall", data["overall"], ""]
    if len(lines) == 2:
        lines.append("Looks good. No notes.")
    return "\n".join(lines).strip() + "\n"


def serve(root, page, feedback, scenes, video, port, open_browser, timeout):
    """Serve root (page and video must sit under it), wait for Send, write feedback, print it, and exit."""
    done = threading.Event()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=root, **k)

        def log_message(self, *a):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
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
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            frames = save_frames(data, video, os.path.join(os.path.dirname(feedback), "review-frames"))
            open(feedback, "w", encoding="utf-8").write(notes_markdown(data, scenes, video, frames))
            self.reply({"ok": True})
            done.set()

        def do_GET(self):   # byte ranges, so the video can seek
            path = self.path.split("?")[0]
            if path == "/api/version":
                return self.reply({"version": os.path.getmtime(page)})
            file, rng = self.translate_path(path), self.headers.get("Range")
            if not rng or not os.path.isfile(file):
                return super().do_GET()
            size = os.path.getsize(file)
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            start = int(m.group(1)) if m and m.group(1) else 0
            end = min(int(m.group(2)) if m and m.group(2) else size - 1, size - 1)
            self.send_response(206)
            self.send_header("Content-Type", self.guess_type(file))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            with open(file, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    left -= len(chunk)

    if os.path.exists(feedback):
        os.remove(feedback)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:   # port busy: use any free one, and open the page since the old tab can't find it
        server, open_browser = ThreadingHTTPServer(("127.0.0.1", 0), Handler), True
    url = f"http://127.0.0.1:{server.server_port}/" + os.path.relpath(page, root)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Review page: {url}\nWaiting for Send (saves {feedback})...", flush=True)
    if open_browser:
        webbrowser.open(url)
    got = done.wait(timeout)
    time.sleep(0.3)
    server.shutdown()
    if not got:
        sys.exit("No notes before the timeout. Reopen the review page; it keeps unsent notes.")
    with open(feedback, encoding="utf-8") as f:
        notes = f.read()
    try:
        print(notes)
    except UnicodeEncodeError:   # a cp1252 console can't print an emoji or an arrow in a note; the file is already saved
        sys.stdout.buffer.write(notes.encode("utf-8") + b"\n")
        sys.stdout.flush()


PAGE = """<!DOCTYPE html>
<html data-theme="dark"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Video review</title>
<style>{css}</style></head>
<body>
  <main class="stage">
    <video id="v" src="{src}" playsinline preload="auto"></video>
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
      <div id="status"></div>
    </div>
  </aside>
  <script>
    const SCENES = {scenes};
    const DUR = {dur}, FPS = {fps};
    {js}
  </script>
</body></html>"""


