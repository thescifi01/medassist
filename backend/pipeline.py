"""Single entry point used by both the API and the UI."""
from functools import lru_cache
import logging
import time

import numpy as np
from PIL import Image

from model import XRayModel
from report import make_report

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_model() -> XRayModel:
    return XRayModel()


def analyze(img: Image.Image, symptoms: str = "", top_k: int = 5) -> dict:
    started = time.perf_counter()
    m = get_model()
    stage = time.perf_counter()
    x, gray = m.preprocess(img)
    logger.info("analysis stage=preprocess seconds=%.2f", time.perf_counter() - stage)
    stage = time.perf_counter()
    findings = m.predict(x, top_k=top_k)
    logger.info("analysis stage=predict seconds=%.2f", time.perf_counter() - stage)

    top_label = findings[0][0]
    heatmap_label = top_label
    stage = time.perf_counter()
    try:
        # Grad-CAM needs autograd and extra activation memory. On a small free
        # instance it can fail even after prediction succeeded; do not discard
        # the useful prediction/report just because the optional visual failed.
        cam = m.gradcam(x, top_label)
        heatmap = m.overlay(gray, cam)
        logger.info("analysis stage=gradcam status=ok seconds=%.2f", time.perf_counter() - stage)
    except Exception:
        logger.exception("analysis stage=gradcam status=failed; returning X-ray preview")
        # Explicitly show the plain X-ray instead of presenting a fake heatmap.
        preview = gray - gray.min()
        preview = preview / (preview.max() + 1e-8)
        preview = np.clip(preview * 255, 0, 255).astype(np.uint8)
        heatmap = Image.fromarray(preview).convert("RGB").resize((448, 448))
        heatmap_label = f"{top_label} — heatmap unavailable"

    logger.info("analysis stage=complete seconds=%.2f", time.perf_counter() - started)
    return {
        "findings": findings,
        "heatmap_label": heatmap_label,
        "heatmap": heatmap,
        "report": make_report(findings, symptoms),
    }
