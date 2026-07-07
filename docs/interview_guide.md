# MAMT2 Cloud SHM 面试答辩指南

本文档用于未来面试、项目答辩、简历项目讲解和复习。它会详细解释 MAMT2 Cloud SHM 的设计思路、运行流程、Docker Compose 链路、API 链路、常见问题和标准回答。

## 1. 项目一句话介绍

我把一个原本本地运行的 MAMT2 / Detectron2 结构表观病害实例分割模型，封装成了一个前端可交互、后端可调用、Worker 独立推理，并且支持 Docker Compose 部署的云原生 AI 推理平台。

更正式一点可以说：

> MAMT2 Cloud SHM 是一个面向结构健康监测场景的云原生 AI 推理展示项目，它将真实的 MAMT2 / Detectron2 / Mask R-CNN 病害实例分割能力，工程化封装为 React 前端、FastAPI 后端、独立推理 Worker 和 Docker Compose 轻量部署链路。

## 2. 项目背景：为什么要做这个项目？

原始 MAMT2 / Detectron2 模型更偏科研脚本形态，通常是在本地命令行中读取图片、加载 config 和权重、执行推理，再把结果保存到本地目录。这种方式适合实验复现，但不适合面试展示、用户交互或云原生部署。

我做这个项目的动机主要有四点：

1. **把科研模型工程化**：不只是跑通模型脚本，而是把模型变成一个可以通过 HTTP 调用的推理服务。
2. **做成可展示的产品形态**：前端可以上传图片、查看原图、结果图、类别、置信度、bbox、mask 和原始 JSON。
3. **服务拆分，便于扩展**：前端、后端 API 和模型 Worker 分离，后续可以独立扩容、独立部署、独立维护。
4. **面向结构健康监测场景**：项目场景是结构表观病害识别，适合桥梁、混凝土结构、建筑表面缺陷检测等 SHM 方向展示。

一句话总结：这个项目的重点不是“又写了一个网页 Demo”，而是把真实深度学习模型从本地脚本推进到可访问、可部署、可扩展的 AI 推理服务。

## 3. 原始模型是什么？

项目接入的是 MAMT2 / Detectron2 / Mask R-CNN 相关的真实结构表观病害实例分割模型。

从工程接入角度看，可以这样理解：

- **MAMT2**：原始研究项目中的模型体系，本项目接入的是其中用于结构表观病害定位与分割的真实推理能力。
- **Detectron2**：Meta 开源的目标检测与实例分割框架，本项目的模型加载、推理和可视化依赖 Detectron2。
- **Mask R-CNN**：实例分割模型框架，可以同时输出目标类别、置信度、bbox 和 mask。
- **instance segmentation**：实例分割，不只是判断图片里有没有病害，也会输出每个病害实例的位置框和掩膜轮廓。

当前推理输出包括：

```text
boxes: [[x1, y1, x2, y2]]
labels: ["spalling"]
scores: [0.92]
masks: polygon points
result_image: 带 bbox/mask 的结果图
```

注意：如果没有足够论文细节支撑，面试中不要过度展开 MAMT2 原理论文细节。这个项目重点讲“真实模型的工程化接入、服务化、容器化和后续云原生演进”。

## 4. 总体架构

当前已经跑通的真实推理链路如下：

```text
浏览器
  ↓
frontend 容器：React/Vite build 产物 + Nginx
  ↓ POST /api/predict
Nginx 反向代理：/api/* -> backend:8000/*
  ↓
backend 容器：FastAPI 业务 API
  ↓ POST http://host.docker.internal:9000/predict-file
宿主机 Worker：FastAPI + MAMT2 / Detectron2 / Mask R-CNN
  ↓
真实模型推理
  ↓
返回 result_image、bbox、mask、labels、scores
  ↓
前端展示
```

每一层职责如下。

### frontend

前端负责用户交互，包括：

- 上传图片
- 展示原始图片
- 展示推理结果图
- 展示类别、置信度、状态、输入文件名
- 折叠展示原始 JSON，方便调试

前端不直接接触模型，也不直接请求 Worker。

### Nginx

Nginx 在 frontend 容器中做两件事：

1. 托管 React/Vite build 后的静态页面。
2. 把 `/api/*` 请求反向代理到 `backend:8000/*`。

这样浏览器只需要访问 `http://localhost:5173`，不需要知道 backend 容器的内部地址。

### backend

backend 是统一 API 层，负责：

