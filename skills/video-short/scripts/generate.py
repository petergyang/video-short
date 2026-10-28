"""Optional: generate an image (Nano Banana), a video clip (Gemini Omni Flash), or a music bed (Lyria) with the Gemini API.
Needs GEMINI_API_KEY with billing enabled, from the environment or ~/.config/video-short/.env (a line GEMINI_API_KEY=...).
usage: generate.py image OUT.jpg --prompt "..." [--aspect 9:16]
       generate.py video OUT.mp4 --prompt "..." [--image START.jpg] [--seconds 6] [--aspect 9:16]
       generate.py music OUT.mp3 --prompt "warm lo-fi, Rhodes, soft drums" [--seconds 45]
--model overrides the default model. Model IDs: https://ai.google.dev/gemini-api/docs/models"""
import argparse, base64, json, mimetypes, os, re, sys, time, urllib.error, urllib.request

API = "https://generativelanguage.googleapis.com/v1beta"
MODELS = {"image": "gemini-nano-banana-2.1", "video": "gemini-omni-1.1-flash", "music": "lyria-3-clip-preview"}
LONG_MUSIC = "lyria-3.5"   # the clip model always makes 30 seconds


SETTINGS = os.path.expanduser("~/.config/video-short/.env")


def settings_key():
    """The key from the settings file, so it never has to be pasted into chat."""
    if os.path.isfile(SETTINGS):
        for line in open(SETTINGS, encoding="utf-8"):
            k, _, v = line.strip().partition("=")
            if k.strip() in ("GEMINI_API_KEY", "GOOGLE_API_KEY") and v.strip():
                return v.strip().strip("'\"")
    return None


def call(url, key, body=None, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"Gemini API error {e.code}: {e.read().decode()[:600]}")


def interaction_output(res, kind):
    """The first base64 output of this kind ('image' or 'audio') from an Interactions response."""
    for step in res.get("steps", []):
        if step.get("type") == "model_output":
            for item in step.get("content", []):
                if item.get("type") == kind and item.get("data"):
                    return base64.b64decode(item["data"])
    sys.exit(f"No {kind} came back. Response: {json.dumps(res)[:600]}")


def image(a, key):
    res = call(f"{API}/interactions", key, {"model": a.model, "input": a.prompt,
                                            "response_format": {"type": "image", "mime_type": "image/jpeg", "aspect_ratio": a.aspect}})
    open(a.out, "wb").write(interaction_output(res, "image"))


def file_bytes(uri, key, name=None):
    """Wait for a Files API upload to finish processing, then download it."""
    while name:
        f = call(f"{API}/{name}", key)
        if f.get("state") == "ACTIVE":
            break
        if f.get("state") == "FAILED":
            sys.exit(f"Video processing failed: {json.dumps(f)[:400]}")
        time.sleep(5)
    req = urllib.request.Request(uri, headers={"x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def video(a, key):
    if a.model.startswith("veo"):
        return veo(a, key)
    prompt = a.prompt + (f" About {round(a.seconds)} seconds long." if a.seconds else "")
    inp = [{"type": "text", "text": prompt}]
    if a.image:   # the image becomes the first frame
        inp.insert(0, {"type": "image", "data": base64.b64encode(open(a.image, "rb").read()).decode(),
                       "mime_type": mimetypes.guess_type(a.image)[0] or "image/jpeg"})
    res = call(f"{API}/interactions", key, {"model": a.model, "input": inp,
               "response_format": {"type": "video", "aspect_ratio": a.aspect, "delivery": "uri"}}, timeout=900)
    for step in res.get("steps", []):
        for item in step.get("content", []) if step.get("type") == "model_output" else []:
            if item.get("type") == "video":
                if item.get("data"):
                    return open(a.out, "wb").write(base64.b64decode(item["data"]))
                if item.get("uri"):
                    name = re.search(r"(files/[^/:?]+)", item["uri"])
                    url = f"{API}/{name.group(1)}:download?alt=media" if name else item["uri"]
                    return open(a.out, "wb").write(file_bytes(url, key, name.group(1) if name else None))
    sys.exit(f"No video came back. Response: {json.dumps(res)[:600]}")


def veo(a, key):
    """Older Veo models, for keys that still have them (--model veo-...)."""
    inst = {"prompt": a.prompt}
    if a.image:
        inst["image"] = {"bytesBase64Encoded": base64.b64encode(open(a.image, "rb").read()).decode(),
                         "mimeType": mimetypes.guess_type(a.image)[0] or "image/jpeg"}
    seconds = min((4, 6, 8), key=lambda s: abs(s - (a.seconds or 6)))
    op = call(f"{API}/models/{a.model}:predictLongRunning", key,
              {"instances": [inst], "parameters": {"aspectRatio": a.aspect, "durationSeconds": seconds}})
    while not op.get("done"):
        time.sleep(10)
        op = call(f"{API}/{op['name']}", key)
    if "error" in op:
        sys.exit(f"Veo failed: {op['error']}")
    uri = op["response"]["generateVideoResponse"]["generatedSamples"][0]["video"]["uri"]
    req = urllib.request.Request(uri, headers={"x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=300) as r:
        open(a.out, "wb").write(r.read())


def music(a, key):
    seconds = a.seconds or 30
    model = a.model if a.model != MODELS["music"] or seconds <= 30 else LONG_MUSIC
    prompt = f"{a.prompt}. Instrumental only, no vocals." + (f" About {round(seconds)} seconds long." if model == LONG_MUSIC else "")
    open(a.out, "wb").write(interaction_output(call(f"{API}/interactions", key, {"model": model, "input": prompt}), "audio"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=MODELS)
    ap.add_argument("out")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--image")
    ap.add_argument("--seconds", type=float)
    ap.add_argument("--aspect", default="9:16")
    ap.add_argument("--model")
    a = ap.parse_args()
    a.model = a.model or MODELS[a.kind]
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or settings_key()
    if not key:
        sys.exit(f"No Gemini key. Put GEMINI_API_KEY=... in {SETTINGS} (key at https://aistudio.google.com/apikey).")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    {"image": image, "video": video, "music": music}[a.kind](a, key)
    print(f"{a.kind} -> {a.out}")


if __name__ == "__main__":
    main()
