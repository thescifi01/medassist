FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=2

WORKDIR /app

RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN grep -v '^streamlit' requirements.txt > req-api.txt \
    && pip install -r req-api.txt

# The published TorchXRayVision jfhealthcare package has this bad import in
# several backbone files (including inception.py, densenet.py and vgg.py).
# Patch every Python file in that backbone directory, not just a fixed list.
RUN python - <<'PY'
from pathlib import Path

root = Path("/usr/local/lib/python3.11/site-packages/torchxrayvision/baseline_models/jfhealthcare/model/backbone")
needle = "from model.utils import get_norm"
replacement = "from ..utils import get_norm"
patched = []

for path in root.rglob("*.py"):
    source = path.read_text()
    if needle in source:
        path.write_text(source.replace(needle, replacement))
        patched.append(str(path))

print("Patched jfhealthcare backbone files:", patched)
if not patched:
    raise SystemExit("Expected broken import was not found; refusing to continue")

# Fail the image build here if the package/model still cannot import.
import torchxrayvision as xrv
print("TorchXRayVision import OK")
xrv.models.DenseNet(weights="densenet121-res224-all")
print("DenseNet weights OK")
PY

COPY model.py report.py pipeline.py db.py models.py ratelimit.py assistant.py api.py ./

EXPOSE 8000
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]
