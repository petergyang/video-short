"""Capture a web page at phone width as a tall 1080-wide PNG, for a `page:` scene that drifts down it.
A phone-width page reflows its text to fit, so no line runs off the side of the frame.
usage: capture.py URL OUT_PNG [--width 540] [--height 6000]"""
import argparse, os, subprocess

from common import HF, NPX, die


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("out")
    ap.add_argument("--width", type=int, default=540, help="CSS width; the PNG is twice as wide")
    ap.add_argument("--height", type=int, default=6000, help="PNG height in pixels")
    a = ap.parse_args()
    chrome = subprocess.run([NPX, "-y", HF, "browser", "path"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip().splitlines()
    if not chrome or not os.path.isfile(chrome[-1]):
        die("HyperFrames has no Chrome yet: run setup.sh")
    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subprocess.run([chrome[-1], "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                    f"--window-size={a.width},{a.height // 2}", "--virtual-time-budget=8000", f"--screenshot={out}", a.url],
                   capture_output=True)
    if not os.path.isfile(out):
        die(f"Chrome could not capture {a.url}")
    print(f"Captured {a.url} -> {out} ({a.width * 2}px wide). Read it, then pick a TOP>TOP drift for a page: scene.")


if __name__ == "__main__":
    main()
