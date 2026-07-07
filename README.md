# MAMT2 Cloud SHM

MAMT2 Cloud SHM 鏄竴涓潰鍚戠粨鏋勮〃瑙傜梾瀹虫娴嬩笌瀹炰緥鍒嗗壊鐨勪簯鍘熺敓灞曠ず椤圭洰銆傞」鐩洰鏍囨槸鎶婄湡瀹炵殑 MAMT2 / Detectron2 / Mask R-CNN 妯″瀷灏佽涓哄墠绔€佸悗绔?API銆佹ā鍨?Worker 涓?Docker/K8s 鏂瑰悜鐨勫畬鏁村伐绋嬮摼璺紝渚夸簬婕旂ず銆佸氨涓氬睍绀哄拰鍚庣画绛旇京璇存槑銆?
褰撳墠宸茬粡璺戦€氱殑閲嶇偣閾捐矾鏄細React/Vite 鍓嶇瀹瑰櫒閫氳繃 Nginx 浠ｇ悊璇锋眰 FastAPI 鍚庣瀹瑰櫒锛屽悗绔啀閫氳繃 HTTP 鏂囦欢涓婁紶璋冪敤杩愯鍦?Windows 瀹夸富鏈?`General` conda 鐜涓殑 MAMT2 Worker锛屾渶缁堝畬鎴愮湡瀹?Detectron2 / MAMT2 / Mask R-CNN 鎺ㄧ悊锛屽苟杩斿洖缁撴灉鍥俱€乥box銆乵ask銆佺被鍒拰缃俊搴︺€?
## 褰撳墠鏋舵瀯

```text
娴忚鍣?  -> frontend 瀹瑰櫒锛歊eact/Vite build 浜х墿 + Nginx
  -> POST /api/predict
  -> backend 瀹瑰櫒锛欶astAPI
  -> POST http://host.docker.internal:9000/predict-file
  -> Windows 瀹夸富鏈?General conda 鐜涓殑 MAMT2 Worker
  -> 鐪熷疄 Detectron2 / MAMT2 / Mask R-CNN 妯″瀷
  -> 杩斿洖缁撴灉鍥俱€乥box銆乵ask銆佺被鍒€佺疆淇″害
  -> 鍓嶇灞曠ず鐪熷疄鎺ㄧ悊缁撴灉
```

褰撳墠 Docker Compose 鍙鍣ㄥ寲浜?`frontend` 鍜?`backend`銆侻AMT2 Worker 鏆傛椂涓嶅鍣ㄥ寲锛屼粛杩愯鍦?Windows 瀹夸富鏈?`General` 鐜涓紝鐩戝惉 `9000` 绔彛銆?
## 鎶€鏈爤

- React / Vite锛氬墠绔氦浜掍笌缁撴灉灞曠ず銆?- Nginx锛氭墭绠″墠绔潤鎬佹枃浠讹紝骞跺皢 `/api/*` 浠ｇ悊鍒板悗绔?API銆?- FastAPI锛氫富鍚庣 API锛岃礋璐ｆ帴鏀朵笂浼犲浘鐗囥€佽皟鐢?Worker銆佽繑鍥炴帹鐞嗙粨鏋溿€?- MAMT2 / Detectron2 / Mask R-CNN锛氱湡瀹炵粨鏋勮〃瑙傜梾瀹冲疄渚嬪垎鍓叉ā鍨嬨€?- Docker / Docker Compose锛氬綋鍓嶇敤浜庡鍣ㄥ寲 frontend 涓?backend銆?- K8s Ready锛氶」鐩粨鏋勫拰鎺ュ彛宸蹭负鍚庣画 Kubernetes 鏀归€犻鐣欑┖闂达紝浣嗗綋鍓嶅皻鏈畬鎴愬叏閲?K8s 閮ㄧ讲銆?
## 鐩綍缁撴瀯

