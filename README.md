# Storytube

Turn a written story into a narrated, illustrated YouTube video — or a few lines of poetry into
a vertical reel — locally, on your own machine.

You give it a story. It plans the scenes with Gemini, draws every scene, narrates it in the
language and voice you choose, adds music and ambience, stitches everything together with
motion and crossfades, burns in subtitles, and gives you a finished MP4.

Give it a couplet instead and you get a 9:16 reel with the poem set on the image, background
music, and a caption with hashtags ready to paste into Instagram.

Everything except scene planning can run **entirely on your own hardware, for free**, with
models licensed for commercial use — so the videos are safe to monetise.

---

## Contents

- [What it does](#what-it-does)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Using the web app](#using-the-web-app)
- [Poetry reels](#poetry-reels)
- [Publishing to Instagram and YouTube](#publishing-to-instagram-and-youtube)
- [Using the command line](#using-the-command-line)
- [Providers you can choose](#providers-you-can-choose)
- [How a video is built](#how-a-video-is-built)
- [Project layout](#project-layout)
- [Troubleshooting](#troubleshooting)
- [Licensing and monetisation](#licensing-and-monetisation)

---

## What it does

| Stage | What happens |
|---|---|
| Scene planning | Gemini turns your story into numbered scenes, each with a narration line and an image prompt, plus a reusable character description so the character looks the same throughout |
| Images | One image per scene, drawn at your video's exact resolution |
| Voice-over | Each scene's narration is spoken in your chosen language and voice |
| Motion | Ken Burns style zoom and pan, alternating direction per scene |
| Transitions | Crossfades between scenes, with a configurable pause after each one |
| Audio | Voice is loudness-normalised, with optional background music and wind ambience mixed underneath |
| Subtitles | Word timings become an SRT file, burned into the final video |
| Output | A single `final_video.mp4`, plus all intermediate images, audio and clips |

---

## Requirements

- **macOS on Apple Silicon** (built and tested on an M4 Max). Local image and voice models use
  Apple's MLX and PyTorch MPS backends.
- **Python 3.14**
- **ffmpeg with libass** — the plain Homebrew `ffmpeg` formula cannot burn subtitles
- **A Gemini API key** — the free tier is enough for scene planning
- **Disk space** — about 35 GB if you use the local image and voice models

---

## Installation

### 1. ffmpeg

The regular `ffmpeg` formula is built without libass, so `subtitles=` filters fail. Install the
full build:

```bash
brew install ffmpeg-full
```

Storytube detects `ffmpeg-full` automatically and prefers it.

### 2. The project

```bash
git clone <your-repo-url> youtube-sub
cd youtube-sub

python3.14 -m venv .venv
source .venv/bin/activate
pip install -e .
```

> **If pip fails with an SSL certificate error** (common on macOS), add trusted hosts:
> ```bash
> pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org \
>     --trusted-host pythonhosted.org -e .
> ```

### 3. Local image generation (optional but recommended)

Free, unlimited, and commercially licensed:

```bash
pip install mflux
```

The first render downloads FLUX.1-schnell (~24 GB, roughly 40 minutes). You must accept the
licence once at https://huggingface.co/black-forest-labs/FLUX.1-schnell while signed in to the
same account as your `HF_TOKEN`.

### 4. Local Indian-language voices (optional)

IndicF5 **must live in its own virtual environment**. It needs `transformers<4.50` and
`numpy<=1.26.4`, which directly conflict with mflux. Keeping them apart is not optional:

```bash
python3.14 -m venv .venv-indicf5
.venv-indicf5/bin/pip install "git+https://github.com/ai4bharat/IndicF5.git" \
    "transformers<4.50" "numpy<=1.26.4" soundfile
```

Storytube runs it as a background worker via `scripts/indicf5_worker.py` and keeps the model
loaded between scenes. Accept the licence once at https://huggingface.co/ai4bharat/IndicF5.

---

## Configuration

Copy the example file and fill in what you need:

```bash
cp .env.example .env
```

Every value can also be edited in the web app under **Settings**, which writes back to `.env`
and applies immediately without a restart.

| Key | Needed when | Where to get it |
|---|---|---|
| `GEMINI_API_KEY` | Always | https://aistudio.google.com/apikey |
| `GEMINI_MODEL` | Optional | Defaults to `gemini-3.1-flash-lite` |
| `IMAGE_PROVIDER` | Always | `local`, `huggingface` or `pollinations` |
| `HF_TOKEN` | Local images, or Hugging Face provider | https://huggingface.co/settings/tokens |
| `POLLINATIONS_API_KEY` | Pollinations provider | https://enter.pollinations.ai/keys |
| `SARVAM_API_KEY` | Sarvam voices | https://indus.sarvam.ai |
| `ELEVENLABS_API_KEY` | ElevenLabs voices | https://elevenlabs.io/app/settings/api-keys |
| `IG_USER_ID` | Checking Instagram credentials | Meta Graph API Explorer |
| `IG_ACCESS_TOKEN` | Checking Instagram credentials | https://developers.facebook.com/docs/instagram-platform/content-publishing |
| `YOUTUBE_API_KEY` | Optional, public channel lookups | https://console.cloud.google.com/apis/credentials |
| `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` | Posting/analytics on YouTube | Google Cloud Console → Credentials → OAuth client ID → Desktop app |
| `YOUTUBE_REFRESH_TOKEN`, `YOUTUBE_CHANNEL_ID`, `YOUTUBE_CHANNEL_TITLE` | — | Written automatically by **Connect YouTube**, never typed in by hand |
| `OUTPUT_DIR` | Optional | Defaults to `output` |

For the Hugging Face token, create a **fine-grained** token with *"Make calls to Inference
Providers"* enabled — a default token returns 403.

The Instagram and YouTube keys enable in-app publishing and insights — see
[Publishing to Instagram and YouTube](#publishing-to-instagram-and-youtube) below.

---

## Using the web app

```bash
source .venv/bin/activate
storytube-web
```

Open http://127.0.0.1:8420

**Create Video** — write or load a story, pick category, language, visual style and voice.
Press **Listen** to hear any voice before committing to a full render. **Advanced** opens a
drawer with resolution, crossfade, pauses, music and caching options. **Generate video** first
shows a review dialog summarising every setting, with warnings for things that would waste a
render — a voice that cannot speak your language, a missing API key, music volume with no
track selected. Nothing starts until you confirm.

**Outputs** — every video with its description, runtime, scene count, thumbnails of each
generated scene, and download or delete actions. Filter by **Reels & Shorts**, **Landscape** or
**Square** to separate vertical from widescreen work. Click any thumbnail to view it full size.
Eligible reels (portrait or square, 3 minutes or under) show **Post** and **Shorts** buttons
directly on the card — no menu-hunting. **Music** re-renders an existing video with a different
background track, reusing the cached images and voice-over so it finishes in under a minute.

**Prompts** — edit the scene-planning template per category. Every save is version-archived so
you can roll back. You can also create new categories here.

**Settings** — all API keys and defaults, each with a link explaining where to obtain it.
Settings that do not apply to your current providers are marked *inactive* rather than hidden.

---

## Poetry reels

The **Poetry Reel** tab turns two or three lines into a vertical video with the words set on the
image. Unlike story videos the image does not move — the frame is still, with no fade at either
end, so the first frame (your feed thumbnail) and the last frame (the loop point on autoplay)
both show the actual artwork rather than black.

The form is deliberately short: the poem, the background, and the music. Everything else —
handle, shape, music volume, pacing, style prompt and image seed — lives under **Advanced** and
is remembered between reels.

**Background** offers two paths:

- **My own photo** — drag in any JPG, PNG, WEBP or HEIC. **Adjust crop** opens a frame in your
  reel's exact shape; drag the picture and zoom to choose what stays. A shaded band shows where
  the poem will sit so you can keep faces clear of the text. This takes about ten seconds.
- **Generate** — Gemini designs an image to match the poem's mood and FLUX draws it. This takes
  a few minutes.

Gemini also writes the caption and hashtags, saved alongside the video as `caption.txt`.

Urdu is set in Nastaliq and Hindi in Devanagari. Line breaks are preserved: the type shrinks to
fit rather than wrapping, because wrapping a verse destroys its metre. Characters no font can
draw, such as emoji, are dropped from the image and kept in the caption.

**Voice-over** is optional — flip to *Read the poem aloud* and pick a reader. Only readers that
can actually speak the poem's script are listed (Urdu-script text only offers Urdu readers, and
so on), because a mismatched voice returns silence rather than a bad accent. Reader is one of:

- **Free (edge-tts)** — ten voices across Urdu, Hindi, Bengali and English, no account needed
- **ElevenLabs** — pulls in whichever voices are in your own account; needs a paid plan
  (Starter or above) for a commercial licence, and Urdu specifically needs the `eleven_v3`
  model, chosen automatically — Multilingual v2 does not cover Urdu

**Delivery** shapes how the reader paces it: *Natural* reads the poem as one block; *Recitation*
(the default) and *Slow* read one line at a time with a real pause at each break and a slower,
lower-pitched voice — pace and silence are most of what makes a recitation sound like one,
rather than a newsreader. **Listen** always auditions the exact voice, delivery and script
combination you have selected.

From the command line:

```bash
storytube-poem \
  --text "दिल की बात कहूँ तो कैसे कहूँ\nये लफ़्ज़ भी अब साथ नहीं देते" \
  --language Hindi \
  --handle "@your.poetry" \
  --music-file assets/indian_sitar_calm.mp3
```

---

## Publishing to Instagram and YouTube

Both platforms are reached from the same places: a **Post** button on the poem/story result
card right after generation, and **Post** / **Shorts** buttons on eligible cards in Outputs
(portrait or square, 3 minutes or under — landscape videos and anything longer only get a
Download button, since neither platform's short-form format accepts them).

### Instagram

Add `IG_USER_ID` and `IG_ACCESS_TOKEN` in Settings, then **Test connection** confirms the token
and account resolve to a Business or Creator account (personal accounts cannot publish through
the API). Reels upload straight from your Mac using Meta's resumable upload — no public URL or
tunnel needed. Once posted, the same button becomes **Insights**: views, reach, likes, comments,
saves and shares.

Instagram's API has no delete endpoint, so publishing is final — a post can only be removed by
hand in the app. The app confirms before posting, and refuses to post the same video twice
unless you explicitly choose to.

### YouTube

Uploading a video and reading private analytics both require **OAuth 2.0** — a plain API key
can only read public data, and Google rejects it for either. One-time setup in
**Settings → YouTube**:

1. In [Google Cloud Console](https://console.cloud.google.com/apis/credentials), enable
   **YouTube Data API v3** and **YouTube Analytics API**, then create an OAuth client ID of
   type **Desktop app**.
2. Paste the Client ID and Client Secret into Settings and save.
3. Click **Connect YouTube** — it opens Google's consent screen in a new tab; sign in with the
   account that owns your channel and approve. A short-lived local server catches the redirect
   and stores a refresh token, so this is a one-time step.

Posting uploads the video, sets its title/description/privacy, and appends `#Shorts` to the
description if you have not already added it. It also sets a **custom thumbnail** — the poem's
lettered card image, or a story's first scene — instead of leaving YouTube to auto-pick a
random frame. Custom thumbnails need your channel to be
[phone-verified](https://www.youtube.com/verify); without that the post still succeeds and the
app tells you specifically that the thumbnail was skipped, rather than failing silently.

**Insights** shows both view/like/comment counts and channel-owned watch-time analytics
(minutes watched, average view duration), the latter only available once you are connected.

---

```bash
storytube stories/thirsty_dog.txt \
  --style "watercolor storybook illustration" \
  --language Hindi \
  --category islamic \
  --tts-provider indicf5 \
  --indicf5-voice mar_m \
  --music-file assets/indian_traditional.mp3 \
  --music-volume 0.15
```

Useful flags:

| Flag | Purpose |
|---|---|
| `--style` | Visual style applied to every scene |
| `--language` | Narration language |
| `--category` | Which prompt template to use |
| `--tts-provider` | `edge`, `indicf5` or `sarvam` |
| `--size` | Output resolution, default `1920x1080` |
| `--transition` | Crossfade length in seconds |
| `--scene-pause` | Silence after each scene |
| `--music-file`, `--music-volume` | Background music |
| `--ambience-volume` | Wind ambience level |
| `--force-replan` | Ignore the cached scene plan |
| `--force-images` | Redraw all images |
| `--force-voice` | Re-record all narration |
| `--no-intro`, `--no-outro` | Skip the opening or closing title card |
| `--intro-title`, `--intro-subtitle` | Text on the opening card |

Scene plans and images are cached, so re-running only redoes what changed.

---

## Providers you can choose

### Images

| Provider | Cost | Speed | Notes |
|---|---|---|---|
| **`local`** | Free, unlimited | ~30–60s per image | FLUX.1-schnell on your Mac. Apache 2.0. Recommended |
| `pollinations` | Small credit cost | ~10s | Good for fast style experiments |
| `huggingface` | Monthly credits | ~10s | Runs out quickly at high resolution |

### Voice

| Provider | Cost | Speed | Languages |
|---|---|---|---|
| `edge` | Free | Instant | Many, including Hindi and Urdu |
| **`indicf5`** | Free, unlimited | ~20–30s per scene | 11 Indian languages. Runs locally. **No Urdu** |
| `sarvam` | Paid API | ~2s | Hindi, Urdu, English with Indian voices |
| `elevenlabs` | Paid, from $6/mo (poetry reels only) | ~2–5s | Whatever voices are in your account. Needs `eleven_v3` for Urdu |

`edge` returns **no audio at all** if the voice locale does not match the narration language.
The app switches the voice automatically when you change language, and the review dialog blocks
the mismatch.

### Music

Thirteen royalty-free tracks ship in `assets/` — cinematic, ambient, Indian traditional and
piano. All are Pixabay Content Licence, free for commercial use with no attribution required.
You can also upload your own from the Advanced drawer.

---

## How a video is built

```
story text
   └─> Gemini  ──> scenes.json  (narration + image prompt + character sheet per scene)
        ├─> image model   ──> images/scene_NN.png
        ├─> TTS           ──> audio/scene_NN.mp3   (+ word timings)
        └─> ffmpeg
              ├─ Ken Burns motion per scene
              ├─ crossfade concat of clips and audio
              ├─ mix voice with music and ambience
              ├─ mux audio to video
              └─ burn captions ──> final_video.mp4
```

Each output folder contains `scenes.json`, `meta.json`, `captions.srt`, and the `images/`,
`audio/` and `clips/` used to build it, so you can inspect or reuse any stage.

---

## Project layout

```
src/storytube/
  cli.py              command line entry point
  pipeline.py         the generation pipeline, shared by CLI and web
  scene_planner.py    Gemini scene planning
  image_gen.py        provider dispatch for images
  image_gen_local.py  FLUX.1-schnell through MLX
  tts.py              edge-tts
  tts_indicf5.py      IndicF5 via its isolated worker
  tts_sarvam.py       Sarvam API
  tts_elevenlabs.py   ElevenLabs API
  poetry.py           poetry reel generation (typography, narration, video)
  instagram.py        Instagram Graph API: publish + insights
  youtube.py          YouTube OAuth connect, Shorts upload, thumbnail, analytics
  assemble.py         all ffmpeg work
  captions.py         SRT building
  config.py           live configuration, re-read on every access
  web/                FastAPI backend and the browser UI
scripts/
  indicf5_worker.py   runs inside .venv-indicf5
prompts/              scene planning templates per category
stories/              your source stories
assets/               music tracks and voice references
output/               generated videos
```

---

## Troubleshooting

**"No such filter: subtitles"**
Your ffmpeg lacks libass. Install `ffmpeg-full`.

**"No audio was received" from edge-tts**
The voice cannot speak your narration language — for example a Hindi story with
`en-US-AriaNeural`. Choose a voice whose locale matches.

**Video plays but has no sound**
Usually the `moov` atom being at the end of the file. Storytube writes with
`-movflags +faststart` to prevent this.

**"You are trying to access a gated repo"**
Open the model page on Hugging Face while signed in to the account matching your `HF_TOKEN`
and accept the licence. Needed once each for FLUX.1-schnell and IndicF5.

**IndicF5 fails after installing something new**
Check nothing upgraded `transformers` past 4.50 or `numpy` past 1.26.4 inside
`.venv-indicf5`. Those pins are required.

**Images look soft or blurry**
Make sure the image provider is generating at your video resolution. Storytube passes the video
size through automatically; a mismatch means frames get upscaled.

**Black bars appear in generated images**
The word "cinematic" in a style prompt makes image models draw letterbox bars. Remove it.

---

## Licensing and monetisation

The parts you generate with are chosen so the output is safe to monetise:

| Component | Licence |
|---|---|
| FLUX.1-schnell | Apache 2.0 |
| IndicF5 | MIT |
| edge-tts | Free Microsoft service |
| Music in `assets/` | Pixabay Content Licence |
| Real-ESRGAN, whisper.cpp (optional) | BSD-3 / MIT |

Deliberately avoided: FLUX.1-dev and FLUX.1 Kontext (non-commercial), XTTS-v2 and F5-TTS
(non-commercial weights), MusicGen (CC-BY-NC), and Wav2Lip (research only).

You are responsible for the stories themselves and for complying with each provider's terms.
