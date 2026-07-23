# GHCR 镜像发布

本页描述 v0.9.0 的镜像发布机制。仓库中的工作流和文档变更本身不会发布镜像；只有合并到 `main` 后人工运行发布工作流，或推送符合要求的版本标签，才会写入 GHCR。

## 镜像与构建入口

| 组件 | GHCR 镜像 | Context | Dockerfile | 平台 |
| --- | --- | --- | --- | --- |
| Frontend | `ghcr.io/davidyz1/structvision-frontend` | `frontend` | `frontend/Dockerfile` | `linux/amd64` |
| Backend | `ghcr.io/davidyz1/structvision-backend` | `backend` | `backend/Dockerfile` | `linux/amd64` |
| Worker | `ghcr.io/davidyz1/structvision-worker` | 仓库根目录 | `worker/Dockerfile.hf` | `linux/amd64` |

Worker 镜像不包含模型权重。运行时仍由 Kubernetes initContainer 从固定 Hugging Face repo/revision 下载固定文件，校验 SHA256 后写入 PVC。

## 两种发布方式

### 人工候选发布

在 GitHub Actions 中选择 `Publish GHCR images` → `Run workflow`，并选择 `main`。来源守卫会拒绝其他 branch 或 tag 上的人工运行。

三个镜像只发布一个完整提交标签：

```text
sha-<40 位 Git commit SHA>
```

该方式适合在创建版本标签前验证完整构建、GHCR 权限和干净环境拉取。

### 版本标签发布

推送严格匹配 `v<major>.<minor>.<patch>` 的标签，例如 `v0.9.0`，且标签指向的提交已经合并到 `main` 时，每个镜像同时发布：

```text
v0.9.0
sha-<40 位 Git commit SHA>
```

不要在人工候选发布、包可见性检查和干净环境验证完成前创建 `v0.9.0`。发布失败时先修复工作流、权限或构建问题，不要移动或重复创建正式版本标签来试错。

工作流不接受用户输入的镜像标签，也不发布 `latest`。

## 权限与包可见性

工作流默认只有 `contents: read`。只有实际构建和推送三个镜像的 matrix job 获得 `packages: write`，并使用仓库运行时自动提供的 `GITHUB_TOKEN` 登录 `ghcr.io`；不需要 PAT 或新增 Secret。

首次成功发布后：

1. 打开仓库页面右侧的 **Packages**，或访问 `DavidYz1` 账户的 Packages 页面；
2. 分别进入 `structvision-frontend`、`structvision-backend`、`structvision-worker`；
3. 检查包是否已关联当前仓库；
4. 如包仍为 private，在每个包的 **Package settings** 中确认后改为 public。

GHCR 包首次发布时默认可能是 private。三个包都必须单独确认；包设为 public 后，干净环境可以匿名执行 `docker pull`。GitHub 当前不允许把已经公开的包重新改回 private，因此变更可见性前应再次核对包名和内容。

GitHub 官方说明：

- [Container registry 使用说明](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [包访问控制和可见性](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility)

## Tag 与 digest

发布完成后，每个 matrix job 都会：

1. 读取 `docker/build-push-action` 返回的 registry digest；
2. 要求 digest 匹配 `sha256:<64 位十六进制>`；
3. 执行 `docker buildx imagetools inspect <image>@<digest>`，确认远程内容存在；
4. 将镜像名、Git commit、所有 tag 和 digest 写入 Job Summary。

`sha-<commit>` 是便于人识别源码来源的可变 registry tag；`sha256:<...>` 才是不可变镜像内容标识。需要复现或部署时，从 Job Summary 复制完整引用：

```text
ghcr.io/davidyz1/structvision-frontend@sha256:<digest>
ghcr.io/davidyz1/structvision-backend@sha256:<digest>
ghcr.io/davidyz1/structvision-worker@sha256:<digest>
```

下一阶段修改 Helm 镜像配置时，应为三个组件使用 `repository + digest`，而不是依赖 `latest` 或仅依赖版本 tag。当前阶段不修改 Helm values、原生 Kubernetes 清单或集群。

## 发布 Action 来源

发布工作流只使用固定到完整 commit SHA 的 Action：

| Action | 发布版本 | 固定 commit SHA |
| --- | --- | --- |
| `actions/checkout` | v4（复用现有 CI） | `11d5960a326750d5838078e36cf38b85af677262` |
| `docker/login-action` | v4.0.0 | `b45d80f862d83dbcd57f89517bcf500b2ab88fb2` |
| `docker/setup-buildx-action` | v4.0.0 | `4d04d5d9486b7bd6fa91e7baf45bbb4f8b9deedd` |
| `docker/build-push-action` | v7.2.0 | `f9f3042f7e2789586610d6e8b85c8f03e5195baf` |

Docker Action SHA 来自各官方 GitHub 仓库对应 release tag，并由 `git ls-remote` 再次核对。
