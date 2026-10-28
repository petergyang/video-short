"""Shared helpers: ffmpeg/ffprobe wrappers, style loading, and the edit.md parser."""
import json, os, re, shutil, subprocess, sys, wave

import numpy as np

FPS = 30
HF = "hyperframes@0.8.169"   # pinned, so renders and transcripts stay the same across machines
NPX = shutil.which("npx") or "npx"   # on Windows npx is npx.cmd, which subprocess cannot find by its bare name
W, H = 1080, 1920
SPLIT_TOP = 880  # split layout: B-roll panel is y 0..880, speaker panel is y 880..1920
LAYOUTS = ("a-roll", "punch", "split", "b-roll")
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def die(msg):
    sys.exit(f"error: {msg}")


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if r.returncode:
        die(f"{cmd[0]} failed:\n{r.stderr[-1500:]}")
    return r


def probe(path):
    """Return width, height, duration (seconds) of a media file."""
    out = run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
               "-of", "json", path]).stdout
    info = json.loads(out)
    vid = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    return vid.get("width"), vid.get("height"), float(info.get("format", {}).get("duration") or 0)


def frames(t):
    return int(round(t * FPS))


def project_paths(project):
    p = os.path.abspath(project)
    return {
        "root": p,
        "edit": os.path.join(p, "edit.md"),
        "work": os.path.join(p, "work"),
        "renders": os.path.join(p, "renders"),
        "clean": os.path.join(p, "work", "clean.mp4"),
        "words_clean": os.path.join(p, "work", "words_clean.json"),
    }


# ---------- audio energy ----------

def read_wav_mono(path):
    with wave.open(path, "rb") as wf:
        sr, ch = wf.getframerate(), wf.getnchannels()
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        pcm = pcm.reshape(-1, ch).mean(axis=1)
    return pcm, sr


