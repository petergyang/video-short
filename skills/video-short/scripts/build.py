"""Build edit.md into the HyperFrames project (PROJECT/hf) that render.py renders.
The project holds the cut video, one host per scene (speaker, split, or full-screen visual), animated cards,
captions on their own track, and the audio mix. Every time comes from the cut timeline in edit.md."""
import hashlib, html, json, os, re, shutil, subprocess

import numpy as np
from common import (FPS, H, SPLIT_TOP, W, die, frames, load_style, parse_edit, parse_framing, probe, project_paths,
                    run, setting, validate_scenes)

SR = 48000
PUSH = 1.02   # every speaker shot drifts in this much over the shot, so no frame looks frozen


def esc(s):
    return html.escape(str(s))


def css_color(hex_color):
    h = hex_color.lstrip("#")
    if len(h) == 6:
        return "#" + h
    r, g, b, a = (int(h[i:i + 2], 16) for i in (0, 2, 4, 6))
    return f"rgba({r},{g},{b},{a / 255:.3f})"


def speaker_box(src_w, src_h, fx, fy, out_w, out_h, zoom, face_at):
    """Position of the camera video inside an out_w x out_h panel: face centered, face_at of the way down."""
    s = max(out_w / src_w, out_h / src_h) * zoom
    sw, sh = src_w * s, src_h * s
    x = (sw - out_w) / 2 if sw < out_w else min(max(fx * sw - out_w / 2, 0), sw - out_w)   # narrower than the panel: center it
    y = min(max(fy * sh - face_at * out_h, 0), sh - out_h)
    return -x, -y, sw, sh, fx * sw - x, fy * sh - y   # left, top, width, height, face point in the panel


EASE = "(3*pow(min(t/{d},1),2)-2*pow(min(t/{d},1),3))"   # smoothstep over the scene, for zooms and page drifts


