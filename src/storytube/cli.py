import argparse
from pathlib import Path

from .pipeline import PipelineOptions, run_pipeline
from .story_reader import read_story


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a narrated video from a story file.")
    parser.add_argument("story_file", type=Path, help="Path to a .txt file containing the story")
    parser.add_argument("--style", default="anime/manga style", help="Visual style for the images")
    parser.add_argument(
        "--voice",
        default="en-US-AriaNeural",
        help="edge-tts voice id, e.g. hi-IN-SwaraNeural or ur-PK-UzmaNeural",
    )
    parser.add_argument("--voice-rate", default="+0%", help="edge-tts speaking rate adjustment, e.g. -10%%")
    parser.add_argument("--voice-pitch", default="+0Hz", help="edge-tts pitch adjustment, e.g. -2Hz")
    parser.add_argument(
        "--tts-provider",
        default="edge",
        choices=["edge", "sarvam", "indicf5"],
        help="Voice-over engine: edge (free), sarvam (paid API), indicf5 (free, local, Indian languages)",
    )
    parser.add_argument(
        "--indicf5-voice",
        default="mar_m",
        help="IndicF5 reference voice key (mar_m, mar_f, mar_f_warm, pan_f) or path to your own .wav",
    )
    parser.add_argument("--no-intro", action="store_true", help="Skip the opening title card")
    parser.add_argument("--no-outro", action="store_true", help="Skip the closing card")
    parser.add_argument("--intro-title", default="", help="Title text; defaults to the story name")
    parser.add_argument("--intro-subtitle", default="", help="Small line under the intro title")
    parser.add_argument("--outro-title", default="Thank you for watching", help="Closing card title")
    parser.add_argument(
        "--outro-subtitle", default="Subscribe for more stories", help="Closing card subtitle"
    )
    parser.add_argument(
        "--sarvam-speaker",
        default="shubh",
        help="Sarvam speaker id, e.g. shubh, manan, aditya, rahul, dev",
    )
    parser.add_argument("--sarvam-pace", type=float, default=1.0, help="Sarvam speaking pace (0.5-2.0)")
    parser.add_argument(
        "--sarvam-temperature", type=float, default=0.6, help="Sarvam expressiveness (0.01-1.0)"
    )
    parser.add_argument("--language", default="English", help="Narration language, e.g. Hindi, Urdu")
    parser.add_argument(
        "--category",
        default="general",
        help="Content category; selects the prompt template file (prompts/scene_planning_<category>.txt)",
    )
    parser.add_argument("--size", default="1920x1080", help="Output video resolution")
    parser.add_argument(
        "--transition", type=float, default=0.6, help="Crossfade transition duration in seconds"
    )
    parser.add_argument(
        "--scene-pause",
        type=float,
        default=0.6,
        help="Silent pause added after each scene's narration before the next scene, in seconds",
    )
    parser.add_argument(
        "--ambience-volume",
        type=float,
        default=0.1,
        help="Background wind ambience volume (0 disables ambience)",
    )
    parser.add_argument(
        "--music-volume",
        type=float,
        default=0.0,
        help="Background instrumental music volume (0 disables music)",
    )
    parser.add_argument(
        "--music-style", default="arabic", choices=["arabic"], help="Background music style"
    )
    parser.add_argument(
        "--music-file",
        type=Path,
        default=None,
        help="Path to a real music file to loop under the narration (takes priority over --music-style)",
    )
    parser.add_argument(
        "--force-replan",
        action="store_true",
        help="Regenerate the scene plan even if scenes.json already exists",
    )
    parser.add_argument(
        "--force-images",
        action="store_true",
        help="Regenerate scene images even if they already exist",
    )
    parser.add_argument(
        "--force-voice",
        action="store_true",
        help="Regenerate the voice-over even if cached audio already exists",
    )
    args = parser.parse_args()

    story_text = read_story(args.story_file)
    story_name = args.story_file.stem

    options = PipelineOptions(
        style=args.style,
        language=args.language,
        category=args.category,
        tts_provider=args.tts_provider,
        voice=args.voice,
        voice_rate=args.voice_rate,
        voice_pitch=args.voice_pitch,
        sarvam_speaker=args.sarvam_speaker,
        indicf5_voice=args.indicf5_voice,
        intro_enabled=not args.no_intro,
        intro_title=args.intro_title,
        intro_subtitle=args.intro_subtitle,
        outro_enabled=not args.no_outro,
        outro_title=args.outro_title,
        outro_subtitle=args.outro_subtitle,
        sarvam_pace=args.sarvam_pace,
        sarvam_temperature=args.sarvam_temperature,
        size=args.size,
        transition=args.transition,
        scene_pause=args.scene_pause,
        ambience_volume=args.ambience_volume,
        music_volume=args.music_volume,
        music_style=args.music_style,
        music_file=args.music_file,
        force_replan=args.force_replan,
        force_images=args.force_images,
        force_voice=args.force_voice,
    )

    def on_progress(event: dict) -> None:
        print(event["message"])

    run_pipeline(story_text, story_name, options, on_progress=on_progress)


if __name__ == "__main__":
    main()