def energy_db(pcm, sr, hop_s=0.01):
    hop = max(1, int(sr * hop_s))
    n = len(pcm) // hop
    if n == 0:
        return np.array([-90.0])
    rms = np.sqrt(np.mean(pcm[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-9)


def silence_threshold(db):
    """Adaptive threshold between the noise floor and typical speech level."""
    live = db[db > -85] if np.any(db > -85) else db  # ignore digital silence when finding the room-noise floor
    floor, speech = np.percentile(live, 10), np.percentile(live, 90)
    return max(floor + 0.3 * (speech - floor), -55.0)


# ---------- style ----------

def load_style(project, style_arg=None):
    """Style lookup: --style flag, then <project>/style.json, then ~/.config/video-short/style.json, then the default."""
    candidates = [style_arg, os.path.join(project, "style.json"),
                  os.path.expanduser("~/.config/video-short/style.json"),
                  os.path.join(SKILL_DIR, "styles", "default.json")]
    path = next(c for c in candidates if c and os.path.isfile(c))

    def resolved(p):
        data = json.load(open(p, encoding="utf-8"))
        base = os.path.dirname(os.path.abspath(os.path.expanduser(p)))
        for section in ("caption", "card"):
            for k, v in data.get(section, {}).items():
                if k.endswith("font"):
                    data[section][k] = os.path.normpath(os.path.join(base, os.path.expanduser(v)))
        return data

    style = resolved(os.path.join(SKILL_DIR, "styles", "default.json"))
    custom = resolved(path)
    for section in ("caption", "card"):
        style[section].update(custom.get(section, {}))
    style.update({k: v for k, v in custom.items() if k not in ("caption", "card")})
    for section in ("caption", "card"):
        for k, v in style[section].items():
            if k.endswith("font") and not os.path.isfile(v):
                die(f"style font not found: {v} (from {path})")
    style["_path"] = path
    return style


# ---------- edit.md ----------

def _num(s, line_no, what):
    try:
        return float(s)
    except ValueError:
        die(f"edit.md line {line_no}: {what} '{s}' is not a number")


def parse_edit(path):
    """Parse edit.md into {settings, cuts, scenes, fixes, emphasis}. Fails loudly with line numbers."""
    if not os.path.isfile(path):
        die(f"{path} not found")
    settings, cuts, scenes, fixes, emphasis = {}, [], [], [], []
    section, header = None, None
    for i, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.rstrip("\n")
        s = line.strip()
        if s.startswith("## "):
            section = s[3:].strip().lower()
            header = None
            continue
        if not s or s.startswith("# ") or s.startswith("<!--"):
            continue
        if section is None:
            m = re.match(r"([A-Za-z ]+):\s*(.*)$", s)
            if m:
                settings[m.group(1).strip().lower()] = (m.group(2).strip(), i)
            continue
        if section.startswith("cuts"):
            m = re.match(r"-\s*([\d.]+)\s*[-–—]\s*([\d.]+)", s)
            if not m:
                die(f"edit.md line {i}: cut must look like '- 0.42-6.10', got '{s}'")
            a, b = _num(m.group(1), i, "cut start"), _num(m.group(2), i, "cut end")
            if b <= a:
                die(f"edit.md line {i}: cut end {b} must be after start {a}")
            cuts.append((a, b))
        elif section.startswith("scenes"):
            if not s.startswith("|"):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if header is None:
                header = [c.lower() for c in cells]
                for need in ("id", "start", "end", "layout"):
                    if need not in header:
                        die(f"edit.md line {i}: scenes table needs a '{need}' column")
                continue
            if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                continue
            if len(cells) != len(header):
                die(f"edit.md line {i}: expected {len(header)} cells, got {len(cells)}. Escape '|' inside text as '/'.")
            row = dict(zip(header, cells))
            layout = row["layout"].lower()
            if layout not in LAYOUTS:
                die(f"edit.md line {i}: layout '{row['layout']}' must be one of {', '.join(LAYOUTS)}")
            scenes.append({
                "id": row["id"], "start": _num(row["start"], i, "start"), "end": _num(row["end"], i, "end"),
                "layout": layout, "visual": parse_visual(row.get("visual", ""), i),
                "note": row.get("note", ""), "line": i,
            })
        elif section.startswith("caption"):
            m = re.match(r"-\s*(.+?)\s*->\s*(.+)$", s)
            if m:
                fixes.append((m.group(1), m.group(2)))
        elif section.startswith("emphasis"):
            m = re.match(r"-\s*(.+)$", s)
            if m:
                emphasis.append(m.group(1).strip())
    return {"settings": settings, "cuts": cuts, "scenes": scenes, "fixes": fixes, "emphasis": emphasis}


def parse_visual(v, line_no):
    """'broll/x.mp4 @1.2-4 fit zoom .5,.5,.8>.3,.4,.4 hold' -> clip; 'receipt: broll/tweet.png mark .05,.3,.9,.12' -> a cited
    screenshot on a card with highlighted lines; 'page: broll/site.png 300>700' -> a page capture
    that drifts down; 'card: Title ; row ; row' -> card; 'number: 89.5% ; label' -> number;
    'graphic: graphics/x.html' -> a HyperFrames sub-composition the agent wrote; '' -> none."""
    v = v.strip()
    if not v:
        return None
    if v.lower().startswith("card:"):
        parts = [p.strip() for p in v[5:].split(";")]
        return {"type": "card", "title": parts[0], "rows": [p for p in parts[1:] if p]}
    if v.lower().startswith("number:"):
        parts = [p.strip() for p in v[7:].split(";")]
        if not re.search(r"\d", parts[0]):
            die(f"edit.md line {line_no}: number needs a value with digits, like 'number: 89.5% ; share of voice'")
        vis = {"type": "number", "value": parts[0], "label": parts[1] if len(parts) > 1 else ""}
        if len(parts) > 2 and parts[2].lower().startswith("over "):   # 'over broll/clip.mp4 @2': count up over a moving clip
            bg = parse_visual(parts[2][5:], line_no)
            vis["bg"] = bg if bg and bg["type"] == "clip" else die(f"edit.md line {line_no}: 'over' needs a clip path")
        return vis
    if v.lower().startswith("receipt:"):
        tokens = v[8:].split()
        rec = {"type": "receipt", "src": tokens[0] if tokens else "", "marks": []}
        it = iter(tokens[1:])
        for t in it:
            try:
                assert t == "mark"
                box = tuple(float(x) for x in next(it, "").split(","))
                assert len(box) == 4 and all(0 <= x <= 1 for x in box)
            except (ValueError, AssertionError):
                die(f"edit.md line {line_no}: receipt is 'receipt: path [mark X,Y,W,H]...', each mark a line's left, top, width, and height as fractions of the screenshot")
            rec["marks"].append(box)
        return rec
    if v.lower().startswith("graphic:"):
        return {"type": "graphic", "src": v[8:].strip()}
    if v.lower().startswith("page:"):   # a phone-width page capture, shown full width and drifting down
        tokens = v[5:].split()
        page = {"type": "clip", "src": tokens[0], "start": 0.0, "end": None, "fit": "fill", "page": (0.0, 160.0)}
        if len(tokens) > 1:
            m = re.fullmatch(r"(\d+(?:\.\d+)?)(?:>(\d+(?:\.\d+)?))?", tokens[1])
            if not m:
                die(f"edit.md line {line_no}: page drift is 'TOP>TOP' in pixels of the 1080-wide capture, like 300>700")
            y0 = float(m.group(1))
            page["page"] = (y0, float(m.group(2)) if m.group(2) else y0 + 160)
        return page
    tokens = v.split()
    clip = {"type": "clip", "src": tokens[0], "start": 0.0, "end": None, "fit": None, "zoom": None, "hold": False}
    it = iter(tokens[1:])
    for t in it:
        if t.startswith("@"):
            a, _, b = t[1:].partition("-")
            clip["start"] = _num(a, line_no, "clip start")
            clip["end"] = _num(b, line_no, "clip end") if b else None
        elif t in ("fit", "fill"):
            clip["fit"] = t
        elif t == "hold":
            clip["hold"] = True
        elif t == "zoom":
            spec = next(it, "")
            try:
                ends = [tuple(float(x) for x in part.split(",")) for part in spec.split(">")]
                assert len(ends) in (1, 2) and all(len(e) == 3 and 0 < e[2] <= 1.5 for e in ends)
            except (ValueError, AssertionError):
                die(f"edit.md line {line_no}: zoom is 'X,Y,W' or 'X,Y,W>X,Y,W': the center and the width shown, as fractions of the clip")
            clip["zoom"] = (ends[0], ends[-1])
            clip["fit"] = "fill"
    return clip


def setting(edit, key, default=None):
    v = edit["settings"].get(key)
    return v[0] if v else default


def validate_scenes(edit, project, duration):
    scenes = edit["scenes"]
    if not scenes:
        die("edit.md has no rows under '## Scenes'")
    if abs(scenes[0]["start"]) > 0.05:
        die(f"edit.md line {scenes[0]['line']}: first scene must start at 0")
    for a, b in zip(scenes, scenes[1:]):
        if abs(a["end"] - b["start"]) > 1.5 / FPS:
            die(f"edit.md line {b['line']}: scene starts at {b['start']} but previous scene ends at {a['end']}")
    for sc in scenes:
        if sc["end"] <= sc["start"]:
            die(f"edit.md line {sc['line']}: scene end must be after start")
        if sc["layout"] in ("split", "b-roll") and not sc["visual"]:
            die(f"edit.md line {sc['line']}: {sc['layout']} needs a visual (a clip path, 'receipt: ...', 'card: ...', 'number: ...', or 'graphic: ...')")
        vis = sc["visual"]
        if vis and vis["type"] in ("graphic", "receipt"):
            vis["abs"] = vis["src"] if os.path.isabs(vis["src"]) else os.path.join(project, vis["src"])
            if not os.path.isfile(vis["abs"]):
                die(f"edit.md line {sc['line']}: {vis['type']} not found: {vis['src']}")
        if vis and vis.get("bg"):
            b = vis["bg"]
            b["abs"] = b["src"] if os.path.isabs(b["src"]) else os.path.join(project, b["src"])
            if not os.path.isfile(b["abs"]):
                die(f"edit.md line {sc['line']}: clip not found: {b['src']}")
        if vis and vis["type"] == "clip":
            vis["abs"] = vis["src"] if os.path.isabs(vis["src"]) else os.path.join(project, vis["src"])
            if not os.path.isfile(vis["abs"]):
                die(f"edit.md line {sc['line']}: clip not found: {vis['src']}")
    last = scenes[-1]
    if abs(last["end"] - duration) > 0.6:
        die(f"edit.md line {last['line']}: last scene ends at {last['end']} but the cut video is {duration:.2f}s")
    last["end"] = duration
    return scenes


def parse_framing(edit):
    v = setting(edit, "framing", "0.5, 0.4")
    try:
        fx, fy = [float(x) for x in re.findall(r"[\d.]+", v)[:2]]
    except ValueError:
        die(f"edit.md: Framing must be 'x, y' fractions, got '{v}'")
    return fx, fy
