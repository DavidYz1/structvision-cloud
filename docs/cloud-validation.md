# 云上验证记录

本页记录 StructVision Cloud 在单节点、单 NVIDIA T4 GPU 环境中的部署和压测过程。应用 Helm Release 为 `structvision`，Namespace 为 `structvision`。原始 Locust CSV、HTML 和服务器日志不提交到 Git，只保留结论、故障依据和对应修改。

## 验证范围

- 公开 GHCR 镜像通过 digest 部署；
- NVIDIA Device Plugin 能向 Kubernetes 公开 `nvidia.com/gpu`；
- Worker 能在 T4 上加载 Detectron2/MAMT2 并执行真实图片推理；
- Init Container 能下载固定 Hugging Face revision、校验 SHA256 并复用 PVC；
- Backend、Worker、Prometheus、Grafana 和 DCGM Exporter 能按当前配置运行；
- Locust 只请求 `POST /api/predict`，不请求首页、健康检查或静态资源。

压测脚本和运行参数见 [GPU 推理压测](../tests/load/README.md)。

## 首轮 100 用户压测

首轮持续压测出现 369 次 Nginx 502，Backend 累计重启 10 次。Kubernetes Events 中可以看到 Liveness Probe failed，Nginx 日志对应 `connection refused`。

代码检查确认，当时 Backend 的异步 `/predict` 路由内部使用同步 `requests` 调用 Worker。真实推理等待期间会阻塞 Uvicorn 事件循环，Backend 的健康端点也无法及时响应。处理方式是：

1. 用 FastAPI lifespan 管理并复用 `httpx.AsyncClient`；
2. Backend 到 Worker 的文件上传改为异步调用，保留 120 秒超时；
3. 增加不访问 Worker 的 `/healthz` 和 `/readyz`；
4. Backend liveness 使用 `/healthz`，readiness 使用 `/readyz`。

测试补充了异步成功、Worker 超时、连接失败、非 2xx，以及推理等待期间健康端点仍能响应的场景。

## Worker 探针调整

Backend 修复后继续压测时，Worker 的 HTTP readiness/liveness 仍会与真实 GPU 推理争用服务响应时间。探针超时会把正在工作的 Worker 判断为失活，重启后又会产生短暂的上游连接失败。

云端先通过补丁验证以下配置，再写回 Helm 与原生 Kubernetes 清单：

- startupProbe：HTTP `GET /healthz`，给模型服务启动保留 300 秒窗口；
- readinessProbe：TCP 端口 `http`，`periodSeconds: 5`、`timeoutSeconds: 2`、`failureThreshold: 3`；
- livenessProbe：TCP 端口 `http`，`periodSeconds: 10`、`timeoutSeconds: 2`、`failureThreshold: 6`。

TCP 探针检查 Worker 是否仍在监听端口，不再要求繁忙的推理服务及时处理额外 HTTP 请求。startupProbe 保留 HTTP 检查，仍能在初次启动时确认应用端点可用。

## 最终结果

完成 Backend 异步调用和 Worker TCP 探针调整后，再次运行 100 用户、4 分钟真实 GPU 推理：

| 指标 | 结果 |
| --- | ---: |
| 完成请求 | 2615 |
| 失败请求 | 0 |
| 吞吐 | 10.52 req/s |
| 平均响应时间 | 9.15 s |
| P95 | 9.8 s |
| P99 | 9.8 s |
| Backend 重启 | 0 |
| Worker 重启 | 0 |

这轮结果说明当前单 Worker、单 T4 配置能够稳定处理该测试负载。它不代表多 GPU、HPA、任务队列或更大输入图片下的性能。

## 仍需补充的构建记录

T4 真实推理已经验证成功，但 `model/manifest.yaml` 和 Worker layout 测试目前只记录 `sm_86`。仓库尚未保存 Detectron2 wheel 的完整 fatbin 架构列表，因此不能仅根据运行结果写成 wheel 已静态确认同时包含 `sm_75` 和 `sm_86`。后续重新构建 wheel 时，应把构建命令和 `cuobjdump` 输出一并保存到产物清单。
