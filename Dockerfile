FROM runpod/pytorch:2.3.1-cuda12.1-py310

ENV PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    TRANSFORMERS_VERBOSITY=info \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /workspace

COPY . /workspace/fixgpt-main
WORKDIR /workspace/fixgpt-main

RUN python -m venv /workspace/venv && \
    /workspace/venv/bin/pip install --upgrade pip && \
    /workspace/venv/bin/pip install -r requirements.txt

EXPOSE 8000

CMD ["/bin/bash", "runpod_start.sh"]

