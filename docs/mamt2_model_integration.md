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