- 接收前端上传的图片文件
- 保存上传图片
- 根据 `USE_REAL_MAMT2` 判断使用 mock 还是真实 Worker
- 调用 Worker 的 `/predict-file`
- 保存 Worker 返回的结果图
- 返回前端需要的数据结构

当前 backend 提供：

```text
GET  /
POST /predict
GET  /results/{filename}
```

### worker

Worker 是独立的模型推理服务，负责：

- 加载真实 MAMT2 / Detectron2 模型
- 接收图片文件或本地图片路径
- 执行真实推理
- 生成 bbox、mask、labels、scores
- 生成带可视化标注的结果图
- 返回 JSON 结果

当前 Worker 暂时未容器化，仍运行在 Windows 宿主机 `General` conda 环境中。

### Docker Compose

Docker Compose 当前负责管理 frontend 和 backend 两个容器：

- 构建 frontend 镜像
- 构建 backend 镜像
- 创建内部网络
- 注入环境变量
- 映射端口
- 启动服务

Worker 暂时作为宿主机外部服务存在。

## 5. 为什么要拆成 frontend / backend / worker？

面试中可以这样回答：

我没有把模型直接塞进后端，而是拆成 frontend、backend 和 worker，是为了让系统更接近真实工程架构。

- 前端只负责交互，不直接接触模型服务，避免把模型地址、推理逻辑暴露给浏览器。
- backend 作为统一 API 层，后续可以扩展鉴权、日志、任务记录、限流、异步队列、结果持久化等能力。
- worker 专注模型推理。模型依赖重、启动慢、推理耗时长，未来可能需要 GPU，把它拆出来后可以单独部署到 GPU 节点，也可以独立扩缩容。
- 服务拆分后，frontend/backend 可以先轻量容器化，worker 后续再单独处理 PyTorch、Detectron2 和 CUDA 依赖。

这一步体现的是从科研脚本到工程化 AI 服务的关键转变。

## 6. 当前 API 链路详解

当前 Docker Compose 轻量真实模式下，请求路径是：

```text
前端请求：POST /api/predict
Nginx 代理：/api/predict -> backend:8000/predict
Backend 路由：@app.post("/predict")
Backend 调用 Worker：POST {MAMT2_WORKER_URL}/predict-file
当前环境变量：
  USE_REAL_MAMT2=true
  MAMT2_WORKER_URL=http://host.docker.internal:9000
```

### 为什么前端不直接请求 Worker？

因为 Worker 是模型推理服务，不应该直接暴露给浏览器。前端直接请求 Worker 会带来几个问题：

- 浏览器跨域问题更复杂
- Worker 地址会暴露给用户
- 后续鉴权、日志、任务记录不好统一管理
- 未来切换 Worker 部署位置时需要改前端

所以前端统一请求 backend，backend 再决定如何调 Worker。

### 为什么 backend 调用 `/predict-file`？

早期本地调试时可以传 `image_path`，但 Docker/K8s 中容器文件系统隔离，backend 容器里的本地路径对 Worker 不一定可见。因此更合理的方式是：backend 把图片作为 multipart 文件上传给 Worker。

这就是 `/predict-file` 的作用。它更适合容器化和云原生环境。

### 为什么用 `host.docker.internal`？

backend 运行在容器里，而 Worker 运行在 Windows 宿主机上。容器里的 `127.0.0.1` 指向容器自己，不是宿主机。

所以 backend 容器要访问宿主机 Worker，需要使用：

```text
http://host.docker.internal:9000
```

在 `docker-compose.yml` 中也配置了：

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

这样 Linux 容器中也能解析这个地址。

## 7. 端口和网络解释

当前端口如下：

```text
frontend: "5173:80"
backend:  "8000:8000"
worker:   宿主机 9000
```

含义是：

- 访问 `http://localhost:5173`，实际进入 frontend 容器的 80 端口。
- 访问 `http://localhost:8000`，实际进入 backend 容器的 8000 端口。
- Worker 运行在宿主机，监听 `127.0.0.1:9000`。

在 Compose 内部网络中，frontend 容器可以通过服务名访问 backend：

```text
http://backend:8000
```

但浏览器不在 Docker 内部网络里，所以浏览器不能访问 `backend:8000`。浏览器只访问 Nginx 暴露出来的 `localhost:5173`，再由 Nginx 代理 `/api/` 请求。

backend 容器访问宿主机 Worker 时，不能用 `127.0.0.1:9000`，因为那会指向 backend 容器自己。它必须用：

```text
host.docker.internal:9000
```

## 8. Docker Compose 在项目中的作用