```text
mamt2-cloud-shm/
  frontend/                 # React/Vite 鍓嶇锛孌ocker 涓敱 Nginx 鎵樼
    src/                    # 鍓嶇婧愮爜
    public/                 # 闈欐€佽祫婧愶紝渚嬪 tongji-logo.png
    Dockerfile              # 鍓嶇澶氶樁娈垫瀯寤洪暅鍍?    nginx.conf              # SPA 鍥為€€鍜?/api/ 浠ｇ悊閰嶇疆

  backend/                  # FastAPI 涓诲悗绔?    app/
      main.py               # /predict銆?results 绛?API 璺敱
      infer_mamt2.py        # mock/real 妯″紡鍒囨崲锛宺eal 妯″紡璋冪敤 Worker
      uploads/              # 涓婁紶鍥剧墖鐩綍锛孌ocker 鏋勫缓鏃跺拷鐣?      outputs/              # 缁撴灉鍥剧洰褰曪紝Docker 鏋勫缓鏃跺拷鐣?    Dockerfile              # 杞婚噺 API 闀滃儚
    requirements.txt        # 鍚庣杞婚噺渚濊禆

  worker/                   # MAMT2 Worker 浠ｇ爜锛岀洰鍓嶆湰鍦拌繍琛岋紝涓嶅弬涓?Compose 瀹瑰櫒鍖?    mamt2_worker_api.py     # Worker HTTP 鏈嶅姟锛屽惈 /healthz銆?predict銆?predict-file
    mamt2_predictor.py      # 鐪熷疄 MAMT2 鎺ㄧ悊閫傞厤鍣?    requirements.txt        # Worker 閲嶅瀷渚濊禆璇存槑
    environment.yml         # 鏈潵 Ubuntu/Conda 鐜妯℃澘

  scripts/                  # 鏈湴鍚姩鑴氭湰
  docs/                     # 妯″瀷鎺ュ叆涓庡伐绋嬭鏄?  docker-compose.yml        # 褰撳墠 frontend + backend 杞婚噺 Compose
  README.md
```

## API 璁捐

褰撳墠鎺ㄨ崘閾捐矾浣跨敤鏂囦欢涓婁紶鏂瑰紡锛岄伩鍏嶅鍣ㄤ箣闂翠緷璧栧叡浜湰鏈虹粷瀵硅矾寰勩€?
```text
鍓嶇璇锋眰锛歅OST /api/predict
Nginx 浠ｇ悊锛?api/* -> backend:8000/*
鍚庣鎺ユ敹锛歅OST /predict
鍚庣杞彂锛歅OST {MAMT2_WORKER_URL}/predict-file
Compose 涓細MAMT2_WORKER_URL=http://host.docker.internal:9000
```

`/predict-file` 浣跨敤 `multipart/form-data` 涓婁紶鍥剧墖鏂囦欢缁?Worker锛岄€傚悎 Docker/K8s 闃舵銆俉orker 鍘熸湁鐨?`/predict` 璺緞鐗堟帴鍙ｄ粛淇濈暀锛屼富瑕佺敤浜?Windows 鏈湴璋冭瘯銆?
## 杩愯妯″紡

### A. 鏈湴 Mock 妯″紡

Mock 妯″紡鍙惎鍔?FastAPI 鍚庣锛屼笉闇€瑕佺湡瀹?MAMT2 Worker銆傞€傚悎蹇€熼獙璇佸墠绔€佷笂浼犲拰缁撴灉灞曠ず娴佺▼銆?
```bash
conda activate mamt2-api
bash scripts/start_backend_mock.sh
```

鍓嶇鏈湴寮€鍙戯細

```bash
cd frontend
npm run dev
```

### B. 鏈湴鐪熷疄 Worker 妯″紡

璇ユā寮忎笉浣跨敤 Docker锛學orker 涓庡悗绔兘鍦ㄥ涓绘満涓婅繍琛屻€?
缁堢 1锛屽惎鍔ㄧ湡瀹?Worker锛?
```bash
conda activate General
cd /d/pythonproject/mamt2-cloud-shm
bash scripts/start_worker.sh
```

缁堢 2锛屽惎鍔ㄧ湡瀹炴帹鐞嗗悗绔細

```bash
conda activate mamt2-api
cd /d/pythonproject/mamt2-cloud-shm
bash scripts/start_backend_real.sh
```

