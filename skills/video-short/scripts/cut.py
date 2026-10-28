"""Apply the Cuts and Grade from edit.md (or the style's default grade) in one ffmpeg pass, then re-transcribe the cut video.
usage: cut.py PROJECT
       cut.py PROJECT --look [--grade FILTER]   (stills of the Source in work/look/ to judge framing and color)
reads edit.md (Source, Grade, ## Cuts); writes work/clean.mp4 and work/transcript_clean.md/.json.
--look draws a 10x10 grid, so the face center reads as x, y in tenths; with --grade each still is original | graded.
One pass keeps audio and video in sync across every join. Cut edges snap to the quietest 10ms
nearby and to the 30fps frame grid so no join lands on a waveform peak."""
import argparse, os, tempfile

import numpy as np
from common import FPS, die, energy_db, load_style, parse_edit, probe, project_paths, read_wav_mono, run, setting
from transcribe import transcribe


def snap(cuts, db, duration, hop=0.01):
    out = []
    for a, b in cuts:
        ka, kb = int(a / hop), int(b / hop)
        lo, hi = max(0, ka - 4), min(len(db) - 1, ka + 2)
        a = (lo + int(np.argmin(db[lo:hi + 1]))) * hop if hi > lo else a
        lo, hi = max(0, kb - 2), min(len(db) - 1, kb + 5)
        b = (lo + int(np.argmin(db[lo:hi + 1]))) * hop if hi > lo else b
        a, b = round(a * FPS) / FPS, min(duration, round(b * FPS) / FPS)
        if b - a >= 1.0 / FPS:
            out.append((a, b))
    return out


def look(src, out_dir, duration, grade, cuts=()):
    """Gridded stills at a quarter, half, and three quarters of the kept footage (or the whole file before Cuts exist)."""
    os.makedirs(out_dir, exist_ok=True)
    grid = "drawgrid=w=iw/10:h=ih/10:t=2:c=yellow@0.7"
    spans = sorted(cuts) or [(0, duration)]
    kept = sum(b - a for a, b in spans)
    times = []
    for k in (1, 2, 3):
        left = kept * k / 4
        for a, b in spans:
            if left <= b - a:
                times.append(a + left)
                break
            left -= b - a
    for t in times:
        out = os.path.join(out_dir, f"{'grade' if grade else 'frame'}_{t:06.2f}.jpg")
        vf = f"split[a][b];[b]{grade}[g];[a][g]hstack,{grid}" if grade else grid
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1", "-filter_complex", f"{vf},scale='min(1600,iw)':-2", "-q:v", "3", out])
        print(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--look", action="store_true")
    ap.add_argument("--grade")
    ap.add_argument("--style")
    a = ap.parse_args()
    paths = project_paths(a.project)
    edit = parse_edit(paths["edit"])
    src = setting(edit, "source")
    if not src:
        die("edit.md needs a 'Source: raw.mp4' line")
    src = src if os.path.isabs(src) else os.path.join(paths["root"], src)
    if a.look:
        return look(src, os.path.join(paths["work"], "look"), probe(src)[2], a.grade, edit["cuts"])
    if not edit["cuts"]:
        die("edit.md has no ranges under '## Cuts'")
    _, _, duration = probe(src)

    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "raw.wav")
        run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav])
        pcm, sr = read_wav_mono(wav)
        cuts = snap(sorted(edit["cuts"]), energy_db(pcm, sr), duration)

        parts, joins = [], ""
        fade = 0.012  # tiny audio fades stop clicks at each join
        for i, (lo, hi) in enumerate(cuts):
            parts.append(f"[0:v]trim=start={lo:.6f}:end={hi:.6f},setpts=PTS-STARTPTS,fps={FPS}[v{i}]")
            parts.append(f"[0:a]atrim=start={lo:.6f}:end={hi:.6f},asetpts=PTS-STARTPTS,"
                         f"afade=t=in:d={fade},afade=t=out:st={max(0, hi - lo - fade):.6f}:d={fade}[a{i}]")
            joins += f"[v{i}][a{i}]"
        grade = setting(edit, "grade") or load_style(paths["root"], a.style).get("grade", "")
        grade_chain = f",{grade}" if grade and grade.lower() != "none" else ""
        parts.append(f"{joins}concat=n={len(cuts)}:v=1:a=1[vc][ac]")
        parts.append(f"[vc]setsar=1{grade_chain},format=yuv420p[vout]")
        script = os.path.join(tmp, "cut.txt")
        open(script, "w", encoding="utf-8").write(";\n".join(parts))
        os.makedirs(paths["work"], exist_ok=True)
        run(["ffmpeg", "-v", "error", "-y", "-i", src, "-filter_complex_script", script,
             "-map", "[vout]", "-map", "[ac]", "-c:v", "libx264", "-preset", "fast", "-crf", "16",
             "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", paths["clean"]])

    _, _, clean_dur = probe(paths["clean"])
    words, _ = transcribe(paths["clean"], os.path.join(paths["work"], "transcript_clean"))
    kept = sum(b - a for a, b in cuts)
    print(f"Cut {len(cuts)} ranges ({kept:.2f}s of {duration:.2f}s) -> work/clean.mp4 ({clean_dur:.2f}s, {len(words)} words). "
          f"Read work/transcript_clean.md next.")


if __name__ == "__main__":
    main()
