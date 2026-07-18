FROM pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    HOME=/home/worker

# Python 虚拟环境以及 OpenCV、Matplotlib 所需的系统动态库
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-venv \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        libsm6 \
        libxext6 \
        libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# 继承基础镜像中的 PyTorch、torchvision 和 CUDA Python 包，
# 其余 Worker 依赖安装到 /opt/venv，不修改 Ubuntu 系统 Python。
RUN /usr/bin/python3 -m venv \
        --system-site-packages \
        "$VIRTUAL_ENV" \
    && python -c "import torch, torchvision; \
print('PyTorch:', torch.__version__); \
print('torchvision:', torchvision.__version__); \
print('CUDA runtime:', torch.version.cuda)"

WORKDIR /app

# 先安装固定版本的 Worker Python 依赖
COPY mamt2-cloud-shm/worker/requirements-docker.txt \
     /tmp/requirements-docker.txt

RUN python -m pip install \
        --no-cache-dir \
        -r /tmp/requirements-docker.txt

# 安装已编译并验证的 Detectron2 wheel
COPY mamt2-artifacts/wheels/detectron2-0.6-cp312-cp312-linux_x86_64.whl \
     /tmp/detectron2-0.6-cp312-cp312-linux_x86_64.whl

RUN python -m pip install \
        --no-cache-dir \
        --no-deps \
        /tmp/detectron2-0.6-cp312-cp312-linux_x86_64.whl \
    && rm -f /tmp/detectron2-0.6-cp312-cp312-linux_x86_64.whl \
    && python -c "import detectron2; from detectron2 import _C; \
print('Detectron2:', detectron2.__version__); \
print('Detectron2 extension:', _C.__file__)"

# Worker、MAMT2 自定义模型代码和容器专用配置
COPY detectron2/projects/MAMT2_main /opt/MAMT2_main
COPY mamt2-cloud-shm/worker /app/worker
COPY mamt2-artifacts/configs/config_container.yaml \
     /app/config/config_container.yaml

# 给代码中的 Detectron2 根目录检查提供稳定路径
RUN mkdir -p \
        /opt/detectron2 \
        /models \
        /outputs \
        /home/worker \
    && ln -s \
       "$(python -c 'import pathlib, detectron2; print(pathlib.Path(detectron2.__file__).parent)')" \
       /opt/detectron2/detectron2 \
    && chown -R 1000:1000 \
        /app \
        /outputs \
        /home/worker

ENV PYTHONPATH=/app:/opt/MAMT2_main \
    MAMT2_DETECTRON2_ROOT=/opt/detectron2 \
    MAMT2_MAIN_DIR=/opt/MAMT2_main \
    MAMT2_CONFIG_PATH=/app/config/config_container.yaml \
    MAMT2_WEIGHT_PATH=/models/model_best_segm.pth \
    MAMT2_OUTPUT_DIR=/outputs \
    MAMT2_WORKER_HOST=0.0.0.0 \
    MAMT2_WORKER_PORT=9000

USER 1000:1000

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9000/healthz', timeout=3)" || exit 1

CMD ["python", "-m", "uvicorn", "worker.mamt2_worker_api:app", \
     "--host", "0.0.0.0", "--port", "9000"]