缁堢 3锛屽惎鍔ㄥ墠绔紑鍙戞湇鍔★細

```bash
cd /d/pythonproject/mamt2-cloud-shm/frontend
npm run dev
```

### C. Docker Compose 杞婚噺鐪熷疄妯″紡

杩欐槸褰撳墠閲嶇偣杩愯鏂瑰紡銆俧rontend 鍜?backend 宸插鍣ㄥ寲锛學orker 浠嶈繍琛屽湪瀹夸富鏈?`General` 鐜涓€?
缁堢 1锛屽厛鍚姩瀹夸富鏈?Worker锛?
```bash
conda activate General
cd /d/pythonproject/mamt2-cloud-shm
bash scripts/start_worker.sh
```

缁堢 2锛屽惎鍔?Docker Compose 鍓嶅悗绔細

```bash
cd /d/pythonproject/mamt2-cloud-shm
docker compose up --build
```

娴忚鍣ㄨ闂細

```text
http://localhost:5173
```

褰撳墠 Compose 鏈嶅姟锛?
- `frontend`锛歂ginx 鎵樼 React 闈欐€侀〉闈紝瀹夸富鏈?`5173` 鏄犲皠鍒板鍣?`80`銆?- `backend`锛欶astAPI API 鏈嶅姟锛屽涓绘満 `8000` 鏄犲皠鍒板鍣?`8000`銆?- `worker`锛氭殏鏃朵笉瀹瑰櫒鍖栵紝杩愯鍦?Windows 瀹夸富鏈?`General` 鐜锛岀鍙?`9000`銆?
backend 瀹瑰櫒閫氳繃 `host.docker.internal:9000` 璁块棶瀹夸富鏈?Worker銆?
## Docker Compose 杩愯姝ラ

1. 纭 Docker Desktop 宸插惎鍔ㄣ€?2. 鍚姩瀹夸富鏈?Worker锛?
```bash
conda activate General
cd /d/pythonproject/mamt2-cloud-shm
bash scripts/start_worker.sh
```

3. 鍚姩 frontend/backend 瀹瑰櫒锛?
```bash
cd /d/pythonproject/mamt2-cloud-shm
docker compose up --build
```

4. 鎵撳紑娴忚鍣細

```text
http://localhost:5173
```

5. 涓婁紶鍥剧墖锛屾煡鐪嬬湡瀹炴帹鐞嗙粨鏋滃浘銆乥box銆乵ask銆佺被鍒拰缃俊搴︺€?
## 甯哥敤娴嬭瘯鍛戒护

妫€鏌ュ涓绘満 Worker锛?
```bash
curl http://127.0.0.1:9000/healthz
```

妫€鏌ュ墠绔?Nginx 鍒板悗绔?API 鐨勪唬鐞嗭細

```bash
curl http://localhost:5173/api/
```

妫€鏌ュ涓绘満鏄犲皠鐨?backend API锛?
```bash
curl http://localhost:8000/
```

鏌ョ湅 Compose 鏈嶅姟鐘舵€侊細

```bash
docker compose ps
```

鏌ョ湅鍚庣鏃ュ織锛?
```bash
docker compose logs -f backend
```

鏌ョ湅鍓嶇鏃ュ織锛?
```bash
docker compose logs -f frontend
```

濡傛灉闇€瑕佸湪瀹瑰櫒鍐呮墽琛屽懡浠わ紝Git Bash 涓嬪缓璁姞 `-T`锛?
```bash
docker compose exec -T backend sh
```

## 甯歌闂

### Docker Desktop 娌℃湁鍚姩

濡傛灉 `docker compose up` 鎻愮ず鏃犳硶杩炴帴 Docker API锛岄€氬父鏄?Docker Desktop 娌″惎鍔ㄣ€傚厛鍚姩 Docker Desktop锛岀瓑寰?Docker Engine ready 鍚庡啀鎵ц鍛戒护銆?
### Docker Hub 闀滃儚鎷夊彇澶辫触

