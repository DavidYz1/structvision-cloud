# StructVision Cloud

StructVision Cloud 是一个 **Kubernetes-native GPU visual inference platform**，用于结构表观病害检测与实例分割。系统将 React 前端、FastAPI API、NVIDIA GPU Worker、MAMT2/Detectron2 推理、模型 PVC 和 Prometheus/Grafana 可观测性组合为可声明部署的完整链路。

当前 v0.8.0 面向单节点、单 GPU Minikube 环境，真实请求链路已经贯通：

```text
Browser
  -> ingress-nginx / mamt2-ingress
  -> frontend Service / React + Nginx
  -> backend Service / FastAPI
  -> mamt2-worker Service / GPU Worker
  -> Detectron2 + MAMT2 + CUDA
  -> mamt2-model PVC
```

详细设计见 [docs/architecture.md](docs/architecture.md)，监控操作见 [monitoring/README.md](monitoring/README.md)。

## 系统架构

### 应用组件

- **Frontend**：React/Vite 构建的 Web UI，由前端 Nginx 托管；Nginx 将 `/api/*` 反向代理到 `backend:8000`。
- **Backend**：FastAPI API，接收上传文件、同步调用 GPU Worker、保存 Worker 返回的结果图，并通过 `/results/{filename}` 提供结果。
- **GPU Worker**：FastAPI + Detectron2/MAMT2 推理服务，通过 `/predict-file` 接收 Backend 上传的图片；模型首次使用时懒加载到 GPU。
- **Ingress**：`mamt2-ingress` 使用 ingress-nginx 将外部流量转发到 `frontend` Service。
- **模型交付**：Helm 与原生 Kubernetes 清单均通过 Init Container 从固定 Hugging Face revision 首次下载权重，执行 SHA256 完整性校验，并通过唯一临时文件和原子 `mv` 写入模型 PVC；Pod 重建时复用 PVC 缓存。
- **PVC**：Chart 默认创建模型 PVC；Init Container 以可写方式挂载，Worker 以只读方式挂载到 `/models`。也可通过 `worker.model.existingClaim` 复用外部 PVC。
- **ConfigMap**：`mamt2-config` 为 Backend 提供 `USE_REAL_MAMT2` 和 `MAMT2_WORKER_URL`。

### 可观测性组件

- **Prometheus Operator**：根据 ServiceMonitor 自动生成 Prometheus 抓取配置。
- **Prometheus**：抓取 Backend、Worker 和 DCGM Exporter 指标并保存时序数据。
- **Grafana**：使用 UID 为 `prometheus` 的数据源展示应用、推理和 GPU 指标。
- **Backend/Worker ServiceMonitor**：由应用 Helm Chart 创建，抓取对应 Service 的 `/metrics`。
- **NVIDIA DCGM Exporter**：节点级 DaemonSet，暴露 GPU 利用率、显存、温度和功耗等 `DCGM_*` 指标；它不申请 `nvidia.com/gpu`。
- **Grafana Dashboard Sidecar**：跨 Namespace 发现带 `grafana_dashboard: "1"` 标签的 ConfigMap，并自动加载 Dashboard JSON。

## 完整请求链路

1. 浏览器向 `mamt2.test` 发起请求。
2. ingress-nginx 根据 `mamt2-ingress` 将请求转发到 `frontend` Service。
3. 前端 Nginx 提供 React 静态资源，并将 `/api/predict` 转发为 Backend 的 `POST /predict`。
4. Backend 将上传图片暂存到自身 Pod 文件系统。
5. Backend 同步调用 `http://mamt2-worker:9000/predict-file`，超时为 120 秒。
6. Worker 从 PVC 加载 MAMT2 权重，使用 CUDA/Detectron2 完成实例分割。
7. Worker 返回 boxes、labels、scores、masks 和 Base64 结果图。
8. Backend 将结果图写入临时 outputs 目录，并向浏览器返回 `/api/results/{filename}`。
9. 浏览器通过同一 Ingress 和前端 Nginx 获取结果图并展示。

## GPU 调度与 Recreate 策略

Worker 请求并限制：

```yaml
nvidia.com/gpu: 1
```

当前 Minikube 节点只有一张可调度 GPU，Worker 因而固定为单副本。Worker Deployment 使用 `Recreate`，更新时先终止旧 Pod，再创建新 Pod。若使用默认 RollingUpdate，旧 Pod 占用唯一 GPU 时，新 Pod 会因为无法获得第二张 GPU 而长期 Pending，滚动发布无法完成。`Recreate` 同时避免两个模型进程争用同一 GPU 显存。

