# MAMT2 Model Integration Notes

## 原始 MAMT2 项目路径

`D:\pythonproject\MAMT2-final\detectron2-main`

## 当前真实模型环境

当前真实模型测试阶段使用 conda 环境：`General`。

不要创建或假设存在 `det2` 环境。

## 推理配置

Config:

`D:\pythonproject\MAMT2-final\detectron2-main\projects\MAMT2\output\mamt2_swin_fpn_task18pretrained_paper_strong\config.yaml`

Weight:

`D:\pythonproject\MAMT2-final\detectron2-main\projects\MAMT2\output\mamt2_swin_fpn_task18pretrained_paper_strong\model_best_segm.pth`

输出图目录：

`D:\pythonproject\mamt2-cloud-shm\backend\app\outputs`

## 类别映射

Detectron2 输出 `pred_classes = 0` 映射为前端展示标签：`spalling`。

## 单图测试命令

在 `General` 环境中，从 FastAPI+React 项目根目录运行：

```bat
conda activate General
cd /d D:\pythonproject\mamt2-cloud-shm
python worker\test_mamt2_predictor.py --image D:\path\to\test.jpg
```

也可以显式指定输出目录：

```bat
python worker\test_mamt2_predictor.py --image D:\path\to\test.jpg --output-dir D:\pythonproject\mamt2-cloud-shm\backend\app\outputs
```

该测试不会启动 FastAPI，也不会修改后端或前端代码。

## 与 FastAPI 接入的下一步计划

1. 先在 `General` 环境中确认 `worker/mamt2_predictor.py` 单图推理可用。
2. 确认输出 JSON 包含 `boxes`、`labels`、`scores`、`masks`、`result_image_path`、`result_filename`。
3. 确认 `result_image_path` 对应的 bbox+mask 可视化图存在。
4. 再考虑让 `backend/app/infer_mamt2.py` 调用 `predict_image_with_mamt2()`，替换当前 mock。
5. 如果 FastAPI 运行环境不能直接 import Detectron2，则改为独立 worker HTTP 服务。

## 为什么未来要拆成 api 服务和 worker 服务

真实 MAMT2/Detectron2 推理依赖 PyTorch、Detectron2、timm、OpenCV 和较大的模型权重。把 API 和模型 worker 拆开可以：

- 让 API 镜像保持轻量。
- 让模型 worker 独立使用 GPU 资源。
- 避免模型加载失败影响前端/API 基础服务。
- 支持后续在 Kubernetes 中扩缩容 worker。
- 为批量推理、队列任务、异步任务留下空间。

## 当前风险点

- `config.yaml` 中可能包含旧机器上的绝对路径，例如 Swin checkpoint 路径；如果本机不存在，需要后续覆盖 `MODEL.SWIN.CHECKPOINT_PATH`。
- `General` 环境必须能 import `detectron2`、`torch`、`timm`、`cv2`。
- 首次加载模型会比较慢，FastAPI 接入时应使用模块级单例，避免每次请求重复加载。
- 当前 mask polygon 只提取每个 mask 的最大外轮廓，复杂多连通区域会被简化。
- 输出目录需要有写权限。
- GPU/CPU 设备选择依赖当前 `torch.cuda.is_available()`，CPU 推理可能较慢。

## Worker HTTP 服务

真实 MAMT2 Worker 服务运行在 `General` 环境中，默认监听 `127.0.0.1:9000`。

启动命令：

```bat
conda activate General
cd /d D:\pythonproject\mamt2-cloud-shm
python worker\mamt2_worker_api.py
```

健康检查：

```bat
curl http://127.0.0.1:9000/healthz
```

单图 HTTP 推理测试：

```bat
curl -X POST http://127.0.0.1:9000/predict ^
  -H "Content-Type: application/json" ^
  -d "{\"image_path\":\"D:/path/to/image.jpg\"}"
```

也可以传入自定义输出目录：

```bat
curl -X POST http://127.0.0.1:9000/predict ^
  -H "Content-Type: application/json" ^
  -d "{\"image_path\":\"D:/path/to/image.jpg\",\"output_dir\":\"D:/pythonproject/mamt2-cloud-shm/backend/app/outputs\"}"
```

当前阶段该 Worker 服务独立运行，不修改 `backend/app/main.py`、`backend/app/infer_mamt2.py` 或任何前端文件。后续 FastAPI 主服务可以通过 HTTP 调用该 Worker 的 `/predict` 接口。

## 路径环境变量覆盖

当前 Windows 本地开发默认使用代码中的绝对路径，因此原有单图测试命令仍然可用，不需要额外设置环境变量。

未来 Docker/K8s 部署时，可以通过环境变量覆盖这些路径：

- `MAMT2_DETECTRON2_ROOT`：真实 Detectron2/MAMT2 项目根目录。
- `MAMT2_CONFIG_PATH`：MAMT2 推理 `config.yaml` 路径。
- `MAMT2_WEIGHT_PATH`：MAMT2 推理权重 `.pth` 路径。
- `MAMT2_OUTPUT_DIR`：bbox+mask 可视化结果图输出目录。

示例：

```bat
set MAMT2_DETECTRON2_ROOT=D:\pythonproject\MAMT2-final\detectron2-main
set MAMT2_CONFIG_PATH=D:\pythonproject\MAMT2-final\detectron2-main\projects\MAMT2\output\mamt2_swin_fpn_task18pretrained_paper_strong\config.yaml
set MAMT2_WEIGHT_PATH=D:\pythonproject\MAMT2-final\detectron2-main\projects\MAMT2\output\mamt2_swin_fpn_task18pretrained_paper_strong\model_best_segm.pth
set MAMT2_OUTPUT_DIR=D:\pythonproject\mamt2-cloud-shm\backend\app\outputs
```

