FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=2

WORKDIR /app

RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN grep -v '^streamlit' requirements.txt > req-api.txt \
    && pip install -r req-api.txt

# Patch every affected TorchXRayVision backbone file; the import appears in
# both densenet.py and vgg.py in some published versions.
RUN grep -RIl 'from model.utils import get_norm' /usr/local/lib/python3.11/site-packages/torchxrayvision/baseline_models \
    | xargs -r sed -i 's/from model\.utils import get_norm/from ..utils import get_norm/g' \
    && python -c "import torchxrayvision as xrv; xrv.models.DenseNet(weights='densenet121-res224-all')"

COPY model.py report.py pipeline.py db.py models.py ratelimit.py assistant.py api.py ./

EXPOSE 8000
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]
