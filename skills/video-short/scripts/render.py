"""Render edit.md into the finished Short: build the HyperFrames project, render it, and add the audio mix.
usage: render.py PROJECT [--style STYLE_JSON] [--draft]
--draft renders fast at lower quality for review.
Output: renders/<project>-vN.mp4, never overwriting an earlier version, plus a 720p copy in renders/share/."""
import argparse, os, re, shutil, subprocess, tempfile

from build import build
from common import HF, NPX, die, project_paths, run


def hyperframes(*args):
    p = subprocess.run([NPX, "-y", HF, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        die(f"hyperframes {args[0]} failed:\n{(p.stdout + p.stderr)[-1500:]}")
    return p.stdout


def next_version(renders, slug):
    os.makedirs(renders, exist_ok=True)
    taken = [int(m.group(1)) for f in os.listdir(renders) if (m := re.fullmatch(rf"{re.escape(slug)}-v(\d+)\.mp4", f))]
    return os.path.join(renders, f"{slug}-v{max(taken, default=0) + 1}.mp4")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--style")
    ap.add_argument("--draft", action="store_true")
    a = ap.parse_args()
    if not shutil.which("npx"):
        die("HyperFrames needs Node.js 22 or newer: https://nodejs.org")
    hf, mix, dur = build(a.project, a.style)
    hyperframes("lint", hf)
    paths = project_paths(a.project)

    with tempfile.TemporaryDirectory() as tmp:
        silent = os.path.join(tmp, "video.mp4")
        hyperframes("render", hf, "-o", silent, "--quality", "draft" if a.draft else "delivery")
        out = next_version(paths["renders"], os.path.basename(paths["root"]))
        run(["ffmpeg", "-v", "error", "-y", "-i", silent, "-i", mix, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "256k", "-frames:v", str(round(dur * 30)), "-t", f"{dur:.6f}", "-movflags", "+faststart", out])
    # A small copy for phones, chat, and email, which the full-quality master is too big for.
    share = os.path.join(paths["renders"], "share", os.path.basename(out))
    os.makedirs(os.path.dirname(share), exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y", "-i", out, "-vf", "scale=720:1280", "-c:v", "libx264", "-crf", "26", "-preset", "medium",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", share])
    print(f"Rendered {out} ({dur:.2f}s), with a 720p copy to share at {share}. Run qa.py next.")


if __name__ == "__main__":
    main()
