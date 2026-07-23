# 依赖与构建输入

本页定义正式 CI 与容器构建使用的权威输入。不要用宿主机 `pip freeze`、本机 editable checkout 或临时安装结果覆盖这些文件。

## 依赖文件边界

| 组件 | 人工维护的直接依赖 | 构建实际使用的锁定输入 |
| --- | --- | --- |
| Frontend | `frontend/package.json` | `frontend/package-lock.json`；本地、CI 和镜像均执行 `npm ci` |
| CI Python 工具 | `scripts/requirements-ci.in` | `scripts/requirements-ci.txt`；固定 CPython 3.10/Linux x86_64 wheel 及 SHA256 |
| Backend | `backend/requirements.in` | `backend/requirements.txt`；包含完整传递依赖和 PyPI SHA256 |
| Backend test | 无额外第三方测试依赖 | `backend/requirements-test.txt` 只引用 Backend 运行锁 |
| GPU Worker | `worker/requirements-docker.in` | `worker/base-packages-docker.txt` 固定并验证基础镜像已有包；`worker/requirements-docker.txt` 固定实际下载包及其 SHA256 |

Frontend 的 `package.json` 可以保留 semver 范围，因为安装只通过 lockfile；`package-lock.json` 的每个包都带精确版本和 integrity。Node 工具链由 `frontend/.node-version` 固定为 20.20.2。

Backend 锁文件使用 Python 3.10 生成。更新直接依赖后，在隔离环境中使用以下固定工具版本重新生成，审阅 diff 后再运行测试：

```bash
python3.10 -m venv /tmp/structvision-backend-lock
/tmp/structvision-backend-lock/bin/python -m pip install \
  pip==26.1.2 \
  pip-tools==7.6.0 \
  typing-extensions==4.15.0
/tmp/structvision-backend-lock/bin/pip-compile \
  --generate-hashes \
  --resolver=backtracking \
  --output-file backend/requirements.txt \
  backend/requirements.in
```

Worker 锁不是任意宿主机可直接安装的通用环境：PyTorch、torchvision、CUDA 和部分公共包由固定 digest 的 PyTorch 基础镜像提供，版本记录在 `worker/base-packages-docker.txt`，镜像构建会先执行 `worker/validate_base_packages.py` 拒绝版本漂移。其余实际下载的包记录在 `worker/requirements-docker.txt`，每项固定一个针对 CPython 3.12/Linux x86_64 审计过的 artifact SHA256。`Dockerfile.hf` 使用 `--require-hashes --no-deps` 安装该锁，防止传递依赖随日期重新解析；对 fvcore 等源码包关闭隔离构建，复用已验证的构建工具，避免临时 build environment 再解析一组浮动依赖。Detectron2 仍由单独校验的 wheel 提供。

更新 `worker/requirements-docker.in` 时，应在同一 tag + digest 基础镜像中解析闭包：基础镜像已有的包更新到 `base-packages-docker.txt`，需要下载的 artifact 更新到带哈希锁，并通过手动完整镜像构建验证。不要从宿主机 `pip freeze` 生成这两个文件。

历史文件 `worker/current-environment-freeze.txt` 已删除。它没有被 Dockerfile、CI 或脚本引用，且混入本机 editable Detectron2 路径，因此不能作为安装输入；需要追溯时使用 Git 历史。

`worker/requirements.txt` 和 `worker/environment.yml` 仅服务旧的本地/Conda 开发说明，不参与 `Dockerfile.hf` 或 CI 镜像构建。

## 基础镜像与外部产物

Dockerfile 保留可读 tag，并追加不可变 digest。tag 说明预期版本线，digest 决定实际拉取的 manifest：

| 用途 | 固定镜像 |
| --- | --- |
| Frontend build | `node:20.20.2-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293` |
| Frontend runtime | `nginx:1.31.2-alpine@sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa` |
| Backend runtime | `python:3.10.20-slim@sha256:e5300dc020a26a34a19337a57602955a2510e22abeb176edd6de6cd2cc927dd4` |
| Worker runtime | `pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime@sha256:eee11b3b3872a8c838e35ef48f08b2d5def2080902c7f666831310ca1a0ef2be` |
| 模型下载 initContainer | `curlimages/curl:8.14.1@sha256:9a1ed35addb45476afa911696297f8e115993df459278ed036182dd2cd22b67b` |

Detectron2 wheel 的来源闭环记录在 `model/manifest.yaml`：

- 上游源码：`facebookresearch/detectron2` commit `b599f139756bd3646a26a909caf86a1a159e53a7`；
- 容器打包补丁：`worker/detectron2-0.6-container.patch`，并记录补丁 SHA256；
- 发布产物：版本化 GitHub Release `runtime-deps-v1` 中固定文件名的 CPython 3.12/Linux x86_64 wheel；
- 下载器与 manifest 同时固定 URL 和 SHA256，校验失败时中止镜像构建。

Hugging Face 权重仍在运行时下载，不进入 Git 或 Worker 镜像。`model/manifest.yaml`、Helm values 和原生 Worker 清单共同固定 repo、40 位 revision、filename 与 SHA256；initContainer 校验后才原子写入 PVC。

## 构建上下文和 CI 防回归

根目录、Frontend 和 Backend 的 `.dockerignore` 都采用 deny-by-default allowlist。正式构建上下文不包含权重、`node_modules`、构建输出、本地 `.env`、上传文件、宿主机环境快照或旧的外部 Detectron2 checkout。

`scripts/validate_reproducibility.py` 在现有 CI 的 quality job 中检查：

- 正式 Python 输入没有 editable、`file://`、个人 home 或 Conda 环境路径；
- CI 工具、Backend 和 Worker 下载锁内每项都有 SHA256，Worker 的直接依赖必须由基础包清单或下载锁覆盖；
- npm lock 与 `package.json` 一致且每项有 integrity；
- 正式 Dockerfile 使用 tag + digest，不使用 `latest`；
- Detectron2、Hugging Face 权重和下载器镜像的来源字段保持闭环；
- 三个 Docker context 继续保持 allowlist。

外部 GitHub Actions 也固定到查询到的完整 commit SHA，Runner 使用 `ubuntu-24.04` 而非浮动的 `ubuntu-latest`。

完整 Worker 镜像仍不进入普通 PR CI。需要验证时，在 GitHub Actions 中选择 `CI` → `Run workflow`，将 `build_worker` 设为 `true`；该 job 只构建 `worker/Dockerfile.hf`，不登录或推送镜像。
