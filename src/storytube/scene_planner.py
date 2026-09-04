import json

from google import genai
from google.genai import types

from . import config

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "character_sheet": {
            "type": "string",
            "description": (
                "One reusable description of each recurring character's appearance "
                "(face, hair, clothing, colors) so every scene image stays visually consistent."
            ),
        },
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "narration": {
                        "type": "string",
                        "description": "The exact line(s) to be spoken as voice-over for this scene, in the target narration language.",
                    },
                    "image_prompt": {
                        "type": "string",
                        "description": "English visual description of this scene's setting and action, for an image generation model.",
                    },
                    "include_character_sheet": {
                        "type": "boolean",
                        "description": "True if this scene's image should show the recurring human character(s). False for symbolic/figure-free scenes (e.g. calligraphy, mosque exterior, desert with no person) where no human figure should be generated at all.",
                    },
                },
                "required": ["id", "narration", "image_prompt", "include_character_sheet"],
            },
        },
    },
    "required": ["character_sheet", "scenes"],
}


def _load_prompt_template(category: str) -> str:
    template_path = config.PROMPTS_DIR / f"scene_planning_{category}.txt"
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
    return template_path.read_text(encoding="utf-8")


def plan_scenes(story_text: str, style: str, language: str = "English", category: str = "general") -> dict:
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it to your .env file.")

    client = genai.Client(api_key=config.GEMINI_API_KEY)

    template = _load_prompt_template(category)
    prompt = (
        template.replace("{{STYLE}}", style)
        .replace("{{LANGUAGE}}", language)
        .replace("{{STORY_TEXT}}", story_text)
    )

    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
        ),
    )

    return json.loads(response.text)