执行：

```bash
docker compose up --build
```

主要做了这些事：

1. 读取 `docker-compose.yml`。
2. 根据 `backend/Dockerfile` 构建 backend 镜像。
3. 根据 `frontend/Dockerfile` 构建 frontend 镜像。
4. 创建 Compose 内部网络。
5. 创建并启动 backend/frontend 容器。
6. 做端口映射，例如 `5173:80`、`8000:8000`。
7. 给 backend 注入环境变量，例如 `USE_REAL_MAMT2=true` 和 `MAMT2_WORKER_URL=http://host.docker.internal:9000`。

常用命令：

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose down
docker compose down --remove-orphans
```

## 9. 当前三种运行方式

### 9.1 Mock 模式

用途：不用真实模型，只测试页面和 API。

```bash
conda activate mamt2-api
cd /d/pythonproject/mamt2-cloud-shm
bash scripts/start_backend_mock.sh
```

前端本地开发：

```bash
cd frontend
npm run dev
```

### 9.2 本地真实 Worker 模式

不使用 Docker，全部在宿主机本地跑。

终端 1：

```bash
conda activate General
cd /d/pythonproject/mamt2-cloud-shm
bash scripts/start_worker.sh
```

终端 2：

```bash
conda activate mamt2-api
cd /d/pythonproject/mamt2-cloud-shm
bash scripts/start_backend_real.sh
```

终端 3：

```bash
cd /d/pythonproject/mamt2-cloud-shm/frontend
npm run dev
```

### 9.3 Docker Compose 轻量真实模式

这是当前已经跑通的真实推理链路。

终端 1：

```bash
conda activate General
cd /d/pythonproject/mamt2-cloud-shm
bash scripts/start_worker.sh
```

终端 2：

```bash
cd /d/pythonproject/mamt2-cloud-shm
docker compose up --build
```

浏览器访问：

```text
http://localhost:5173
```

强调：当前 Worker 暂未容器化，frontend/backend 已通过 Docker Compose 容器化。

## 10. 当前版本完成情况

- [x] React/Vite 前端
- [x] FastAPI backend
- [x] mock 推理
- [x] 真实 MAMT2 Worker
- [x] backend 调用 Worker `/predict-file`
- [x] 前端展示真实推理结果
- [x] frontend/backend Dockerfile
- [x] `docker-compose.yml`
- [x] Nginx `/api` 反向代理
- [x] Docker Compose 轻量真实模式跑通
- [ ] Worker 容器化
- [ ] K8s 部署
- [ ] Redis 异步队列
- [ ] MinIO 对象存储
- [ ] Prometheus/Grafana 监控

## 11. 项目中遇到的关键问题和解决方案

### 11.1 Docker Desktop 没有启动

现象：

```text
failed to connect to docker API at npipe...
```

原因是 Docker Desktop 没有启动，或者 Docker Engine 还没有 ready。

解决：启动 Docker Desktop，等待 Linux Engine 运行后再执行 Docker 命令。

### 11.2 Docker Hub 镜像拉取失败

现象：

```text
failed to fetch oauth token
```

原因通常是网络或代理问题。

解决：在 Docker Desktop 中配置 HTTP/HTTPS proxy，例如使用本机代理地址，具体端口根据本机代理软件确定。

### 11.3 `docker pull` 成功但 `docker compose build` 失败

`docker pull` 和 BuildKit 构建链路不完全一样，BuildKit 在构建阶段可能仍受代理、DNS 或认证链路影响。

解决方向：

- 检查 Docker Desktop 代理是否对 BuildKit 生效。
- 尝试重启 Docker Desktop。
- 必要时预先 pull 基础镜像。

### 11.4 `nginx.conf` 带 UTF-8 BOM 导致 frontend 启动失败

现象：

```text
unknown directive "﻿server"
```

原因是 `nginx.conf` 文件开头有 UTF-8 BOM。Nginx 会把 `server` 识别成带隐藏字符的指令。

解决：统一保存为 UTF-8 无 BOM。项目已添加 `.editorconfig`，并对关键 Docker / Nginx / YAML 文件做过 BOM 检查。

### 11.5 `POST /api/predict 405 Method Not Allowed`

原因通常是前端请求路径、Nginx 代理和 backend 路由不一致。

当前正确关系是：

```text
前端：POST /api/predict
Nginx：/api/* -> backend:8000/*
后端：POST /predict
```

如果 `/api/` 没有被 Nginx 代理，Nginx 会把 POST 当成静态资源请求，从而返回 405。

### 11.6 Git Bash 中 `docker compose exec` 的 TTY 问题

现象：

```text
cannot attach stdin to a TTY-enabled container
```

解决：加 `-T`，例如：

```bash
docker compose exec -T backend sh
```

## 12. 面试常见追问与回答

### Q1：这个项目和普通 Web Demo 有什么区别？

A：普通 Demo 通常只是网页调用一个本地脚本，而这个项目完成了模型服务化、API 封装、服务拆分、Docker Compose 容器化、Nginx 反向代理和后续 K8s 扩展设计。它不是单纯展示页面，而是把真实 MAMT2 / Detectron2 模型接入到一个可部署的 AI 推理链路中。

### Q2：为什么不直接把模型代码放 backend？

A：模型依赖很重，涉及 PyTorch、Detectron2、OpenCV、timm 等，推理耗时也更长，未来可能需要 GPU。拆成 Worker 后，模型服务可以独立部署、独立扩缩容、独立维护，也便于后续迁移到 GPU Pod。

### Q3：为什么 Worker 暂时不容器化？

A：Detectron2 / PyTorch / CUDA 依赖比较复杂。第一阶段目标是先把真实模型服务化，并跑通 frontend/backend 容器链路。下一阶段再专门处理 GPU 镜像、CUDA Runtime、Detectron2 编译或预编译安装等问题。

### Q4：为什么用 `host.docker.internal`？

A：backend 在容器中运行，容器内的 `127.0.0.1` 指向容器自己，不是 Windows 宿主机。Worker 现在运行在宿主机 9000 端口，所以 backend 容器要通过 `host.docker.internal:9000` 访问它。

### Q5：Docker Compose 体现在哪里？

A：frontend 和 backend 分别构建镜像，`docker-compose.yml` 统一管理构建、容器启动、端口映射、环境变量和内部网络。通过 `docker compose up --build` 可以一键启动前后端容器。

### Q6：以后怎么迁移 K8s？

A：第一步把 frontend/backend 写成 Deployment 和 Service，用 ConfigMap 注入 `MAMT2_WORKER_URL`。Worker 初期可以作为外部服务，后续容器化后作为 GPU Worker Deployment，再通过 Service 暴露给 backend。

### Q7：为什么前端请求 `/api/predict`，而不是直接请求 `backend:8000`？

A：浏览器不在 Docker 内部网络里，不能解析 Compose 服务名 `backend`。同时 `/api` 代理可以隐藏后端地址，未来迁移到 K8s Ingress 时前端代码也不用改。

### Q8：如果请求变慢怎么办？

A：当前是同步推理。后续可以引入 Redis 任务队列，backend 只创建任务，worker 异步消费任务，前端轮询任务状态或用 WebSocket 接收结果更新。

### Q9：这个项目能体现云原生吗？

A：当前体现了服务拆分、容器化、反向代理、环境变量配置和 Docker Compose 编排。后续会迁移到 K8s，用 Deployment、Service、ConfigMap、Ingress 和监控组件完善云原生部署。

## 13. 30 秒讲解稿

这个项目是我把结构表观病害识别的 MAMT2 / Detectron2 模型做成云原生推理服务的实践。前端用 React/Vite 实现图片上传和结果展示，部署时由 Nginx 托管静态页面并代理 `/api` 请求；后端用 FastAPI 作为统一 API 层，接收图片后通过文件上传方式调用独立的 MAMT2 Worker；Worker 运行真实 Detectron2 / Mask R-CNN 模型，返回 bbox、mask、类别、置信度和结果图。当前 frontend/backend 已经通过 Docker Compose 容器化，Worker 暂时运行在宿主机 General 环境中，完整真实推理链路已经跑通。后续计划是迁移到 K8s，并逐步做 Worker 容器化、异步任务队列和监控。

## 14. 后续路线图

- **v0.1**：Docker Compose 轻量真实推理版，已完成。frontend/backend 容器化，Worker 在宿主机运行。
- **v0.2**：K8s 轻量版。frontend/backend 部署到 minikube，Worker 作为外部服务。
- **v0.3**：Worker 容器化。解决 Detectron2 / PyTorch / CUDA 依赖，形成独立 GPU Worker 镜像。
- **v0.4**：异步任务版。引入 Redis、MinIO、MySQL，支持任务队列、结果存储和历史记录。
- **v0.5**：监控版。引入 Prometheus / Grafana，监控 API、Worker、任务耗时和资源使用。