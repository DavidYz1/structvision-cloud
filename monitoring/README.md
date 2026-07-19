# StructVision Cloud 可观测性

## 架构概览

StructVision Cloud 的可观测性链路由两部分组成：

```text
Backend / GPU Worker ServiceMonitor ─┐
                                    ├─> Prometheus ─> Grafana
节点级 DCGM Exporter ServiceMonitor ─┘
```

- `kube-prometheus-stack` 在 `monitoring` 命名空间中提供 Prometheus Operator、Prometheus、Grafana、kube-state-metrics 和 node-exporter。
- Backend 与 GPU Worker 通过各自的 `/metrics` 暴露应用指标，并由应用 Chart 中的 ServiceMonitor 交给 Prometheus Operator 自动发现。
- NVIDIA DCGM Exporter 以节点级 DaemonSet 运行，通过端口 `9400` 暴露 `DCGM_*` GPU 遥测指标，例如 GPU 利用率、显存使用量和温度。
- DCGM Exporter 不申请 `nvidia.com/gpu`，因此不会占用单节点集群中留给 `mamt2-worker` 的唯一可调度 GPU resource。

## 配置文件

- `kube-prometheus-stack-values.yaml`：本地单节点 Minikube 的轻量 Prometheus/Grafana 配置。
- `dcgm-exporter-values.yaml`：NVIDIA DCGM Exporter 的 Service、ServiceMonitor、资源限制和低基数 Pod label allowlist。
- `../helm/dashboards/structvision-overview.json`：由应用 Helm Chart 声明式发布的 StructVision 总览 Dashboard。

## 安装

以下命令仅作为操作文档。本次变更不会执行这些命令。

安装或更新 kube-prometheus-stack：

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  --values monitoring/kube-prometheus-stack-values.yaml
```

安装或更新官方 NVIDIA DCGM Exporter：

```bash
helm repo add nvidia https://nvidia.github.io/dcgm-exporter/helm-charts
helm repo update
helm upgrade --install dcgm-exporter nvidia/dcgm-exporter \
  --namespace monitoring \
  --create-namespace \
  --values monitoring/dcgm-exporter-values.yaml
```

## Dashboard 声明式加载

应用 Helm Chart 使用 `helm/templates/grafana-dashboard-configmap.yaml` 将
`helm/dashboards/structvision-overview.json` 封装为 `mamt2` 命名空间中的
`structvision-grafana-dashboard` ConfigMap。ConfigMap 带有
`grafana_dashboard: "1"` 标签，Grafana Dashboard Sidecar 跨 Namespace
发现该标签后，会自动把 JSON 加载到 Grafana。Dashboard 内容变化也会更新
ConfigMap 的 `checksum/dashboard` annotation。

Dashboard 标识：

- 标题：`StructVision Cloud Overview`
- UID：`structvision-cloud-overview`
- 数据源 UID：`prometheus`

通过现有应用 Helm Release 发布或更新 Dashboard：

```bash
helm upgrade --install mamt2 ./helm \
  --namespace mamt2 \
  --create-namespace
```

如需暂时停止声明式加载，可在发布时设置：

```bash
helm upgrade --install mamt2 ./helm \
  --namespace mamt2 \
  --set monitoring.grafanaDashboard.enabled=false
```

## 验证

检查 DaemonSet Pod 是否在 Minikube 节点上运行：

```bash
kubectl get pods --namespace monitoring \
  --selector app.kubernetes.io/name=dcgm-exporter \
  --output wide
```

检查 Service 和 ServiceMonitor：

```bash
kubectl get service --namespace monitoring dcgm-exporter
kubectl get servicemonitor --namespace monitoring dcgm-exporter --output yaml
```

直接检查 DCGM Exporter 的 `/metrics`：

```bash
kubectl port-forward --namespace monitoring service/dcgm-exporter 9400:9400
curl --fail http://127.0.0.1:9400/metrics | grep '^DCGM_'
```

检查 Prometheus 是否发现并成功抓取 target：

```bash
kubectl port-forward --namespace monitoring \
  service/kube-prometheus-stack-prometheus 9090:9090

curl --get http://127.0.0.1:9090/api/v1/query \
  --data-urlencode 'query=up{job=~".*dcgm-exporter.*"}'
```

可在 Prometheus UI 中执行以下基础查询：

```promql
up{job=~".*dcgm-exporter.*"}
DCGM_FI_DEV_GPU_UTIL
DCGM_FI_DEV_FB_USED
DCGM_FI_DEV_GPU_TEMP
```

应用指标可继续通过以下查询检查：

```promql
structvision_backend_http_requests_total
structvision_worker_inference_requests_total
```

检查 Dashboard ConfigMap 及内嵌 JSON：

```bash
kubectl get configmap structvision-grafana-dashboard \
  --namespace mamt2 \
  --output yaml

kubectl get configmap structvision-grafana-dashboard \
  --namespace mamt2 \
  --output jsonpath='{.data.structvision-overview\.json}'
```

检查 Grafana Dashboard Sidecar 是否发现并加载 ConfigMap：

```bash
kubectl logs --namespace monitoring \
  --selector app.kubernetes.io/name=grafana \
  --container grafana-sc-dashboard \
  --tail 100
```

Dashboard 使用的主要 PromQL 包括：

- `up{namespace="mamt2",service="backend"}`、`up{namespace="mamt2",service="mamt2-worker"}` 和 DCGM Exporter 的 `up`：采集目标状态。
- `increase(structvision_backend_worker_calls_total[$__range])`：Backend 到 Worker 的调用结果。
- `increase(structvision_worker_inference_requests_total[$__range])`：推理请求结果及成功率。
- `rate(structvision_backend_http_requests_total[$__rate_interval])`：按 route 和 HTTP status 展示请求速率。
- `histogram_quantile(...)`：Backend 到 Worker、Worker 推理的 P50/P95/P99 延迟。
- `structvision_worker_model_load_duration_seconds_sum/count`：平均模型加载耗时。
- `structvision_worker_detected_instances_sum/count`：检测实例总量和每次推理平均值。
- `DCGM_FI_DEV_GPU_UTIL`、`DCGM_FI_DEV_FB_USED`、`DCGM_FI_DEV_GPU_TEMP`、`DCGM_FI_DEV_POWER_USAGE`、`DCGM_FI_DEV_MEM_COPY_UTIL`：GPU 利用率、显存、温度、功耗和显存拷贝利用率。

## 卸载

只卸载 DCGM Exporter：

```bash
helm uninstall dcgm-exporter --namespace monitoring
```

如需同时移除整个监控栈：

```bash
helm uninstall kube-prometheus-stack --namespace monitoring
```