## 模型权重自动配置

Helm Chart 和原生 Kubernetes 清单都会在模型 PVC 中检查 `model_best_segm.pth`。首次部署时，如果 PVC 中没有校验通过的权重，`model-weight-downloader` Init Container 会从公开 Hugging Face 仓库的固定 revision 下载到同一 PVC 的唯一临时文件，校验 SHA256 后通过原子 `mv` 写入正式路径。后续 Pod 重启会校验已有文件并跳过重复下载。

下载、网络访问或 SHA256 校验失败时，Init Container 非零退出，Worker 不会启动；错误可从 Init Container 日志中查看。目标部署环境必须能够访问配置的 Hugging Face 仓库，且该仓库必须允许部署者下载对应 revision。

下载代理默认关闭：

```yaml
worker:
  model:
    download:
      proxy:
        enabled: false
```

云服务器能够直接访问 Hugging Face 时不需要代理。网络受限时可按需使用以下占位示例，并将地址替换为部署环境实际可用的代理：

```bash
helm upgrade --install mamt2 helm \
  -n mamt2 \
  --create-namespace \
  --set worker.model.download.proxy.enabled=true \
  --set-string worker.model.download.proxy.httpProxy=http://proxy.example.invalid:3128 \
  --set-string worker.model.download.proxy.httpsProxy=http://proxy.example.invalid:3128
```

原生清单默认直连，不包含 `HTTP_PROXY`、`HTTPS_PROXY` 或对应的小写变量。如确需代理，只应在应用清单前为 `k8s/worker.yaml` 的 `model-weight-downloader` Init Container 增加这些变量；不要把代理变量加入 Worker 主容器、Backend 或 Frontend。示例地址 `proxy.example.invalid` 是明确的占位值，不能直接用于部署。

`ingress.enabled=false` 只关闭入站 Ingress，不控制 Pod 的外网访问，也不能替代上述下载代理配置。

## 仓库结构

```text
backend/                      FastAPI Backend 与应用指标
frontend/                     React UI 与前端 Nginx
worker/                       GPU Worker、MAMT2 适配和 Worker 指标
helm/                         应用 Helm Chart
  dashboards/                Grafana Dashboard JSON
  templates/                 Deployment、Service、Ingress、监控资源
k8s/                          不使用 Helm 时的原生 Kubernetes 部署入口
  optional/                   可选 Ingress 和 ServiceMonitor
monitoring/                   Prometheus/Grafana 与 DCGM values、操作文档
docs/                         架构和模型集成文档
.github/workflows/ci.yml      静态检查与 Helm 渲染 CI
```

## 前置条件

- Linux 主机和 NVIDIA 驱动
- NVIDIA Container Toolkit
- Docker
- Minikube
- kubectl
- Helm 3
- 构建 Worker 镜像时能够访问固定版本的 Detectron2 wheel 下载地址
- 不提交到 Git 的 `model_best_segm.pth`

## 本地 Minikube 部署

以下命令用于部署说明；执行前请确认本机 NVIDIA 容器运行时可用。

### 1. 启动单节点 GPU Minikube

```bash
minikube start --profile mamt2 --driver=docker --gpus=all
minikube --profile mamt2 addons enable ingress
kubectl config use-context mamt2
```

确认节点公开 GPU resource：

```bash
kubectl get node -o custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu
```

### 2. 将镜像构建到 Minikube Docker daemon

```bash
eval "$(minikube --profile mamt2 docker-env)"

docker build -t mamt2-frontend:v1 frontend
docker build -t mamt2-backend:v1 backend
docker build -t mamt2-worker:hf-v1 -f worker/Dockerfile.hf .
```

旁路 `worker/Dockerfile.hf` 使用当前仓库作为构建上下文。MAMT2 在线 runtime 和推理配置位于仓库内；固定版本的 Detectron2 wheel 从版本化 GitHub Release URL 下载并强制校验 SHA256。模型权重不进入构建上下文或镜像，仍在运行时挂载。原 `worker/Dockerfile` 暂留作旧链路基线，不用于 `hf-v1`。该 GPU 镜像较大，不在普通 PR CI 中构建；需要时通过 CI 的 `workflow_dispatch` 并设置 `build_worker=true` 手动验证。

Frontend、Backend、Worker 的权威依赖文件、基础镜像 digest、外部产物来源和更新方法见 [依赖与构建输入](docs/reproducible-builds.md)。

GHCR 的候选/版本发布入口、权限边界、公开候选 digest 和更新方式见 [GHCR 镜像发布](docs/ghcr-images.md)。