濡傛灉鎷夊彇 `python:3.10-slim`銆乣node:20-alpine`銆乣nginx:alpine` 澶辫触锛岄€氬父闇€瑕佸湪 Docker Desktop 涓厤缃唬鐞嗭紝鎴栧垏鎹㈠彲鐢ㄧ綉缁滅幆澧冦€?
### Nginx 鎶?unknown directive "锘縮erver"

杩欓€氬父鏄?`frontend/nginx.conf` 鏂囦欢寮€澶村甫 UTF-8 BOM 瀵艰嚧銆侼ginx銆丏ockerfile銆乣docker-compose.yml` 绛夐厤缃枃浠跺繀椤讳繚瀛樹负 UTF-8 鏃?BOM銆傞」鐩凡娣诲姞 `.editorconfig` 鐢ㄤ簬闄嶄綆鍐嶆鍑虹幇 BOM 鐨勯闄┿€?
### Git Bash 涓?docker compose exec 寮傚父

Git Bash 閲?`docker compose exec` 鏈夋椂浼氬彈 TTY 杞崲褰卞搷銆傚彲浠ヤ娇鐢細

```bash
docker compose exec -T backend sh
```

### POST /api/predict 405 Method Not Allowed

閫氬父鏄墠绔帴鍙ｈ矾寰勩€丯ginx 浠ｇ悊瑙勫垯鍜屽悗绔矾鐢变笉涓€鑷村鑷淬€傚綋鍓嶇洰鏍囬厤缃负锛?
```text
鍓嶇锛歅OST /api/predict
Nginx锛?api/* -> backend:8000/*
鍚庣锛歅OST /predict
```

纭 `frontend/nginx.conf` 涓瓨鍦?`/api/` 浠ｇ悊锛屽苟閲嶆柊鏋勫缓鍓嶇闀滃儚锛?
```bash
docker compose up --build
```

## 闀滃儚涓庡鍣ㄦ竻鐞?
娓呯悊鎮┖闀滃儚锛?
```bash
docker image prune
```

娓呯悊鍋滄瀹瑰櫒锛?
```bash
docker container prune
```

褰撳墠闃舵鏆傛椂涓嶈浣跨敤锛?
```bash
docker system prune -a
```

鍥犱负瀹冧細鍒犻櫎鏈褰撳墠瀹瑰櫒浣跨敤鐨勫熀纭€闀滃儚锛屽悗缁噸鏂版瀯寤烘椂鍙兘闇€瑕侀噸鏂版媺鍙?Docker Hub 闀滃儚銆?
## 妯″瀷涓庢潈閲嶈鏄?
鐪熷疄妯″瀷鏉冮噸鍜岄厤缃綋鍓嶄粛鍦ㄦ湰鏈?`MAMT2-final` 椤圭洰涓紝娌℃湁澶嶅埗鍒版湰浠撳簱锛屼篃涓嶅缓璁彁浜ゅ埌 Git銆傚悗缁?Docker/K8s 闃舵搴旈€氳繃鐜鍙橀噺鍜屾ā鍨嬫寕杞界鐞嗭細

- `MAMT2_DETECTRON2_ROOT`
- `MAMT2_CONFIG_PATH`
- `MAMT2_WEIGHT_PATH`
- `MAMT2_OUTPUT_DIR`

鎺ㄨ崘鍚庣画浣跨敤 `model/weights` 鏈湴鎸傝浇銆並ubernetes PVC 鎴?MinIO/S3 瀵硅薄瀛樺偍绠＄悊妯″瀷鏉冮噸銆?
## 鍚庣画璁″垝

- Kubernetes Deployment / Service / ConfigMap銆?- MAMT2 Worker 瀹瑰櫒鍖栥€?- Redis 寮傛浠诲姟闃熷垪銆?- MinIO 缁撴灉鍥句笌涓婁紶鏂囦欢瀛樺偍銆?- MySQL 浠诲姟涓庢娴嬬粨鏋滃厓鏁版嵁鎸佷箙鍖栥€?- Prometheus / Grafana 鐩戞帶銆?- 鏇村畬鏁寸殑鍓嶇浠诲姟鍒楄〃銆佸巻鍙茶褰曞拰鎵归噺鎺ㄧ悊椤甸潰銆?