def edge_color(path, start):
    """The clip's background color at its left edge, to pad around a zoom window that reaches past the frame."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", path, "-frames:v", "1", "-vf", "crop=8:8:4:ih/2,scale=1:1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return "0x" + raw[:3].hex() if len(raw) >= 3 else "black"


def prep_clip(vis, dur, out, panel=None):
    """Make the clip exactly the scene's length, muted, at 30 fps, so seeks are exact. A short clip loops, or with
    `hold` freezes on its last frame. `zoom` eases a window across the clip; `page` drifts a still capture down."""
    if os.path.isfile(out):
        return
    enc = ["-an", "-c:v", "libx264", "-crf", "17", "-g", "15", "-pix_fmt", "yuv420p", out]
    pw, ph = panel or (W, H)
    if vis.get("page"):
        y0, y1 = vis["page"]
        y = f"min(ih-oh,{y0}+({y1 - y0})*{EASE.format(d=dur)})"
        run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", vis["abs"],
             "-vf", f"scale={pw}:-2,pad=iw:max(ih\\,{ph}):0:0:white,crop={pw}:{ph}:0:'{y}',fps={FPS}", "-frames:v", str(frames(dur)), *enc])
        return
    src = ["-ss", f"{vis['start']:.3f}", "-i", vis["abs"]]
    if vis.get("end"):
        src[2:2] = ["-to", f"{vis['end']:.3f}"]
    if vis.get("hold"):   # play once, then freeze the last frame for the rest of the scene
        chain = [f"fps={FPS}", f"tpad=stop_mode=clone:stop_duration={dur:.3f}"]
    else:
        loop = ["-ignore_loop", "0"] if vis["abs"].lower().endswith(".gif") else ["-stream_loop", "-1"]
        src = loop + src
        chain = [f"fps={FPS}"]
    if vis.get("zoom"):   # pad the clip to the panel's shape, then ease a window from one region to another
        cw, ch, _ = probe(vis["abs"])
        a = pw / ph
        padw, padh = (round(ch * a / 2) * 2, ch) if cw / ch < a else (cw, round(cw / a / 2) * 2)
        ox, oy = (padw - cw) // 2, (padh - ch) // 2
        (x0, y0, w0), (x1, y1, w1) = vis["zoom"]
        e = EASE.replace("t/{d}", f"on/{max(frames(dur) - 1, 1)}")
        ww = f"(({w0})+(({w1})-({w0}))*{e})*{cw}"
        cx, cy = f"(({x0})+(({x1})-({x0}))*{e})*{cw}+{ox}", f"(({y0})+(({y1})-({y0}))*{e})*{ch}+{oy}"
        chain += [f"pad={padw}:{padh}:{ox}:{oy}:color={edge_color(vis['abs'], vis['start'])}",
                  f"zoompan=z='{padw}/({ww})':x='max(0,min(iw-iw/zoom,{cx}-iw/zoom/2))':y='max(0,min(ih-ih/zoom,{cy}-ih/zoom/2))'"
                  f":d=1:s={pw}x{ph}:fps={FPS}"]
    else:
        chain.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
    run(["ffmpeg", "-v", "error", "-y", *src, "-t" if not vis.get("hold") else "-frames:v",
         f"{dur:.3f}" if not vis.get("hold") else str(frames(dur)), "-vf", ",".join(chain), *enc])


def number_parts(v):
    m = re.search(r"-?[\d,]*\.?\d+", v)
    num = m.group(0)
    return v[:m.start()], float(num.replace(",", "")), v[m.end():], len(num.split(".")[1]) if "." in num else 0


def synth_sfx(kind, sr=SR):
    """Very quiet, dry sounds made here, so nothing needs a license: a soft tap and a short air swell."""
    rng = np.random.default_rng(7 if kind == "tap" else 11)
    if kind == "tap":
        n = int(.045 * sr)
        x = rng.standard_normal(n) * np.exp(-np.linspace(0, 9, n))
        x = np.convolve(x, np.ones(18) / 18, "same")
    else:
        n = int(.32 * sr)
        x = rng.standard_normal(n)
        x = np.convolve(x, np.ones(60) / 60, "same") * np.sin(np.linspace(0, np.pi, n)) ** 2
    x /= np.max(np.abs(x)) + 1e-9
    return np.stack([x, x], 1) * (0.05 if kind == "tap" else 0.035)


def emphasis_spans(words, emphasis):
    """Word index ranges in this caption that match an '## Emphasis' phrase (whole words, any case)."""
    norm = lambda t: re.sub(r"[^\w.$%]+", "", t.lower())
    toks, spans = [norm(w) for w in words], []
    for phrase in emphasis:
        p = [norm(t) for t in phrase.split()]
        for i in range(len(toks) - len(p) + 1):
            if toks[i:i + len(p)] == p:
                spans.append((i, i + len(p)))
    return spans


# ---------- captions ----------

def clean_word(w):
    return re.sub(r"^[\"'“‘(]+|[\"”’),.!?;:]+$", "", w)


def apply_fixes(words, fixes):
    """Apply '## Caption fixes' at the word level, so a multi-word fix such as 'Anti Gravity -> Antigravity'
    works even when the words would land in different captions."""
    words = [dict(w) for w in words]
    for wrong, right in fixes:
        target = [t.lower() for t in wrong.split()]
        i = 0
        while i <= len(words) - len(target):
            seg = words[i:i + len(target)]
            if [clean_word(w["text"]).lower() for w in seg] == target:
                tail = re.search(r"[,.!?;:]*$", seg[-1]["text"]).group(0)
                words[i:i + len(target)] = [{"text": right + tail, "start": seg[0]["start"], "end": seg[-1]["end"]}]
            i += 1
    return words


def caption_chunks(words, fixes, max_words=3, max_chars=18):
    """Up to max_words per caption, split at punctuation and pauses, shown 2 frames before the first word."""
    words = apply_fixes(words, fixes)
    chunks, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        chars = sum(len(x["text"]) + 1 for x in cur)
        punct = w["text"][-1:] in ".,!?;:"
        gap = nxt["start"] - w["end"] if nxt else 9
        if nxt is None or len(cur) >= max_words or punct or gap >= 0.14 or chars + len(nxt["text"]) > max_chars:
            text = " ".join(t for t in (clean_word(x["text"]) for x in cur) if t)
            if text:
                start = max(0.0, cur[0]["start"] - 2 / FPS)
                if chunks and chunks[-1]["end"] > start:
                    chunks[-1]["end"] = start
                chunks.append({"start": start, "end": cur[-1]["end"] + 0.05, "text": text})
            cur = []
    return chunks


def caption_y(layout, style):
    pos = {"a-roll": 1400, "punch": 1400, "split": SPLIT_TOP, "b-roll": 1440}   # B-roll captions clear the Shorts like and comment buttons
    pos.update(style.get("caption_y", {}))
    return pos[layout]


def caption_track(chunks, scenes, total_frames):
    """Frame-quantized list of (start_frame, end_frame, text, y_layout), split wherever the layout changes."""
    out = []
    for c in chunks:
        a, b = frames(c["start"]), min(total_frames, frames(c["end"]))
        pieces = [(max(a, frames(sc["start"])), min(b, frames(sc["end"])), c["text"], sc["layout"]) for sc in scenes]
        pieces = [p for p in pieces if p[1] > p[0]]
        # A sliver on the far side of a cut flickers in the old position, so a split caption drops pieces under 4 frames.
        out += [p for p in pieces if len(pieces) == 1 or p[1] - p[0] >= 4]
    return out


def receipt_panel(sc, i, t0, d, out_h, top, A, js, sfx):
    """A cited screenshot as a card centered in its panel, never cropped, with each marked line highlighted in turn."""
    v, sid = sc["visual"], sc["id"]
    key = f"{os.path.realpath(v['abs'])}|{os.path.getmtime(v['abs'])}"
    name = f"{sid}-{hashlib.md5(key.encode()).hexdigest()[:8]}{os.path.splitext(v['abs'])[1].lower()}"
    shutil.copy(v["abs"], os.path.join(A, "clips", name))
    iw, ih, _ = probe(v["abs"])
    s = min(960 / iw, (out_h - 120) / ih)
    w, h = iw * s, ih * s
    if w < 760:
        print(f"warning: {sid} receipt shows at {w:.0f}px wide; crop the screenshot to the lines that matter so it reads on a phone")
    marks = "".join(f'<div id="{sid}m{k}" class="mark" style="left:{x * 100:.2f}%;top:{y * 100:.2f}%;width:{mw * 100:.2f}%;height:{mh * 100:.2f}%"></div>'
                    for k, (x, y, mw, mh) in enumerate(v["marks"]))
    js.append(f'gsap.set("#{sid}rc", {{ autoAlpha: 0 }});')
    js.append(f'tl.fromTo("#{sid}rc", {{ autoAlpha: 0, y: 40 }}, {{ autoAlpha: 1, y: 0, duration: .4, ease: "power3.out", immediateRender: false }}, {t0:.3f});')
    js.append(f'tl.fromTo("#{sid}rc", {{ scale: 1 }}, {{ scale: 1.03, duration: {d:.3f}, ease: "none", immediateRender: false }}, {t0:.3f});')
    sfx.append(("tap", t0))
    for k in range(len(v["marks"])):   # the highlighter sweeps across each marked line, one after another
        js.append(f'gsap.set("#{sid}m{k}", {{ scaleX: 0 }});')
        js.append(f'tl.fromTo("#{sid}m{k}", {{ scaleX: 0 }}, {{ scaleX: 1, duration: .45, ease: "power2.inOut", immediateRender: false }}, {t0 + .5 + .5 * k:.3f});')
    return (f'<div class="panel vis cardbg" style="top:{top}px;height:{out_h}px"><div id="{sid}rc" class="receipt" style="width:{w:.0f}px;height:{h:.0f}px">'
            f'<img src="assets/clips/{name}" alt="">{marks}</div></div>')


# ---------- audio ----------

def read_pcm(path, seconds):
    raw = run_bytes(["ffmpeg", "-v", "error", "-i", path, "-t", f"{seconds:.4f}", "-vn", "-ac", "2", "-ar", str(SR),
                     "-f", "f32le", "-"])
    a = np.frombuffer(raw, dtype=np.float32)
    return a[: len(a) // 2 * 2].reshape(-1, 2).astype(np.float64)


def run_bytes(cmd):
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode:
        die(f"{cmd[0]} failed: {r.stderr.decode()[-800:]}")
    return r.stdout


def lufs(pcm):
    r = subprocess.run(["ffmpeg", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-af", "ebur128", "-f", "null", "-"],
                       input=pcm.astype(np.float32).tobytes(), capture_output=True)
    m = re.findall(rb"I:\s+(-?[\d.]+)\s+LUFS", r.stderr)
    return float(m[-1]) if m else -70.0


def fit_length(pcm, n):
    if len(pcm) >= n:
        return pcm[:n]
    return np.vstack([pcm, np.zeros((n - len(pcm), 2))])


def duck_curve(voice, n, dip_db=5.0, hop=0.05):
    """Gain for the music bed: down dip_db while the voice talks, back up in pauses. Fast attack, slow release,
    so the bed doesn't pump between words."""
    h = int(hop * SR)
    frames_ = max(1, n // h)
    mono = voice[:frames_ * h].mean(axis=1).reshape(frames_, h)
    db = 10 * np.log10(np.mean(mono ** 2, axis=1) + 1e-12)
    talk = (db > np.percentile(db, 90) - 25).astype(float)   # within 25 dB of the voice's loud parts counts as speech
    g = np.empty(frames_)
    level = 0.0
    for i, t in enumerate(talk):   # attack in about 0.1s, release over about 0.5s
        level += (t - level) * (0.5 if t > level else 0.1)
        g[i] = level
    gain = 10 ** (-dip_db * g / 20)
    return np.interp(np.arange(n), np.arange(frames_) * h + h / 2, gain)


def mix_audio(clean, music, level_db, duration, out_wav, lifts=()):
    n = int(round(duration * SR))
    voice = fit_length(read_pcm(clean, duration), n)
    v = lufs(voice)
    if v > -60:
        voice *= min(10 ** ((-14 - v) / 20), 8.0)
    mix = voice.copy()
    if music:
        bed = read_pcm(music, duration + 1)
        while 0 < len(bed) < n:
            bed = np.vstack([bed, bed])
        bed = fit_length(bed, n)
        b = lufs(bed)
        if b > -60:
            bed *= 10 ** ((-14 + level_db - b) / 20)
        bed *= duck_curve(voice, n)[:, None]
        for a, z in lifts:   # 'Music lift' ranges: the bed rises 9 dB with short ramps, for a beat where the music is the point
            env = np.ones(n)
            i, j, r = int(a * SR), min(n, int(z * SR)), int(0.25 * SR)
            if j > i:
                env[i:j] = 10 ** (9 / 20)
                env[max(0, i - r):i] = np.linspace(1, 10 ** (9 / 20), i - max(0, i - r))
                env[j:min(n, j + r)] = np.linspace(10 ** (9 / 20), 1, min(n, j + r) - j)
                bed *= env[:, None]
        ramp = min(n, int(1.2 * SR))
        bed[:ramp] *= np.linspace(0.4, 1.0, ramp)[:, None]  # keep the opening hook clear
        tail = min(n, int(0.6 * SR))
        bed[-tail:] *= np.linspace(1.0, 0.0, tail)[:, None]
        mix += bed
    m = lufs(mix)
    if m > -60:
        mix *= 10 ** ((-14 - m) / 20)
    ceiling = 10 ** (-1.5 / 20)
    if np.max(np.abs(mix)) > ceiling:
        mix = np.tanh(mix / ceiling) * ceiling  # soft limit instead of hard clipping
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", out_wav],
                       input=mix.astype(np.float32).tobytes(), capture_output=True)
    if p.returncode:
        die("could not write the audio mix")


