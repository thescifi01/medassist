"""Single entry point used by both the API and the UI."""
from functools import lru_cache
import logging
import time

from PIL import Image

from model import XRayModel
from report import make_report


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
    stage = time.perf_counter()
    cam = m.gradcam(x, top_label)
    logger.info("analysis stage=gradcam seconds=%.2f", time.perf_counter() - stage)
    heatmap = m.overlay(gray, cam)
    logger.info("analysis stage=complete seconds=%.2f", time.perf_counter() - started)
    return {
        "findings": findings,
        "heatmap_label": top_label,
        "heatmap": heatmap,
        "report": make_report(findings, symptoms),
    }
