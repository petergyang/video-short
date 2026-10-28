"""Open the draft render for review on the shared review page (review_page.py): a player with a scene-band
timeline, where the user comments on any frame and clicks Send. Send saves work/feedback.md and this script prints it and exits.
usage: review.py PROJECT [VIDEO] [--no-open] [--port 8791] [--timeout 7200]
VIDEO defaults to the newest renders/*.mp4. Pass --no-open after the first round: the open page reloads itself
when the next draft is ready."""
import argparse, glob, json, os, sys

from common import parse_edit, probe, project_paths, validate_scenes
from review_page import serve, words_between, write_page


def describe(vis):
    if not vis:
        return "camera"
    if vis["type"] == "card":
        return "card: " + " / ".join([vis["title"], *vis["rows"]])
    if vis["type"] == "number":
        return f"number: {vis['value']}"
    return f"{vis['type']}: {vis['src']}"


def build(paths, video, page):
    edit = parse_edit(paths["edit"])
    words = json.load(open(os.path.join(paths["work"], "transcript_clean.json"), encoding="utf-8"))
    scenes = [{"id": sc["id"], "start": sc["start"], "end": sc["end"], "layout": sc["layout"], "visual": describe(sc["visual"]),
               "spoken": words_between(words, sc["start"], sc["end"])}
              for sc in validate_scenes(edit, paths["root"], probe(paths["clean"])[2])]
    write_page(paths["root"], page, video, scenes)
    return scenes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("video", nargs="?")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--timeout", type=int, default=7200)
    a = ap.parse_args()
    paths = project_paths(a.project)
    renders = glob.glob(os.path.join(paths["renders"], "*.mp4"))
    if not a.video and not renders:
        sys.exit("No render to review. Run render.py --draft first.")
    video = os.path.abspath(a.video or max(renders, key=os.path.getmtime))
    page = os.path.join(paths["work"], "review", "index.html")
    scenes = build(paths, video, page)
    serve(paths["root"], page, os.path.join(paths["work"], "feedback.md"), scenes, video, a.port, not a.no_open, a.timeout)


if __name__ == "__main__":
    main()
