# main.py

import logging
import time

from datetime import datetime, timezone

from easynmt import EasyNMT
from fastapi import FastAPI
from langdetect import detect, LangDetectException
from pydantic import BaseModel

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool


logging.basicConfig(level=logging.INFO)

LOG = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "m2m_100_418M"
MODEL_NAMES = {"m2m_100_418M", "m2m_100_1.2B"}

# Cache models on first use instead of loading everything at import time.
_MODEL_CACHE: dict[str, EasyNMT] = {}

def get_model(model_name: str) -> EasyNMT:
    """
    Lazy-load and cache EasyNMT models to reduce startup time and memory/VRAM usage.
    """
    if model_name not in MODEL_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model '{model_name}'. Available: {', '.join(sorted(MODEL_NAMES))}",
        )

    cached = _MODEL_CACHE.get(model_name)
    if cached is not None:
        return cached

    LOG.info("Loading EasyNMT model: %s", model_name)
    # Use CUDA if available; EasyNMT will fall back to CPU if not.
    m = EasyNMT(model_name, device="cuda")
    _MODEL_CACHE[model_name] = m
    return m



app = FastAPI()

class TranslateRequest(BaseModel):
    text: str
    # Optional: if provided, we skip auto-detection
    source_lang: str | None = None
    # Optional: if not provided and source_lang != 'en', we default to 'en'
    target_lang: str | None = None
    # Optional: choose a model (e.g. "m2m_100_418M", "m2m_100_1.2B")
    model: str | None = None

@app.post("/translate")
async def translate(req: TranslateRequest):
    # Decide which model to use
    # Decide which model to use (lazy-load)
    model_name = (req.model or DEFAULT_MODEL_NAME).strip()
    chosen_model = get_model(model_name)

    # Start from any explicit source/target in the request
    source_lang = req.source_lang.lower() if req.source_lang else None
    target_lang = req.target_lang.lower() if req.target_lang else None

    # Case A: both source and target are provided -> trust the caller
    if source_lang and target_lang:
        pass
    else:
        # Case B: at least one of source/target is missing -> auto-detect source if needed
        if not source_lang:
            detected_lang: str | None = None
            try:
                # langdetect can be flaky on very short/noisy strings; still try, but don't fail hard.
                detected_lang = detect(req.text)
            except LangDetectException:
                LOG.warning("Language detection failed; defaulting source_lang to 'en'")

            source_lang = (detected_lang or "en").lower()
            LOG.info("Auto-detected source language: %s", source_lang)

        # Decide target:
        if not target_lang:
            # If source is not English, default target to English
            if source_lang != "en":
                target_lang = "en"
            else:
                # Source is English and no explicit target -> no translation
                started_at = datetime.now().isoformat()
                finished_at = started_at
                duration_seconds = 0.0

                LOG.info(
                    "Text is English and no target_lang provided; "
                    "returning original text without translation."
                )

                return {
                    "translation": req.text,
                    "model": model_name,
                    "source_lang": source_lang,
                    "target_lang": source_lang,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "duration_seconds": duration_seconds,
                    "note": "Source language is English and no target_lang was provided; no translation performed.",
                }

    # 3. Timing + translation using the *computed* languages
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()

    try:
        def _do_translate() -> str:
            return chosen_model.translate(
                req.text,
                source_lang=source_lang,
                target_lang=target_lang,
                beam_size=1,
            )

        out = await run_in_threadpool(_do_translate)
    except Exception as e:
        LOG.exception("Translation failed")
        raise HTTPException(status_code=500, detail=f"Translation failed: {e}")

    # End timing
    t1 = time.perf_counter()
    finished_at = datetime.now(timezone.utc).isoformat()
    duration_seconds = t1 - t0

    # Log to console
    LOG.info(
        "Translation %s -> %s using %s took %.3f seconds",
        source_lang,
        target_lang,
        model_name,
        duration_seconds,
    )

    return {
        "translation": out,
        "model": model_name,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
    }

@app.get("/")
async def root():
    # Simple health check / sanity check endpoint
    return {"status": "ok", "default_model": DEFAULT_MODEL_NAME, "loaded_models": sorted(_MODEL_CACHE.keys())}
