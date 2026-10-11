"""Single entry point used by both the API and the UI."""
from functools import lru_cache

from PIL import Image

from model import XRayModel
from report import make_report


@lru_cache(maxsize=1)
def get_model() -> XRayModel:
    return XRayModel()


def analyze(img: Image.Image, symptoms: str = "", top_k: int = 5) -> dict:
    m = get_model()
    x, gray = m.preprocess(img)
    findings = m.predict(x, top_k=top_k)
    top_label = findings[0][0]
    cam = m.gradcam(x, top_label)
    heatmap = m.overlay(gray, cam)
    return {
        "findings": findings,
        "heatmap_label": top_label,
        "heatmap": heatmap,
        "report": make_report(findings, symptoms),
    }
