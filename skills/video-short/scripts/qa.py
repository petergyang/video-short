"""Measure a rendered Short and export frames for the agent to inspect.
usage: qa.py PROJECT [VIDEO]   (VIDEO defaults to the newest renders/*.mp4)
writes work/qa/report.md, contact.jpg (2 frames/second), opening.jpg (first 3 seconds),
and cuts/ (10 frames around every scene change)."""
import glob, json, os, re, subprocess, sys

from common import FPS, H, W, parse_edit, project_paths, run


def loudness(video):
    err = subprocess.run(["ffmpeg", "-i", video, "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    i = re.findall(r"I:\s+(-?[\d.]+)\s+LUFS", err)
    tp = re.findall(r"Peak:\s+(-?[\d.]+)\s+dBFS", err)
    return (float(i[-1]) if i else None), (float(tp[-1]) if tp else None)


def streams(video):
    info = json.loads(run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                           "stream=codec_type,width,height,r_frame_rate,nb_read_frames,duration", "-of", "json", video]).stdout)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    return v, a


def black_frames(video):
    err = subprocess.run(["ffmpeg", "-i", video, "-vf", "blackdetect=d=0.03:pix_th=0.08", "-an", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    return re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    paths = project_paths(sys.argv[1])
    video = sys.argv[2] if len(sys.argv) == 3 else max(glob.glob(os.path.join(paths["renders"], "*.mp4")), key=os.path.getmtime)
    qa = os.path.join(paths["work"], "qa")
    os.makedirs(os.path.join(qa, "cuts"), exist_ok=True)
    for f in glob.glob(os.path.join(qa, "cuts", "*.jpg")):
        os.remove(f)

    v, a = streams(video)
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    vdur, adur = float(v["duration"]), float(a["duration"]) if a else 0.0
    lufs, peak = loudness(video)
    blacks = black_frames(video)

    checks = [
        ("Size is 1080x1920", v["width"] == W and v["height"] == H, f"{v['width']}x{v['height']}"),
        ("Frame rate is 30", num / den == FPS, f"{num / den:g} fps"),
        ("Has audio", a is not None, "yes" if a else "no audio stream"),
        ("Audio and video lengths match within 1 frame", abs(vdur - adur) <= 1 / FPS, f"video {vdur:.3f}s, audio {adur:.3f}s"),
        ("Loudness is -15 to -13 LUFS", lufs is not None and -15 <= lufs <= -13, f"{lufs} LUFS"),
        ("Peak is at or below -1.0 dBFS", peak is not None and peak <= -1.0, f"{peak} dBFS"),
        ("No black gaps", not blacks, ", ".join(f"{s}-{e}s" for s, e in blacks) or "none"),
    ]

    run(["ffmpeg", "-v", "error", "-y", "-i", video, "-vf",
         f"fps=2,scale=216:384,tile=8x{max(1, int(vdur * 2 / 8) + 1)}", "-frames:v", "1", os.path.join(qa, "contact.jpg")])
    run(["ffmpeg", "-v", "error", "-y", "-t", "3", "-i", video, "-vf", "fps=6,scale=270:480,tile=6x3", "-frames:v", "1",
         os.path.join(qa, "opening.jpg")])
    edit = parse_edit(paths["edit"]) if os.path.isfile(paths["edit"]) else {"scenes": []}
    for sc in edit["scenes"][1:]:
        t = max(0.0, sc["start"] - 5 / FPS)
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", video, "-vf", "scale=162:288,tile=10x1",
             "-frames:v", "1", os.path.join(qa, "cuts", f"{sc['id']}_{sc['start']:.2f}.jpg")])

    lines = [f"# QA: {os.path.basename(video)}", ""]
    lines += [f"- [{'x' if ok else ' '}] {name}: {detail}" for name, ok, detail in checks]
    lines += ["", "Look at contact.jpg, opening.jpg, and cuts/*.jpg (5 frames before and after each scene change)."]
    open(os.path.join(qa, "report.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nFiles in {qa}")
    sys.exit(0 if all(ok for _, ok, _ in checks) else 1)


if __name__ == "__main__":
    main()
