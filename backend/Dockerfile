# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

WORKDIR /app

# The backend does not use CUDA inside Docker; Ollama runs natively on Windows.
# Install the smaller CPU PyTorch wheel first and preserve pip downloads across
# transient network failures during BuildKit rebuilds.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 --timeout 120 \
    --index-url https://download.pytorch.org/whl/cpu \
    "torch>=2.2" "torchvision>=0.17"

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 --timeout 120 -r requirements.txt

# RapidOCR pulls the desktop OpenCV wheel, which imports libGL/libXCB. Replace
# it with the API-compatible, checksum-verified headless wheel vendored for a
# reproducible server-only build.
COPY vendor/opencv_python_headless-5.0.0.93-cp37-abi3-manylinux_2_28_x86_64.whl /tmp/opencv_python_headless-5.0.0.93-cp37-abi3-manylinux_2_28_x86_64.whl
RUN echo "ed709fdf9aa0bd1f2ed8549e71d19449b03a675bb581eb292285f6861953be37  /tmp/opencv_python_headless-5.0.0.93-cp37-abi3-manylinux_2_28_x86_64.whl" | sha256sum -c - \
    && pip uninstall -y opencv-python \
    && pip install --no-cache-dir --no-deps /tmp/opencv_python_headless-5.0.0.93-cp37-abi3-manylinux_2_28_x86_64.whl \
    && rm /tmp/opencv_python_headless-5.0.0.93-cp37-abi3-manylinux_2_28_x86_64.whl

COPY . .

RUN mkdir -p uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
