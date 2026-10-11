FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=2

WORKDIR /app

RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN grep -v '^streamlit' requirements.txt > req-api.txt \
    && pip install -r req-api.txt

# TorchXRayVision currently ships jfhealthcare backbone files with an
# invalid absolute import. Patch those files explicitly, then smoke-test import.
RUN python - <<'PY'
from pathlib import Path
root = Path("/usr/local/lib/python3.11/site-packages/torchxrayvision/baseline_models/jfhealthcare/model/backbone")
for name in ("densenet.py", "vgg.py"):
    path = root / name
    text = path.read_text()
    text = text.replace("from model.utils import get_norm", "from ..utils import get_norm")
    path.write_text(text)
    print(f"Patched {path}")
PY

RUN python -c "import torchxrayvision as xrv; print('TorchXRayVision import OK'); xrv.models.DenseNet(weights='densenet121-res224-all'); print('DenseNet weights OK')"

COPY model.py report.py pipeline.py db.py models.py ratelimit.py assistant.py api.py ./

EXPOSE 8000
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]
