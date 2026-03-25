# Deploy

## 디렉토리 구조

```
deploy/
├── docker/
│   └── Dockerfile
└── k8s/
    ├── deployment.yaml
    ├── service.yaml
    └── ingress.yaml
```

---

## Docker

### 빌드 & 푸시

```bash
# 프로젝트 루트에서 실행
docker build -f deploy/docker/Dockerfile -t aip-harbor.sktai.io/sktai/agent/builder-qa:latest .
docker push aip-harbor.sktai.io/sktai/agent/builder-qa:latest
```

> VSCode에서는 **Terminal → Run Task → Docker: Build / Docker: Push** 로 실행 가능

### 베이스 이미지

```
aip-harbor.sktai.io/sktai/python-base:3.12-bookworm-ossl3.0.18
```

### 복사 파일

| 소스 | 컨테이너 경로 |
|------|--------------|
| `app_streamlit/` | `/app/app_streamlit/` |
| `core/` | `/app/core/` |
| `scenarios/` | `/app/scenarios/` |
| `.env.example` | `/app/.env` (기본값) |

실행 환경변수는 k8s Deployment의 `env` 또는 Secret으로 주입.

---

## Kubernetes

### namespace

```
aiplatform
```

### 배포

```bash
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
kubectl apply -f deploy/k8s/ingress.yaml
```

### 접속 URL

```
http://aip-agent-builder-qa.sktai.io
```

`/etc/hosts` 로컬 등록 (클러스터 외부에서 접근 시):

```
172.21.147.169  aip-agent-builder-qa.sktai.io
```

---

## 주의사항

`scenarios/`는 컨테이너 파일시스템에 저장되므로 **pod 재시작 시 변경사항이 초기화**됨.