### 3A. 使用 Helm 部署应用（推荐）

默认 values 保持本地 Minikube 镜像兼容：

```bash
helm upgrade --install mamt2 helm \
  -n mamt2 \
  --create-namespace
```

使用公开 GHCR 候选进行正式的 digest 固定部署：

```bash
helm upgrade --install structvision helm \
  -n structvision \
  --create-namespace \
  -f helm/values-release.yaml
```

`values-release.yaml` 中的 `sha-<commit>` tag 用于人工识别来源；Deployment 实际使用 `repository@sha256:...`，digest 才是 Kubernetes 拉取的不可变内容标识。三个 GHCR Package 必须保持 public。

默认配置直接访问 Hugging Face，并自动创建模型 PVC、下载和校验权重。默认资源名称保持稳定：`frontend`、`backend`、`mamt2-worker`、`mamt2-config`、`mamt2-ingress`。

Helm 默认渲染 ServiceMonitor；集群尚未安装 Prometheus Operator CRD 时，通过以下参数关闭它：

```bash
helm upgrade --install mamt2 helm \
  -n mamt2 \
  --create-namespace \
  --set monitoring.serviceMonitor.enabled=false
```

### 3B. 使用原生 Kubernetes 清单（不使用 Helm）

原生清单提供与 Helm 相同的 Frontend、Backend、GPU Worker、ConfigMap、模型 PVC 和自动权重配置，但仍明确保留本地镜像引用。使用原生入口时必须先按第 2 步构建 `mamt2-frontend:v1`、`mamt2-backend:v1` 和 `mamt2-worker:hf-v1`；需要公开 GHCR digest 的部署应使用上面的 Helm `values-release.yaml`。

先可靠创建 Namespace，再一次应用目录中的全部核心资源：

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/
```

`kubectl apply -f` 默认不递归子目录，因此上面的核心安装不会应用 `k8s/optional/`。

首次部署时，Worker Init Container 会下载固定 revision 的权重、执行 SHA256 校验，并只在校验成功后原子写入 `mamt2-model` PVC。后续部署会校验并复用缓存；下载或校验失败时 Worker 主容器不会启动，且只会读取最终的 `/models/model_best_segm.pth`。

原生 Ingress 是显式可选资源；不应用该文件就等价于 Helm 的 `ingress.enabled=false`：

```bash
kubectl apply -f k8s/optional/ingress.yaml
```

ServiceMonitor 依赖 Prometheus Operator CRD，不在核心目录安装流程中。确认 CRD 已存在后再应用：

```bash
kubectl get crd servicemonitors.monitoring.coreos.com
kubectl apply -f k8s/optional/servicemonitors.yaml
```

### 4. 配置本地域名

```bash
echo "$(minikube --profile mamt2 ip) mamt2.test" | sudo tee -a /etc/hosts
curl http://mamt2.test/api/
```

应用 Helm 默认 Ingress 或原生可选 Ingress 后，浏览器访问 `http://mamt2.test`。

## 安装监控

安装轻量 kube-prometheus-stack：

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  --values monitoring/kube-prometheus-stack-values.yaml
```

安装官方 NVIDIA DCGM Exporter：

```bash
helm repo add nvidia https://nvidia.github.io/dcgm-exporter/helm-charts
helm repo update
helm upgrade --install dcgm-exporter nvidia/dcgm-exporter \
  --namespace monitoring \
  --values monitoring/dcgm-exporter-values.yaml
```

重新发布应用 Chart，确保 ServiceMonitor 和 Dashboard ConfigMap 已声明：

```bash
helm upgrade --install mamt2 ./helm --namespace mamt2
```

使用原生清单时，Dashboard ConfigMap 仍由 Helm 管理；只需在 Prometheus Operator CRD 就绪后单独应用 `k8s/optional/servicemonitors.yaml`，即可抓取 Backend 和 Worker 的 `/metrics`。

## Grafana Dashboard

应用 Chart 默认创建 `structvision-grafana-dashboard` ConfigMap。Grafana Sidecar 自动加载：

- 标题：**StructVision Cloud Overview**
- UID：`structvision-cloud-overview`
- JSON：[helm/dashboards/structvision-overview.json](helm/dashboards/structvision-overview.json)

Dashboard 包含 target 状态、调用结果、成功率、HTTP 请求、P50/P95/P99 延迟、模型加载、检测实例和 GPU 遥测。可通过以下命令访问 Grafana：

```bash
kubectl port-forward --namespace monitoring \
  service/kube-prometheus-stack-grafana 3000:80
