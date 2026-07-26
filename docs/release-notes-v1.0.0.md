# StructVision Cloud v1.0.0 发布说明

本文记录 v1.0.0 的发布内容；它不表示 Git 标签、GitHub Release 或最终版本镜像已经创建。

## 本次发布

- 浏览器通过 React Frontend 上传图片，Nginx 将 `/api` 请求转发到 FastAPI Backend，Backend 使用 `httpx.AsyncClient` 异步调用 GPU Worker。
- GPU Worker 加载已经训练完成的 MAMT2 / Detectron2 模型，通过 PyTorch、CUDA 和 NVIDIA GPU 执行实例分割推理。
- Frontend、Backend 和 Worker 分别构建为 Docker 镜像，并通过 Kubernetes/K3s 与 Helm 管理 Deployment、Service、Ingress、ConfigMap 和模型 PVC。
- Worker 启动前由 Init Container 从 Hugging Face 固定 revision 下载权重，校验 SHA256 后原子写入 PVC；Worker 只读挂载已校验文件，模型权重不进入 Git 或 Worker 镜像。
- Backend、Worker 和 DCGM Exporter 指标由 Prometheus 采集，并通过 Grafana Dashboard 展示应用、推理和 GPU 状态。
- GitHub Actions 执行前后端测试、Frontend 构建、Helm/Kubernetes 清单校验和容器构建检查；独立发布工作流负责向 GHCR 发布三个镜像，不执行集群部署。

## 云上验证

仓库中的 [云上验证记录](cloud-validation.md)保存了单 NVIDIA T4、单 Worker 环境的测试结论。完成 Backend 异步调用和 Worker 探针调整后，100 个 Locust 用户持续运行 4 分钟，共完成 2615 次真实 GPU 推理请求，失败数为 0，吞吐为 10.52 req/s，Backend 和 Worker 均未重启。

该结果只对应记录中的输入、模型和单 GPU 环境，不代表多 GPU、任务队列或其他负载条件。

## 最小部署入口

集群需先具备 NVIDIA Device Plugin；启用默认 ServiceMonitor 时，还需先安装 Prometheus Operator CRD。完整准备步骤见 [根 README 的 GPU 云服务器部署说明](../README.md#gpu-云服务器部署)。

```bash
helm upgrade --install structvision ./helm \
  --namespace structvision \
  --create-namespace \
  --values helm/values-release.yaml
```

正式配置通过 GHCR repository 和 digest 固定镜像内容。模型 repository、revision、文件名和 SHA256 记录在 [`model/manifest.yaml`](../model/manifest.yaml)。

## 已知限制

- 当前部署面向单 GPU、单 Worker，Worker 更新使用 `Recreate`，更新时会有短暂中断。
- `/predict` 是等待推理完成后返回的请求/响应接口，没有任务队列、持久化状态或进度查询。
- Backend 使用 Pod 临时目录保存上传文件和结果图，Pod 重建后不会保留。
- Worker 首次请求时加载模型，正式测试前需要预热。
- T4 真实推理已经通过，但模型 manifest 仍只静态记录 `sm_86`，尚未保存 Detectron2 wheel 的完整 fatbin 架构清单。
