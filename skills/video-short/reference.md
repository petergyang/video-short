# Video Short reference

Set `S` to this skill's `scripts` folder and `P` to the project folder. Run every Python script through `$S/py`, which creates a venv at `~/.cache/video-short/venv` with numpy. HyperFrames runs through `npx`, pinned to version 0.8.169; `setup.sh` downloads its headless Chrome and the Parakeet speech model, about 1 GB together.

```bash
S=/path/to/video-short/scripts
P=~/Videos/my-short
mkdir -p "$P/broll"
```

## Commands

```bash
# First use: check tools, install numpy, fetch HyperFrames with its Chrome and Parakeet
$S/setup.sh

# 1. Cut
$S/py $S/transcribe.py "$P/raw.mp4" "$P/work/transcript_raw"   # -> .md to read, .json with word times
$S/py $S/cut.py "$P" --look                                     # gridded stills of the kept footage for Framing -> work/look/
$S/py $S/cut.py "$P" --look --grade "eq=contrast=1.06:saturation=1.1"
$S/py $S/cut.py "$P"                                            # -> work/clean.mp4 and transcript_clean

# B-roll: a web page at phone width, as a tall 1080-wide PNG for a page: scene, or to crop into a receipt
$S/py $S/capture.py "https://example.com/pricing" "$P/broll/pricing.png"

# 2. Optional generation (needs GEMINI_API_KEY with billing enabled)
$S/py $S/generate.py image "$P/broll/castle.jpg" --prompt "..."   # a first frame for a video clip, never B-roll on its own
$S/py $S/generate.py video "$P/broll/castle.mp4" --prompt "slow push through the gate" --image "$P/broll/castle.jpg" --seconds 6
$S/py $S/generate.py music "$P/music.mp3" --prompt "warm lo-fi, Rhodes piano, soft brushed drums" --seconds 45

# 3. Draft and review: run review.py in the background and wait for it to print the notes
$S/py $S/render.py "$P" --draft
$S/py $S/review.py "$P"            # later rounds: --no-open, the open page reloads itself

# 4. Final
$S/py $S/render.py "$P"
$S/py $S/qa.py "$P"
```

`render.py` builds the HyperFrames project in `hf/`, renders it, adds the audio mix, and saves the next version in `renders/`, plus a 720p copy under 10 MB or so in `renders/share/` for phones, chat, and email. A draft keeps one earlier draft beside it for comparison. A final render replaces every earlier version, and later drafts never remove it. `edit.md` holds only the current edit, so an older cut comes back only if you restore that edit. A draft takes as long as a final; `--draft` only lowers encoding quality. `review.py` reviews the newest render unless you pass a video, saves notes to `work/feedback.md` with a still of each commented frame in `work/review-frames/`, and uses port 8791 or any free port. `render.py` and `cut.py` accept `--style FILE`; `qa.py` checks the newest render unless you pass a video.

Generation: images come back as 9:16 JPEGs to start a video clip; video clips come from Gemini Omni Flash at 720p, can start from an image, and `--seconds` asks for a length in the prompt, since the model has no duration setting; music under 30 seconds uses the clip model, longer uses the full-song model. Free-tier keys get no generation requests, so the key needs billing enabled. The key comes from `GEMINI_API_KEY` or a `GEMINI_API_KEY=...` line in `~/.config/video-short/.env`, so it never goes in chat. `--model` overrides a default when Google renames a model; current IDs are at https://ai.google.dev/gemini-api/docs/models.

## edit.md

Settings come first, then sections. Times are seconds. Cuts use raw-recording time; scenes use the cut (clean) timeline.

```markdown
# edit.md: gemini-short

Source: raw.mp4
Grade: eq=contrast=1.06:saturation=1.1:brightness=0.01
Framing: 0.47, 0.36
Music: music.mp3
Music level: -18
Music lift: 14.0-16.0
Sound effects: off

## Cuts
- 3.40-11.20  (lead-in silence removed)
- 12.05-42.80  (dropped the false start at 11.2)

## Scenes
| id  | start | end   | layout | visual                                       | note                    |
|-----|-------|-------|--------|----------------------------------------------|-------------------------|
| s01 | 0.00  | 3.80  | a-roll |                                              | hook                    |
| s02 | 3.80  | 5.30  | split  | broll/3d_castle.mp4 @0.5                     | on "3D models"          |
| s03 | 5.30  | 6.80  | b-roll | broll/benchmarks.mp4 @2-3 zoom .5,.5,.9>.3,.35,.45 hold | push in on the top score |
| s04 | 6.80  | 11.00 | split  | receipt: broll/post.png mark .08,.66,.86,.07 | the launch post she cites |
| s05 | 11.00 | 13.90 | split  | card: Gemini did the edit ; Image            | one row per spoken item |
| s06 | 13.90 | 16.00 | split  | card: Gemini did the edit ; Image ; Video    | only the new row animates |
| s07 | 16.00 | 19.50 | split  | number: 3 ; prompts from raw cut to Short    | counts up               |
| s08 | 19.50 | 23.00 | b-roll | graphic: broll/flow.html                     | your own motion graphic |

## Caption fixes
- Anti Gravity -> Antigravity

## Emphasis
- Gemini 4
```