```

然后访问 `http://127.0.0.1:3000/d/structvision-cloud-overview`。

## 验证命令

应用状态：

```bash
kubectl get pods,services,ingress,pvc --namespace mamt2
kubectl rollout status deployment/frontend --namespace mamt2
kubectl rollout status deployment/backend --namespace mamt2
kubectl rollout status deployment/mamt2-worker --namespace mamt2 --timeout=10m
kubectl logs deployment/mamt2-worker --namespace mamt2 \
  --container model-weight-downloader
kubectl get endpoints --namespace mamt2 backend mamt2-worker
```

接口和指标：

```bash
curl http://mamt2.test/api/
curl http://mamt2.test/api/metrics

kubectl port-forward --namespace mamt2 service/mamt2-worker 9000:9000
curl http://127.0.0.1:9000/healthz
curl http://127.0.0.1:9000/metrics
```

监控资源：

```bash
kubectl get servicemonitor --all-namespaces
kubectl get configmap structvision-grafana-dashboard --namespace mamt2
kubectl get pods --namespace monitoring
```

本地静态检查：

```bash
python3 -m compileall backend worker
python3 -m json.tool helm/dashboards/structvision-overview.json > /dev/null
helm lint helm
helm template mamt2 helm -n mamt2 > /tmp/mamt2-rendered.yaml
kubectl apply --dry-run=client --validate=false -f k8s/
```

## 故障排查

Worker 调度与 GPU：

```bash
kubectl describe pod --namespace mamt2 \
  --selector app=mamt2-worker
kubectl describe node
kubectl get events --namespace mamt2 --sort-by=.lastTimestamp
```

Worker 推理和完整 Python traceback：

```bash
kubectl logs --namespace mamt2 \
  --selector app=mamt2-worker \
  --follow
```

模型权重下载：

```bash
kubectl logs deployment/mamt2-worker --namespace mamt2 \
  --container model-weight-downloader
kubectl get pods,pvc --namespace mamt2
kubectl rollout status deployment/mamt2-worker --namespace mamt2 --timeout=10m
```

- `curl: (7)` 通常表示 DNS、路由、防火墙或代理等网络出口问题。
- HTTP `401` 通常表示 Hugging Face 仓库或目标 revision 的访问权限不满足。
- SHA256 校验失败表示下载文件与 Chart 中固定的模型清单不一致；Worker 会保持在 Init 阶段，不加载该文件。

Backend 到 Worker 调用：

```bash
kubectl logs --namespace mamt2 --selector app=backend --follow
kubectl get endpoints --namespace mamt2 mamt2-worker
```

Ingress：

```bash
kubectl describe ingress mamt2-ingress --namespace mamt2
kubectl logs --namespace ingress-nginx \
  --selector app.kubernetes.io/component=controller \
  --tail=200
```

Prometheus、ServiceMonitor 和 Dashboard Sidecar：

```bash
kubectl describe servicemonitor backend --namespace mamt2
kubectl describe servicemonitor mamt2-worker --namespace mamt2
kubectl logs --namespace monitoring \
  --selector app.kubernetes.io/name=grafana \
  --container grafana-sc-dashboard \
  --tail=200
```

## 当前限制

1. 推理链路为同步 HTTP 调用，长推理会占用请求连接。
2. 当前为单 GPU、单 Worker 副本，尚不支持并行 GPU 扩容。
3. 上传图片和结果图存储在 Backend Pod 临时文件系统，Pod 重建后会丢失。
4. 当前没有 MySQL、Redis 或 MinIO。

## 未来计划

1. 使用 Redis/Celery 引入异步推理任务队列。
2. 使用 MinIO 保存上传图片、结果图和可选模型工件。
3. 使用 MySQL/PostgreSQL 保存推理任务和结果元数据。
4. 支持多 GPU 调度、队列感知扩缩容和自动扩缩容。

## CI

GitHub Actions CI 在 pull request、`main` push 和手动触发时执行 Python 语法检查、Backend 轻量单元测试、Frontend lockfile 安装/ESLint/生产构建、Dashboard JSON、Helm 开关与代理断言、原生清单语义比较、仓库安全边界和空白检查，并构建但不推送 Frontend/Backend 镜像。默认 Worker job 只运行无需重依赖的 runtime layout 检查；约 8.5 GB 的 Worker 镜像仅在手动执行工作流并显式启用 `build_worker` 时构建且不推送。CI 不连接 Kubernetes、不执行 CUDA 推理，也不下载模型权重。
