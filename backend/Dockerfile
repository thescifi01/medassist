FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=2

WORKDIR /app

RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN grep -v '^streamlit' requirements.txt > req-api.txt \
    && pip install -r req-api.txt

# Fix TorchXRayVision's jfhealthcare imports throughout its model package.
# Files directly in jfhealthcare/model need ".utils"; files in subpackages
# such as model/backbone need "..utils". Patching only backbone files missed
# attention_map.py and other modules, which caused repeated startup failures.
RUN python - <<'PY'
from pathlib import Path

root = Path("/usr/local/lib/python3.11/site-packages/torchxrayvision/baseline_models/jfhealthcare/model")
needle = "from model.utils import get_norm"
patched = []

for path in root.rglob("*.py"):
    source = path.read_text()
    if needle not in source:
        continue
    relative = path.parent.relative_to(root)
    replacement = "from .utils import get_norm" if str(relative) == "." else "from ..utils import get_norm"
    path.write_text(source.replace(needle, replacement))
    patched.append(f"{path.relative_to(root)} -> {replacement}")

print("Patched jfhealthcare imports:", patched)
if not patched:
    raise SystemExit("No broken jfhealthcare imports found; inspect installed TorchXRayVision version")

import torchxrayvision as xrv
print("TorchXRayVision import OK")
xrv.models.DenseNet(weights="densenet121-res224-all")
print("DenseNet weights OK")
PY

COPY model.py report.py pipeline.py db.py models.py ratelimit.py assistant.py api.py ./

EXPOSE 8000
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]