- `Source`: the raw recording, relative to the project or absolute.
- `Grade`: any ffmpeg video filter chain, or `none`. Leave it out to use the style's `grade`. Useful pieces: `eq=contrast=:saturation=:brightness=:gamma=`, `colortemperature=temperature=5600`, `lut3d=file.cube`.
- `Framing`: face center as fractions of the source frame width and height.
- `Sound effects`: `off` (default) or `subtle`: quiet taps when a card, row, or number enters and a soft whoosh on B-roll cuts, synthesized locally.
- `Music lift`: cut-timeline ranges where the music rises 9 dB for a beat, such as when the speaker mentions the music. Comma-separate several ranges.
- `Music`: an audio file or `none`. `Music level`: dB relative to the voice (default -18); the bed also dips about 5 dB while the speaker talks and comes back up in pauses. The mix normalizes to -14 LUFS with a -1.5 dBTP soft ceiling.
- Scenes must be contiguous: each start equals the previous end, the first starts at 0, and the last ends at the clean video's end.
- `visual` for a clip: `path [@start[-end]] [fit|fill] [zoom X,Y,W[>X,Y,W]] [hold]`, a video or gif. `@start-end` plays that range of the clip. `fill` crops to cover the panel; `fit` shows the whole clip over a blurred copy. The default is `fill` only when the shapes nearly match, so text at the sides survives. A clip shorter than its scene loops, unless `hold` freezes its last frame; give a tiny range such as `@4.30-4.35 hold` to hold one frame. `zoom` shows a window of the clip and eases it from the first region to the second over the scene: X and Y are the window center and W its width, all as fractions of the clip, so `zoom .5,.5,.9>.3,.35,.4` pushes from almost the whole frame into the upper left. Pick a window that holds one complete card or field, and add `fit` when a zoom on a landscape clip would crop text at the panel's sides.
- `visual` for a page: `page: path [TOP>TOP]`, a PNG from `capture.py`. It fills the panel at full width and drifts down from the first top to the second, in pixels of the 1080-wide capture (default: 160 pixels down from the top). Read the capture first and pick one complete section.
- `visual` for a card: `card: Title ; row ; row`. Separate parts with `;`, because `|` ends a table cell. Rows slide in one by one. When the next scene repeats the same title and rows, only its new rows animate, so a list builds across scenes.
- `visual` for a number: `number: 3x ; label` or `number: 3x ; label ; over broll/clip.mp4 @2`. The number counts up from zero, keeping any prefix or suffix such as `$`, `%`, or `x`, and the label fades in below. With `over`, it sits on that clip, darkened.
- `visual` for a graphic: `graphic: path.html`, a HyperFrames sub-composition you write. See below.
- `visual` for a receipt: `receipt: path [mark X,Y,W,H]...`, a screenshot (png, jpg, webp) of a tweet, article, or page the speaker cites. It sits as a card centered in the panel, up to 960px wide, never cropped, with a slow push. Each `mark` sweeps a highlighter across one line, in turn: the line's left, top, width, and height as fractions of the screenshot. Marks show on light backgrounds, such as most tweets and articles. Crop the screenshot to whole lines that matter; the build warns when a card would show under 760px wide.
- `split` and `b-roll` need a visual. `a-roll` and `punch` leave it empty.
- `## Caption fixes` rows replace words in captions only, matching whole words without case.
- `## Emphasis` rows are phrases that get a solid box behind them in the caption (the style's `caption.emphasis` color), matching whole words without case. A style without `emphasis` ignores them.

The parser stops with the line number on any malformed row.

## Graphics

A `graphic:` file is a self-contained HyperFrames sub-composition: inline CSS and SVG, no external files. Size it to the panel it fills, 1080x880 for `split` or 1080x1920 for `b-roll`, and give it the scene's duration. Register its GSAP timeline under its composition id. The style's fonts are loaded as `Ftitle`, `Fbody`, `Fnum`, and `Fcap`, and its colors are in `style.json`. The build copies it into the project.

```html
<template id="flow-template">
  <div data-composition-id="flow" data-width="1080" data-height="1920" data-duration="3.5">
    <style>
      .g { position: absolute; inset: 0; background: #0B0B0D; display: flex; flex-direction: column;
           align-items: center; justify-content: center; gap: 48px; font: 72px Ftitle, sans-serif; color: #fff; }
      .box { padding: 40px 60px; border-radius: 28px; background: #17171B; }
      .arrow { color: #3B82F6; font-size: 96px; }
    </style>
    <div class="g"><div class="box b1">Raw recording</div><div class="arrow">↓</div><div class="box b2">Finished Short</div></div>
    <script>
      const tl = gsap.timeline({ paused: true });
      tl.from(".b1", { autoAlpha: 0, y: -40, duration: .4 }, .1)
        .from(".arrow", { autoAlpha: 0, scale: .6, duration: .3 }, .5)
        .from(".b2", { autoAlpha: 0, y: 40, duration: .4 }, .8);
      window.__timelines["flow"] = tl;
    </script>
  </div>
</template>
```

Keep motion purposeful: one entrance per element, eased, then hold. Check it in the draft before the final render.

Before writing a graphic from scratch, check whether one of these [HyperFrames catalog](https://hyperframes.heygen.com/catalog) items fits. Install it in a scratch folder with `npx hyperframes@0.8.169 add <name> --json`, read it, then adapt it into a `graphic:` file: size it to the panel, inline what it needs, use the style's fonts and colors, and enlarge any text a phone can't read. Show real text and numbers. A chat or app mockup illustrates an idea and never stands in as proof of what a product did.

- **Prompts and chats:** `typed-prompt`, `claude-exchange`, `chatgpt-exchange`, `message-thread-reveal`, `notes-reveal`.
- **Pointing at something:** `cursor-annotate`, `cursor-text-select`.
- **Hooks and proof:** `apple-money-count`, `notification-cascade`, `x-post`, `reddit-post`.
- **Explaining:** `whiteboard-ink`, `swipe-rail`, `modal-morph`, `gloss-sweep`, `app-showcase`.
- **Closing:** `cta-close`, `instagram-follow`, `yt-lower-third`.

## Layout geometry

- `a-roll`: the camera covers 1080x1920 with the face centered horizontally and 36% down.
- `punch`: the same, zoomed by `punch_zoom` (default 1.1).
- `split`: the visual fills y 0 to 880. The speaker fills y 880 to 1920 at 1.2x, face 42% down the panel.
- Captions sit at y 1400 on speaker shots, on the 880 seam for splits, and at y 1440 on B-roll, above the like and comment buttons the Shorts and Reels apps draw near the bottom. Override with `caption_y` in the style, and keep any caption above about y 1480.

## Getting B-roll

```bash
# YouTube, X, and most video sites (the player client flag avoids YouTube's throttled formats)
yt-dlp --extractor-args "youtube:player_client=tv,mweb" -f "bv*[height<=1080]+ba/b" -o "$P/broll/raw_%(id)s.%(ext)s" URL

# Media embedded in a blog post: list candidate files, then download the one you need
curl -sL -A "Mozilla/5.0" "PAGE_URL" | grep -oE 'https?://[^"'"'"' ]+\.(mp4|webm|gif|m3u8)' | sort -u
curl -sL -o "$P/broll/clip.gif" "MEDIA_URL"

# Trim to the useful seconds and convert anything (gif, webm, mov) to H.264
ffmpeg -ss 12.0 -t 4 -i in.webm -an -c:v libx264 -crf 18 -pix_fmt yuv420p -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" "$P/broll/clip.mp4"

# Crop a capture or screenshot to the lines a receipt shows (w:h:x:y in source pixels)
ffmpeg -i "$P/broll/post.png" -vf "crop=1080:300:0:820" "$P/broll/quote.png"

# Crop a clip to the part that reads on a phone
ffmpeg -i in.mp4 -an -vf "crop=1200:900:300:120" -c:v libx264 -crf 18 "$P/broll/clip_crop.mp4"
```

Look at a clip before using it: `ffmpeg -ss 2 -i clip.mp4 -frames:v 1 /tmp/look.jpg`, then read the image.

## style.json

`sound_effects` is the default for the `Sound effects:` line. Every key is optional; missing keys fall back to `styles/default.json`. `pad` is the band's horizontal and vertical padding; `max_words` and `max_chars` cap each caption, which also splits at punctuation and pauses; `border` with zero alpha draws no outline. Font paths are relative to the style file; weights pick a weight from a variable font. The default is Inter for everything. Colors are `#RRGGBB` or `#RRGGBBAA`. `projects_dir` is where new projects go when the user doesn't say. `grade` is the default ffmpeg grade, used when `edit.md` has no `Grade:` line.

```json
{
  "projects_dir": "~/Videos/shorts",
  "grade": "colortemperature=temperature=6200,eq=contrast=1.04:saturation=1.05",
  "punch_zoom": 1.1,
  "caption_y": {"a-roll": 1400, "punch": 1400, "split": 880, "b-roll": 1440},
  "caption": {"font": "fonts/MyFont.woff2", "weight": 500, "size": 64, "color": "#FFFFFF", "box": "#000000E0",
              "border": "#FFFFFF30", "radius": 18, "pad": [36, 20], "uppercase": true,
              "max_words": 3, "max_chars": 18, "emphasis": "#F59E0B"},
  "card": {"background": "#0B0B0D", "panel": "#17171B", "border": "#FFFFFF24", "text": "#FFFFFF",
           "accent": "#3B82F6", "title_font": "fonts/Title.woff2", "title_weight": 800, "body_font": "fonts/Body.woff2",
           "body_weight": 600, "number_font": "fonts/Mono.woff2", "number_weight": 800},
  "sound_effects": "off"
}
```