# ---------- project ----------

def build(project, style_arg=None):
    paths = project_paths(project)
    if not os.path.isfile(paths["clean"]):
        die("work/clean.mp4 not found. Run cut.py first.")
    edit = parse_edit(paths["edit"])
    style = load_style(paths["root"], style_arg)
    src_w, src_h, duration = probe(paths["clean"])
    scenes = validate_scenes(edit, paths["root"], duration)
    fx, fy = parse_framing(edit)
    words = json.load(open(os.path.join(paths["work"], "transcript_clean.json"), encoding="utf-8"))
    total = frames(duration)
    dur = total / FPS
    hf = os.path.join(paths["root"], "hf")
    A = os.path.join(hf, "assets")
    os.makedirs(os.path.join(A, "fonts"), exist_ok=True)
    os.makedirs(os.path.join(A, "clips"), exist_ok=True)
    cam = os.path.join(A, "camera.mp4")
    if not os.path.isfile(cam) or os.path.getmtime(cam) < os.path.getmtime(paths["clean"]):
        run(["ffmpeg", "-v", "error", "-y", "-i", paths["clean"], "-an", "-c:v", "libx264", "-crf", "16", "-g", "15", "-pix_fmt", "yuv420p", cam])

    run(["ffmpeg", "-v", "error", "-y", "-i", cam, "-frames:v", "1", "-q:v", "4", os.path.join(A, "camera_bg.jpg")])
    cs, cd = style["caption"], style["card"]
    fonts = {}
    for key, path in (("cap", cs["font"]), ("title", cd["title_font"]), ("body", cd["body_font"]), ("num", cd["number_font"])):
        name = os.path.basename(path)
        shutil.copy(path, os.path.join(A, "fonts", name))
        fonts[key] = name
    face_css = "\n".join(f'@font-face {{ font-family: "F{k}"; src: url("assets/fonts/{v}"); font-weight: 100 900; }}' for k, v in fonts.items())

    # Duplicate clip check: each source moment is used once.
    seen = {}
    for sc in scenes:
        v = sc["visual"]
        if v and v["type"] == "clip":
            key = (os.path.realpath(v["abs"]), round(v["start"], 1))
            if key in seen:
                print(f"warning: {sc['id']} reuses the clip from {seen[key]} ({v['src']} @{v['start']}); use each clip once")
            seen[key] = sc["id"]

    # A list card that grows across scenes reserves room for its last row from the start, so it never moves.
    final_rows = {}
    for i in range(len(scenes) - 1, -1, -1):
        v = scenes[i]["visual"]
        if v and v["type"] == "card":
            nxt = scenes[i + 1]["visual"] if i + 1 < len(scenes) else None
            grows = nxt and nxt["type"] == "card" and nxt["title"] == v["title"] and nxt["rows"][:len(v["rows"])] == v["rows"]
            final_rows[i] = final_rows[i + 1] if grows else v["rows"]

    hosts, js, sfx = [], [], []
    prev_card = None
    for i, sc in enumerate(scenes):
        # Each scene starts half a frame before its first frame, so rounded times never leave a frame uncovered.
        t0, t1 = max(0.0, frames(sc["start"]) - .5) / FPS, (frames(sc["end"]) - .5) / FPS
        d = t1 - t0
        sid = sc["id"]
        lay = sc["layout"]
        parts = []

        def speaker(out_w, out_h, top, zoom, face_at):
            l, t, w, h, ox, oy = speaker_box(src_w, src_h, fx, fy, out_w, out_h, zoom, face_at)
            js.append(f'tl.fromTo("#{sid}push", {{ scale: 1 }}, {{ scale: {PUSH}, duration: {d:.3f}, ease: "none", immediateRender: false }}, {t0:.3f});')
            fill = '<img class="campad" src="assets/camera_bg.jpg" alt="">' if w < out_w else ""   # the room, blurred, behind a zoomed-out speaker
            return (f'<div class="panel" style="top:{top}px;height:{out_h}px">{fill}<div id="{sid}push" class="push" style="transform-origin:{ox:.0f}px {oy:.0f}px">'
                    f'<video id="{sid}cam" class="clip" src="assets/camera.mp4" data-start="{t0:.3f}" data-duration="{d:.3f}" data-media-start="{t0:.3f}" '
                    f'data-track-index="{10 + i}" muted playsinline style="left:{l:.1f}px;top:{t:.1f}px;width:{w:.1f}px;height:{h:.1f}px"></video></div></div>')

        def visual(out_h, top):
            v = sc["visual"]
            if v["type"] == "clip":
                opts = json.dumps([v.get(k) for k in ("start", "end", "zoom", "hold", "page")]) + f"|{W}x{out_h}"
                key = f"{os.path.realpath(v['abs'])}|{os.path.getmtime(v['abs'])}|{opts}|{d:.3f}"
                name = f"{sid}-{hashlib.md5(key.encode()).hexdigest()[:8]}.mp4"   # a changed clip, option, or length gets a fresh file
                prep_clip(v, d, os.path.join(A, "clips", name), (W, out_h))
                cw, ch, _ = probe(os.path.join(A, "clips", name))
                fit = v.get("fit") or ("fill" if abs(cw / ch - W / out_h) / (W / out_h) < .2 else "fit")   # crop only near-matching shapes, so text at the sides survives
                vid = lambda vid_id, cls, extra: (f'<video id="{vid_id}" class="clip {cls}" src="assets/clips/{name}" data-start="{t0:.3f}" data-duration="{d:.3f}" '
                                                  f'data-media-start="0" data-track-index="{40 + i * 2 + extra}" muted playsinline></video>')
                if fit == "fit":   # letterbox over a blurred still of the same clip
                    bg = os.path.join(A, "clips", name[:-4] + "-bg.jpg")
                    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{d / 2:.3f}", "-i", os.path.join(A, "clips", name), "-frames:v", "1", "-q:v", "4", bg])
                    inner = f'<img class="blurbg" src="assets/clips/{name[:-4]}-bg.jpg" alt="">' + vid(f"{sid}v", "contain", 0)
                else:
                    inner = vid(f"{sid}v", "cover", 0)
                js.append(f'tl.fromTo("#{sid}vis", {{ scale: 1 }}, {{ scale: 1.04, duration: {d:.3f}, ease: "none", immediateRender: false }}, {t0:.3f});')
                if lay == "b-roll":
                    sfx.append(("air", t0))
                return f'<div class="panel vis" style="top:{top}px;height:{out_h}px"><div id="{sid}vis" class="push">{inner}</div></div>'
            if v["type"] == "receipt":
                return receipt_panel(sc, i, t0, d, out_h, top, A, js, sfx)
            if v["type"] == "graphic":   # the agent's own HyperFrames sub-composition, copied in so it is self-contained
                text = open(v["abs"], encoding="utf-8").read()
                m = re.search(r'data-composition-id="([^"]+)"', text)
                if not m:
                    die(f"{v['src']}: a graphic needs a root element with data-composition-id (see reference.md)")
                os.makedirs(os.path.join(hf, "graphics"), exist_ok=True)
                shutil.copy(v["abs"], os.path.join(hf, "graphics", f"{sid}.html"))
                return (f'<div class="panel vis" style="top:{top}px;height:{out_h}px"><div id="{sid}g" class="clip" data-composition-id="{m.group(1)}" '
                        f'data-composition-src="graphics/{sid}.html" data-start="{t0:.3f}" data-duration="{d:.3f}" data-track-index="{40 + i * 2}" '
                        f'style="position:absolute;inset:0"></div></div>')
            if v["type"] == "number":
                pre, val, suf, dec = number_parts(v["value"])
                js.append(f'countUp("#{sid}num", {val}, {dec}, {json.dumps(pre)}, {json.dumps(suf)}, {t0 + .1:.3f}, .9);')
                js.append(f'gsap.set("#{sid}lab", {{ autoAlpha: 0 }});')
                js.append(f'tl.fromTo("#{sid}lab", {{ autoAlpha: 0, y: 18 }}, {{ autoAlpha: 1, y: 0, duration: .45, ease: "power3.out", immediateRender: false }}, {t0 + .35:.3f});')
                sfx.append(("tap", t0 + .1))
                size = 360 if out_h > 1200 else 280
                under = ""
                if v.get("bg"):   # the number sits on a darkened moving clip
                    bg = v["bg"]
                    key = f"{os.path.realpath(bg['abs'])}|{os.path.getmtime(bg['abs'])}|{bg['start']}|{d:.3f}"
                    name = f"{sid}-{hashlib.md5(key.encode()).hexdigest()[:8]}.mp4"
                    prep_clip(bg, d, os.path.join(A, "clips", name))
                    under = (f'<video id="{sid}bgv" class="clip cover" src="assets/clips/{name}" data-start="{t0:.3f}" data-duration="{d:.3f}" '
                             f'data-media-start="0" data-track-index="{40 + i * 2 + 1}" muted playsinline></video><div class="shade"></div>')
                return (f'<div class="panel vis cardbg" style="top:{top}px;height:{out_h}px">{under}<div class="numwrap">'
                        f'<div id="{sid}num" class="bignum" style="font-size:{size}px">{esc(pre)}0{esc(suf)}</div>'
                        f'<div id="{sid}lab" class="numlab">{esc(v["label"])}</div></div></div>')
            # card: a title with numbered rows. A card that repeats the previous scene's title only animates its new rows.
            nonlocal_prev = prev_card
            same = nonlocal_prev and nonlocal_prev["title"] == v["title"] and v["rows"][:len(nonlocal_prev["rows"])] == nonlocal_prev["rows"]
            shown = len(nonlocal_prev["rows"]) if same else 0
            big = out_h > 1200
            rows = "".join(f'<div id="{sid}r{k}" class="row"{"" if k < len(v["rows"]) else " style=\"visibility:hidden\""}>'
                           f'<span class="rn">{k + 1:02d}</span><span class="rt">{esc(r)}</span></div>' for k, r in enumerate(final_rows[i]))
            if not same:
                js.append(f'gsap.set("#{sid}card", {{ autoAlpha: 0 }});')
                js.append(f'tl.fromTo("#{sid}card", {{ autoAlpha: 0, y: 40 }}, {{ autoAlpha: 1, y: 0, duration: .4, ease: "power3.out", immediateRender: false }}, {t0:.3f});')
                sfx.append(("tap", t0))
            for k in range(len(v["rows"])):
                if k < shown:
                    continue
                tk = t0 + (.25 if not same else .05) + .14 * (k - shown)
                js.append(f'gsap.set("#{sid}r{k}", {{ autoAlpha: 0 }});')
                js.append(f'tl.fromTo("#{sid}r{k}", {{ autoAlpha: 0, x: -36 }}, {{ autoAlpha: 1, x: 0, duration: .35, ease: "power3.out", immediateRender: false }}, {tk:.3f});')
                sfx.append(("tap", tk))
            return (f'<div class="panel vis cardbg" style="top:{top}px;height:{out_h}px"><div id="{sid}card" class="card{" big" if big else ""}">'
                    f'<div class="title">{esc(v["title"])}</div><div class="rows">{rows}</div></div></div>')

        if lay in ("a-roll", "punch"):
            zoom = style.get("punch_zoom", 1.1) if lay == "punch" else 1.0
            parts.append(speaker(W, H, 0, zoom, .36))
        elif lay == "split":
            parts.append(visual(SPLIT_TOP, 0))
            # A landscape camera needs a push in to fill the panel; a vertical one already frames head and shoulders.
            # A landscape camera pushes in to fill the panel; a vertical one zooms out so the whole head and neck fit.
            parts.append(speaker(W, H - SPLIT_TOP, SPLIT_TOP, 1.2, .42) if src_w > src_h else speaker(W, H - SPLIT_TOP, SPLIT_TOP, .72, .42))
        else:
            parts.append(visual(H, 0))
        prev_card = sc["visual"] if sc["visual"] and sc["visual"]["type"] == "card" else None
        js.append(f'gsap.set("#{sid}", {{ autoAlpha: 0 }}); tl.set("#{sid}", {{ autoAlpha: 1 }}, {t0:.3f}); tl.set("#{sid}", {{ autoAlpha: 0 }}, {t1:.3f});')
        hosts.append(f'  <div id="{sid}" class="scene" data-layout="{lay}">{"".join(parts)}</div>')

    # Captions: one track; each caption shows from its first frame to its last.
    track = caption_track(caption_chunks(words, edit["fixes"], cs.get("max_words", 3), cs.get("max_chars", 18)), scenes, total)
    caps = []
    for k, (fa, fb, text, layout) in enumerate(track):
        text = text.upper() if cs.get("uppercase", True) else text
        ws = text.split(" ")
        marks = set()
        if cs.get("emphasis"):
            for x, y in emphasis_spans(ws, edit["emphasis"]):
                marks.update(range(x, y))
        inner, j = [], 0
        while j < len(ws):   # one box per emphasized phrase, not per word
            m = j
            while m < len(ws) and (m in marks) == (j in marks):
                m += 1
            seg = esc(" ".join(ws[j:m]))
            inner.append(f'<span class="em">{seg}</span>' if j in marks else seg)
            j = m
        inner = " ".join(inner)
        caps.append(f'<div id="cap{k}" class="clip cap" data-start="{max(0.0, fa - .5) / FPS:.4f}" data-duration="{(fb - fa) / FPS:.4f}" data-track-index="100" '
                    f'style="top:{caption_y(layout, style)}px"><span class="band">{inner}</span></div>')

    # Audio: voice, optional music, optional subtle sound effects, leveled to -14 LUFS.
    music = setting(edit, "music")
    if music and music.lower() != "none":
        music = music if os.path.isabs(music) else os.path.join(paths["root"], music)
        if not os.path.isfile(music):
            die(f"music file not found: {music}")
    else:
        music = None
    level = float(re.findall(r"-?[\d.]+", setting(edit, "music level", "-18"))[0])
    mix = os.path.join(A, "mix.wav")
    lifts = [tuple(float(x) for x in r.split("-")) for r in re.findall(r"\d+(?:\.\d+)?-\d+(?:\.\d+)?", setting(edit, "music lift", ""))]
    mix_audio(paths["clean"], music, level, dur, mix, lifts)
    if (setting(edit, "sound effects") or style.get("sound_effects", "off")).lower() in ("subtle", "on"):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", mix, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], capture_output=True).stdout
        m = np.frombuffer(raw, np.float32).reshape(-1, 2).astype(np.float64).copy()
        for kind, t in sfx:
            s = synth_sfx(kind)
            k = int(t * SR)
            e = min(len(m), k + len(s))
            if k < len(m):
                m[k:e] += s[:e - k]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", mix],
                       input=m.astype(np.float32).tobytes(), check=True)

    # The root duration sits just under the last frame, so HyperFrames never renders an extra one.
    page = PAGE.format(dur=f"{(total - .25) / FPS:.4f}", W=W, H=H, faces=face_css, bg=css_color(style.get("background", "#0B0B0D")),
                       cap_size=cs["size"], cap_color=css_color(cs["color"]), cap_box=css_color(cs["box"]),
                       cap_radius=cs.get("radius", 8), pad_x=cs.get("pad", [36, 20])[0], pad_y=cs.get("pad", [36, 20])[1],
                       cap_border=css_color(cs.get("border", "#00000000")), em=css_color(cs.get("emphasis") or cd["accent"]),
                       card_bg=css_color(cd["background"]), panel=css_color(cd["panel"]), border=css_color(cd["border"]),
                       text=css_color(cd["text"]), accent=css_color(cd["accent"]),
                       hosts="\n".join(hosts), w_cap=cs.get("weight", 500), w_title=cd.get("title_weight", 800),
                       w_body=cd.get("body_weight", 600), w_num=cd.get("number_weight", 800), caps="\n  ".join(caps), script="\n".join(js))
    open(os.path.join(hf, "index.html"), "w", encoding="utf-8").write(page)
    print(f"Built {len(scenes)} scenes and {len(track)} captions ({dur:.2f}s).")
    return hf, mix, dur


