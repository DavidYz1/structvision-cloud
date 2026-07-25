# GPU 推理压测

本目录使用 Locust 模拟浏览器向 `POST /api/predict` 上传图片，只压测经过 Frontend Nginx 转发到 Backend、再调用 GPU Worker 的真实推理链路。脚本不会请求首页、静态资源、健康检查或结果图片。

## 准备

使用 Python 3.10 或更高版本，在独立虚拟环境中安装压测依赖：

```bash
python -m pip install -r tests/load/requirements.txt
```

准备一张有代表性的结构病害图片，放在仓库之外。图片路径必须通过 `LOCUST_IMAGE_PATH` 传入；脚本未设置默认图片或默认 Host。建议始终使用绝对路径：

```bash
export LOCUST_IMAGE_PATH=/绝对路径/测试图片.jpg
```

脚本加载时会检查变量是否存在、路径是否指向普通文件以及文件是否可读。检查失败会在产生压测流量前终止。每个虚拟用户启动时读取一次图片并复用其内容，但每次请求都会重新构造字段名为 `file` 的 `multipart/form-data`。

## 先预热

正式计时前先用同一张图片完成一次请求，使 Worker 加载模型并确认端到端接口成功：

```bash
curl --fail-with-body \
  --max-time 120 \
  --form "file=@${LOCUST_IMAGE_PATH}" \
  http://119.28.156.57/api/predict
```

预热成功应返回 HTTP 200、`Content-Type: application/json`，且 JSON 中的 `status` 为 `success`。预热不计入两轮 Locust 结果。

## 观察服务器

压测期间在云服务器的独立终端观察 GPU：

```bash
nvidia-smi \
  --query-gpu=timestamp,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw \
  --format=csv \
  -l 1
```

同时观察 Pod 状态和重启次数：

```bash
watch -n 2 kubectl get pods -n structvision
```

## 第一轮：30 用户快速爬坡

```bash
mkdir -p tests/load/results

LOCUST_IMAGE_PATH=/绝对路径/测试图片.jpg \
locust -f tests/load/locustfile.py \
  --host http://119.28.156.57 \
  --headless \
  --users 30 \
  --spawn-rate 1 \
  --run-time 4m \
  --csv tests/load/results/t4-ramp30 \
  --csv-full-history \
  --html tests/load/results/t4-ramp30.html
```

只有在 Locust 没有明显失败、Pod 没有重启或异常，且吞吐尚未形成明显平台时，才继续第二轮。出现持续错误、OOM、Pod 重启或服务不可用时应停止测试并先排查。

## 第二轮：50 用户

```bash
LOCUST_IMAGE_PATH=/绝对路径/测试图片.jpg \
locust -f tests/load/locustfile.py \
  --host http://119.28.156.57 \
  --headless \
  --users 50 \
  --spawn-rate 1 \
  --run-time 5m \
  --csv tests/load/results/t4-ramp50 \
  --csv-full-history \
  --html tests/load/results/t4-ramp50.html
```

`--host` 是唯一的目标主机来源；Python 文件中没有公网 IP。Locust 统计中的所有请求统一显示为 `GPU inference`。单次请求超时为 120 秒，用户完成一次推理后立即发起下一次请求。

CSV、历史数据和 HTML 报告均写入 `tests/load/results/`，该目录内容不会进入 Git。
