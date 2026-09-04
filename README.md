# Storytube

Turn a written story into a narrated, illustrated YouTube video — locally, on your own machine.

You give it a story. It plans the scenes with Gemini, draws every scene, narrates it in the
language and voice you choose, adds music and ambience, stitches everything together with
motion and crossfades, burns in subtitles, and gives you a finished MP4.

Everything except scene planning can run **entirely on your own hardware, for free**, with
models licensed for commercial use — so the videos are safe to monetise.

---

## Contents

- [What it does](#what-it-does)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Using the web app](#using-the-web-app)
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
| `OUTPUT_DIR` | Optional | Defaults to `output` |

For the Hugging Face token, create a **fine-grained** token with *"Make calls to Inference
Providers"* enabled — a default token returns 403.

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
generated scene, and download or delete actions. Click any thumbnail to view it full size.

**Prompts** — edit the scene-planning template per category. Every save is version-archived so
you can roll back. You can also create new categories here.

**Settings** — all API keys and defaults, each with a link explaining where to obtain it.

---

## Using the command line

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
