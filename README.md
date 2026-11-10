# Cloud Board

프론트엔드(nginx + 정적 JS)와 백엔드(FastAPI)가 분리된 게시판을 로컬 Kubernetes(kind)에 올리고,
GitHub Actions + ArgoCD(CI/CD), Prometheus + Grafana(모니터링), AWS Lambda(욕설 필터)를 붙인 프로젝트.

```
브라우저 ──▶ frontend (nginx, Deployment x2) ──/api──▶ backend (FastAPI, Deployment x2) ──▶ postgres (StatefulSet + PVC)
                                                          │  └─▶ AWS Lambda Function URL (욕설 필터, 선택)
                                                          └─ /metrics ◀── Prometheus ──▶ Grafana

git push(main) ─▶ GitHub Actions: 이미지 빌드 → GHCR push → k8s/kustomization.yaml 태그 커밋 ─▶ ArgoCD 자동 Sync
```

## 디렉터리

| 경로 | 내용 |
|---|---|
| `backend/` | FastAPI CRUD API, Dockerfile |
| `frontend/` | 정적 페이지 + nginx 리버스 프록시, Dockerfile |
| `k8s/` | Namespace, Postgres, backend, frontend 매니페스트 (kustomize) |
| `argocd/application.yaml` | ArgoCD Application (k8s/ 경로 자동 동기화) |
| `.github/workflows/ci.yaml` | main push 시 빌드·푸시·매니페스트 갱신 |
| `monitoring/` | kube-prometheus-stack values, ServiceMonitor, Grafana 대시보드 |
| `serverless/` | 욕설 필터 Lambda 함수 |

## 1. 클러스터

```bash
kind create cluster --config kind-config.yaml
```

## 2. ArgoCD

```bash
kubectl create namespace argocd
kubectl apply -n argocd --server-side -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl apply -f argocd/application.yaml
# UI: https://localhost:8443  (admin / 아래 명령으로 초기 비밀번호 확인)
kubectl -n argocd port-forward svc/argocd-server 8443:443
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d
```

게시판: http://localhost:8080

## 3. 모니터링

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install monitoring prometheus-community/kube-prometheus-stack -n monitoring --create-namespace -f monitoring/values.yaml
kubectl apply -f monitoring/servicemonitor.yaml -f monitoring/grafana-dashboard.yaml
# Grafana: http://localhost:3000  (admin / monitoring/values.yaml 의 adminPassword), 대시보드 "Cloud Board"
kubectl -n monitoring port-forward svc/monitoring-grafana 3000:80
```

## 4. 서버리스 (선택)

1. AWS Lambda 에 `serverless/lambda_function.py` 를 Python 3.12 런타임으로 생성
2. Function URL 생성 (Auth type: NONE)
3. `k8s/backend.yaml` 의 `FILTER_URL` 에 URL 을 넣고 push → ArgoCD 가 반영
4. `kubectl -n board rollout restart deploy/backend` (ConfigMap 변경 반영)

## 시연 때 쓸 명령

```bash
kubectl -n board get deploy,pod,svc,pvc
kubectl -n board exec -it postgres-0 -- psql -U board -d board -c 'select id, title, author, created_at from posts order by id;'
kubectl -n argocd get applications
```
