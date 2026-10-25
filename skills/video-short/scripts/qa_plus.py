"""Measure the editorial rules in SKILL.md that eval.md currently asks the agent to self-answer.
usage: qa_plus.py PROJECT        (reads edit.md and work/words_clean.json; no render needed)
writes work/qa/report_plus.md. Exit 0 when every check passes, 1 otherwise.

qa.py measures the file: size, fps, loudness, black frames. This measures the edit:
speaker share, B-roll shot length, clip reuse, scene edges on word boundaries, and
cuts that abandon a sentence. Judgment checks stay in eval.md for the agent."""
import json, os, re, sys

from common import parse_edit, project_paths

SPEAKER_LAYOUTS = ("a-roll", "punch", "split")
MIN_SPEAKER_SHARE = 0.50
MAX_BROLL_SHOT = 3.5
EDGE_EPS = 1 / 60.0          # half a frame: a boundary this close to a word edge is on it
TERMINAL = ".?!\"')"

# A cut that lands after one of these leaves the sentence in the air.
DANGLING = {
    "and", "but", "or", "so", "because", "that", "which", "who", "when", "while",
    "if", "than", "then", "as", "at", "by", "for", "from", "in", "into", "of",
    "on", "to", "with", "the", "a", "an", "my", "your", "our", "their", "its",
    "is", "was", "are", "were", "be", "been", "like", "about", "over", "under",
}


def load_words(paths):
    p = paths["words_clean"]
    if not os.path.isfile(p):
        return None
    return json.load(open(p, encoding="utf-8"))


def word_at(words, t):
    """The word straddling time t, if a boundary falls inside one."""
    for w in words:
        if w["start"] + EDGE_EPS < t < w["end"] - EDGE_EPS:
            return w
    return None


def last_word_before(words, t):
    prev = None
    for w in words:
        if w["end"] <= t + EDGE_EPS:
            prev = w
        else:
            break
    return prev


def bare(text):
    return re.sub(r"[^\w']", "", text).lower()


def hangs(word):
    """True when this word is a bad place to end a spoken segment."""
    if word is None:
        return False
    t = word["text"].rstrip()
    if t and t[-1] in TERMINAL:
        return False
    if t.endswith(","):
        return True
    return bare(t) in DANGLING


def opens_sentence(word):
    """True when this word reads as the start of a new sentence, not a continuation."""
    if word is None:
        return False
    t = word["text"].strip()
    return bool(t) and t[0].isupper()


def scene_clips(scene):
    """Every source clip a scene plays, as (src, start, end) on the clip's own timeline."""
    out, dur = [], scene["end"] - scene["start"]

    def add(v):
        if not isinstance(v, dict):
            return
        if v.get("type") == "clip" and v.get("src"):
            a = float(v.get("start") or 0.0)
            b = v.get("end")
            out.append((os.path.normpath(v["src"]), a, float(b) if b else a + dur))
        if isinstance(v.get("bg"), dict):
            add(v["bg"])

    add(scene.get("visual"))
    return out


def overlaps(a, b):
    return a[1] < b[2] - 1e-6 and b[1] < a[2] - 1e-6


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    paths = project_paths(sys.argv[1])
    edit = parse_edit(paths["edit"])
    scenes, cuts = edit["scenes"], edit["cuts"]
    if not scenes:
        sys.exit("edit.md has no scenes")
    words = load_words(paths)
    total = scenes[-1]["end"] - scenes[0]["start"]
    checks = []

    # 1. Speaker on screen for at least half the Short.
    spk = sum(s["end"] - s["start"] for s in scenes if s["layout"] in SPEAKER_LAYOUTS)
    share = spk / total if total else 0.0
    checks.append(("Speaker on screen for at least half the Short",
                   share >= MIN_SPEAKER_SHARE, f"{share * 100:.0f}% of {total:.1f}s"))

    # 2. No full-screen B-roll shot longer than 3.5s.
    long_broll = [(s["id"], s["end"] - s["start"]) for s in scenes
                  if s["layout"] == "b-roll" and s["end"] - s["start"] > MAX_BROLL_SHOT + 1e-6]
    checks.append((f"No full-screen B-roll shot over {MAX_BROLL_SHOT}s", not long_broll,
                   ", ".join(f"{i} {d:.2f}s" for i, d in long_broll) or "longest ok"))

    # 3. Each clip's seconds used once: the same source range twice is a repeat.
    used, dupes = {}, []
    for s in scenes:
        for c in scene_clips(s):
            for prev_id, prev in used.get(c[0], []):
                if overlaps(prev, c):
                    dupes.append(f"{c[0]} @{c[1]:.2f}-{c[2]:.2f} in {s['id']} repeats {prev_id}")
                    break
            used.setdefault(c[0], []).append((s["id"], c))
    checks.append(("Each clip's seconds used once", not dupes,
                   "; ".join(dupes) or f"{sum(len(v) for v in used.values())} clip uses, no repeat"))

    # 4 and 5 need the clean word times.
    if words is None:
        checks.append((f"Word times present ({os.path.basename(paths['words_clean'])})", False, "not found, ran cut.py?"))
    else:
        inside = []
        for s in scenes[1:]:
            w = word_at(words, s["start"])
            if w:
                inside.append(f"{s['id']} at {s['start']:.2f}s cuts '{w['text']}'")
        checks.append(("Every scene edge lands between words", not inside,
                       "; ".join(inside) or f"{len(scenes) - 1} edges clear"))

        joins, elapsed = [], 0.0
        for a, b in (cuts[:-1] if len(cuts) > 1 else []):
            elapsed += b - a
            out_w = last_word_before(words, elapsed)
            in_w = next((w for w in words if w["start"] >= elapsed - EDGE_EPS), None)
            if hangs(out_w) and opens_sentence(in_w):
                joins.append(f"join at {elapsed:.2f}s drops '{out_w['text']}' then restarts on '{in_w['text']}'")
        tail = words[-1] if words else None
        if tail is not None and not str(tail["text"]).rstrip().endswith(tuple(TERMINAL)):
            joins.append(f"ends mid-sentence on '{tail['text']}'")
        checks.append(("No cut abandons a sentence", not joins,
                       "; ".join(joins) or "every segment resolves"))

    shots = sorted(s["end"] - s["start"] for s in scenes)
    median = shots[len(shots) // 2]
    qa = os.path.join(paths["work"], "qa")
    os.makedirs(qa, exist_ok=True)
    lines = [f"# QA+ : {os.path.basename(paths['root'])}", ""]
    lines += [f"- [{'x' if ok else ' '}] {name}: {detail}" for name, ok, detail in checks]
    lines += ["", f"{len(scenes)} scenes over {total:.1f}s, median shot {median:.2f}s. "
                  "Pace, hook and taste are eval.md's job."]
    out = "\n".join(lines) + "\n"
    open(os.path.join(qa, "report_plus.md"), "w").write(out)
    print(out)
    sys.exit(0 if all(ok for _, ok, _ in checks) else 1)


if __name__ == "__main__":
    main()