权重文件不建议提交到 Git。后续应使用 `model/weights` 本地目录、Kubernetes PVC，或对象存储来管理模型权重，并通过 `MAMT2_WEIGHT_PATH` 指向实际挂载位置。

## 本地三服务启动方式

本地开发时可以拆成三个服务：`frontend`、`backend api`、`mamt2 worker`。前端不用改，仍然请求 `http://127.0.0.1:8000/predict`。

默认不设置 `USE_REAL_MAMT2` 时仍然是 mock 模式。真实推理模式需要先启动 MAMT2 Worker 服务。

1. 启动 Worker：

```bat
conda activate General
bash scripts/start_worker.sh
```

2. 启动真实推理后端：

```bat
conda activate mamt2-api
bash scripts/start_backend_real.sh
```

3. 启动 mock 后端：

```bat
conda activate mamt2-api
bash scripts/start_backend_mock.sh
```

后端启动时会在终端输出当前推理模式：

```text
[infer_mamt2] USE_REAL_MAMT2=false, using mock predictor
```

或：

```text
[infer_mamt2] USE_REAL_MAMT2=true, using worker: http://127.0.0.1:9000
```

真实推理请求时，后端还会打印 Worker URL、上传图片绝对路径和输出目录，便于确认请求是否走到了真实模型服务。

### 脚本路径自动定位

`scripts/start_worker.sh`、`scripts/start_backend_real.sh`、`scripts/start_backend_mock.sh` 不再依赖固定 D 盘路径。脚本会通过自身位置自动计算项目根目录：

```bash
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
```

因此在 Windows Git Bash 和 Ubuntu Bash 中，只要从项目内或项目外调用这些脚本，都可以根据当前项目实际位置自动定位。

## Docker/K8s 模型路径与权重管理

当前 Windows 本地路径只是开发阶段默认值，用于快速连接本机的 `MAMT2-final` 项目和已训练权重。

Docker/K8s 阶段应通过环境变量覆盖路径：

- `MAMT2_DETECTRON2_ROOT`
- `MAMT2_CONFIG_PATH`
- `MAMT2_WEIGHT_PATH`
- `MAMT2_OUTPUT_DIR`

权重文件不要提交到 Git。推荐后续使用以下方式管理：

- `model/weights` 本地目录挂载，适合 Docker Compose 和单机调试。
- Kubernetes PVC，适合集群内持久化挂载模型文件。
- 对象存储，例如 MinIO/S3，适合模型版本管理和多节点分发。

Worker 镜像中可以只包含推理代码和依赖，模型 config/weight 由环境变量指向挂载位置。

## Worker 文件上传推理接口

Worker 保留两个真实推理接口：

- `POST /predict`：传入本地 `image_path`，适合 Windows 本地调试，要求 backend 和 worker 能访问同一条本机绝对路径。
- `POST /predict-file`：使用 `multipart/form-data` 上传图片文件，更适合 Docker/K8s。

Docker/K8s 中容器文件系统彼此隔离，不推荐服务之间传本地绝对路径。后续 Docker 化 backend 时，主后端会通过 `/predict-file` 把图片文件上传给 worker，worker 推理后返回 `result_image_base64`，backend 再保存结果图到自己的 outputs 目录。

前端不需要修改，仍然上传图片到 backend api 的 `/predict`。backend 内部负责选择 mock、路径调试接口或文件上传接口。

文件上传接口测试示例：

```bash
curl -X POST http://127.0.0.1:9000/predict-file \
  -F "file=@D:/path/to/image.jpg"
```

## Worker 环境依赖说明

`backend/requirements.txt` 是轻量 API 依赖，只包含 FastAPI 主后端需要的包，例如 `fastapi`、`uvicorn`、`python-multipart`、`pillow`、`requests`。

`worker/requirements.txt` 是重型 MAMT2 Worker 依赖说明，包含 PyTorch、Detectron2 生态、timm、OpenCV、COCO 工具和 Detectron2 常用基础库。

当前 Windows 本地真实推理使用已有 Conda 环境 `General`。未来 Ubuntu/Docker 阶段建议创建独立的 `mamt2-worker` 环境，不建议继续复用 `General`。

不要直接提交完整 `General` 环境的 `pip freeze` 结果；它通常包含大量本机无关包、Windows 特定包和临时实验依赖。应基于 `worker/environment.yml` 和 `worker/requirements.txt` 在目标 Ubuntu/CUDA 环境中逐步固定版本。

未来 Ubuntu 环境模板：

```bash
conda env create -f worker/environment.yml
conda activate mamt2-worker
```

PyTorch/CUDA 与 Detectron2 的安装版本需要根据目标 GPU、CUDA Runtime 和基础镜像单独固定。

## Docker 轻量模式

当前 Docker 轻量模式只容器化 `frontend` 和 `backend api`，暂不容器化 MAMT2 Worker。

启动步骤：

1. 宿主机启动 Worker：

```bash
conda activate General
bash scripts/start_worker.sh
```

2. 启动 frontend 和 backend 容器：

```bash
docker compose up --build
```

3. 访问前端：

```text
http://localhost:5173
```

该模式下，backend 容器通过 `http://host.docker.internal:9000` 访问宿主机 Worker。前端仍然请求 `http://127.0.0.1:8000`，由 backend api 再调用 Worker 的 `/predict-file` 接口完成真实推理。

下一阶段再 Docker 化 MAMT2 Worker，并通过环境变量和模型挂载管理 `MAMT2_DETECTRON2_ROOT`、`MAMT2_CONFIG_PATH`、`MAMT2_WEIGHT_PATH` 和 `MAMT2_OUTPUT_DIR`。
