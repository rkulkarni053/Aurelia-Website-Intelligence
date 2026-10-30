"""Free local AI image generation for website redesign mockups.

Uses open-source Stable Diffusion weights via Diffusers on CPU.
No paid API. Slow on CPU; falls back to caller if generation fails.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from PIL import Image

# Small open-source SD checkpoint that can run on CPU with limited RAM.
DEFAULT_MODEL_ID = "segmind/tiny-sd"
DEFAULT_STEPS = 12
DEFAULT_GUIDANCE = 6.0
DEFAULT_SIZE = 512


def diffusion_available() -> dict[str, Any]:
    try:
        import torch  # noqa: F401
        import diffusers  # noqa: F401

        return {
            "ok": True,
            "engine": "diffusers_cpu",
            "default_model": DEFAULT_MODEL_ID,
        }
    except Exception as exc:
        return {"ok": False, "engine": "diffusers_cpu", "error": str(exc)}


@lru_cache(maxsize=1)
def _load_pipeline(model_id: str):
    import torch
    from diffusers import StableDiffusionPipeline

    pipe = StableDiffusionPipeline.from_pretrained(
        model_id,
        dtype=torch.float32,
        safety_checker=None,
        requires_safety_checker=False,
    )
    pipe = pipe.to("cpu")
    pipe.set_progress_bar_config(disable=True)
    # Attention slicing reduces peak RAM on CPU.
    if hasattr(pipe, "enable_attention_slicing"):
        pipe.enable_attention_slicing()
    return pipe


def build_website_prompt(
    *,
    domain: str,
    idea: str,
    viewport: str = "desktop",
) -> str:
    # Keep under CLIP's ~77 token limit.
    idea = (idea or "clean modern homepage").strip()
    if len(idea) > 80:
        idea = idea[:77].rstrip() + "..."
    if viewport == "desktop":
        return (
            f"website homepage UI mockup for {domain}, {idea}, "
            "nav bar, hero headline, CTA button, SaaS landing page, "
            "Figma web design screenshot"
        )
    return (
        f"mobile website UI mockup for {domain}, {idea}, "
        "hero, CTA button, clean app landing page, "
        "smartphone screenshot"
    )


DEFAULT_NEGATIVE = (
    "photo of a room, interior design, kitchen, landscape, people faces, "
    "blurry, low quality, distorted text, unreadable garbage text, watermark, "
    "logo spam, collage, many panels, screenshot of code, "
    "extra limbs, deformed, NSFW, 3d render of building exterior"
)


def generate_ai_image(
    prompt: str,
    *,
    model_id: str = DEFAULT_MODEL_ID,
    steps: int = DEFAULT_STEPS,
    guidance: float = DEFAULT_GUIDANCE,
    width: int = DEFAULT_SIZE,
    height: int = DEFAULT_SIZE,
    seed: int | None = 42,
) -> Image.Image:
    import torch

    pipe = _load_pipeline(model_id)
    generator = None
    if seed is not None:
        generator = torch.Generator(device="cpu").manual_seed(seed)

    result = pipe(
        prompt=prompt,
        negative_prompt=DEFAULT_NEGATIVE,
        num_inference_steps=steps,
        guidance_scale=guidance,
        width=width,
        height=height,
        generator=generator,
    )
    image = result.images[0]
    return image