PAGE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Short</title>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
{faces}
html, body {{ margin: 0; width: 100%; height: 100%; overflow: hidden; background: {bg}; }}
#root {{ position: relative; width: {W}px; height: {H}px; overflow: hidden; background: {bg}; }}
.scene {{ position: absolute; inset: 0; }}
.panel {{ position: absolute; left: 0; width: {W}px; overflow: hidden; background: #000; }}
.push {{ position: absolute; inset: 0; }}
.push video {{ position: absolute; }}
.campad {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; filter: blur(30px) brightness(.85); transform: scale(1.15); }}
.vis video.cover, .vis video.contain, .vis .blurbg {{ position: absolute;  left: 0; top: 0; width: 100%; height: 100%; }}
.vis video.cover {{ object-fit: cover; }}
.vis video.contain {{ object-fit: contain; }}
.vis .blurbg {{ object-fit: cover; filter: blur(28px) brightness(.8); transform: scale(1.1); }}
.cardbg {{ background: {card_bg}; display: flex; justify-content: center; align-items: center; }}
.card {{ width: 960px; box-sizing: border-box; padding: 52px 56px; border-radius: 28px; background: {panel}; border: 2px solid {border}; }}
.card.big {{ width: 960px; padding: 64px; }}
.card .title {{ font: {w_title} 100px/1.1 Ftitle, sans-serif; color: {text}; }}
.card.big .title {{ font-size: 120px; }}
.card .rows {{ margin-top: 30px; }}
.card .row {{ display: flex; gap: 30px; align-items: baseline; margin-top: 34px; font: {w_body} 68px/1.2 Fbody, sans-serif; color: {text}; }}
.card.big .row {{ font-size: 80px; }}
.card .rn {{ font: {w_num} 56px/1 Fnum, sans-serif; color: {accent}; flex: none; width: 90px; }}
.numwrap {{ position: relative; text-align: center; }}
.vis .shade {{ position: absolute; inset: 0; background: rgba(0,0,0,.68); }}
.bignum, .numlab {{ text-shadow: 0 4px 30px rgba(0,0,0,.6); }}
.bignum {{ font-family: Fnum, sans-serif; font-weight: {w_num}; color: {accent}; line-height: 1; }}
.numlab {{ margin-top: 32px; font: {w_body} 76px/1.2 Fbody, sans-serif; color: {text}; padding: 0 60px; }}
.receipt {{ position: relative; border-radius: 22px; overflow: hidden; box-shadow: 0 18px 50px rgba(0,0,0,.45); background: #fff; }}
.receipt img {{ position: absolute; inset: 0; width: 100%; height: 100%; }}
.receipt .mark {{ position: absolute; background: #FFE34D; mix-blend-mode: multiply; transform-origin: left center; border-radius: 4px; }}
.cap {{ position: absolute; left: 0; width: {W}px; z-index: 50; text-align: center; transform: translateY(-50%); }}
.cap .band {{ display: inline-block; max-width: 880px; padding: {pad_y}px {pad_x}px; border-radius: {cap_radius}px; background: {cap_box};
             box-shadow: 0 0 0 2px {cap_border}; font: {w_cap} {cap_size}px/1.2 Fcap, sans-serif; color: {cap_color}; }}
.cap .em {{ background: {em}; padding: 0 10px; border-radius: 4px; }}
</style></head><body>
<div id="root" data-composition-id="short" data-width="{W}" data-height="{H}" data-fps="30" data-start="0" data-duration="{dur}">
{hosts}
  <div id="captions">
  {caps}
  </div>
  <audio id="mix" src="assets/mix.wav" data-start="0" data-duration="{dur}" data-track-index="200"></audio>
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
function countUp(sel, to, dec, pre, suf, t, d) {{
  const o = {{ v: 0 }}, el = document.querySelector(sel);
  tl.fromTo(o, {{ v: 0 }}, {{ v: to, duration: d, ease: "power2.out", immediateRender: false,
    onUpdate: () => {{ el.textContent = pre + o.v.toLocaleString("en-US", {{ minimumFractionDigits: dec, maximumFractionDigits: dec }}) + suf; }} }}, t);
  tl.fromTo(sel, {{ scale: .9 }}, {{ scale: 1, duration: .5, ease: "back.out(1.6)", immediateRender: false }}, t);
}}
{script}
tl.to({{}}, {{ duration: {dur} }}, 0);
window.__timelines["short"] = tl;
</script></body></html>
"""
