# Deploying the RAG model service to Google Cloud Run

This guide covers building the `rag_service/` container and deploying it to
**Cloud Run** three ways: manual `gcloud`, **Cloud Build** (`cloudbuild.yaml`),
and **GitHub Actions** (`.github/workflows/deploy-cloud-run.yml`). It also covers
running the **Ollama** LLM as a separate GPU-enabled Cloud Run service that this
service calls for generation.

> Scope: this deploys *only* the RAG model service (embeddings + reranking +
> generation proxy). The main EagleGIS API is unchanged.

## What the service exposes

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness (never loads models) |
| GET | `/ready` | Readiness (which backends are loaded/configured) |
| POST | `/embed` | Dense embeddings via BGE-M3 |
| POST | `/rerank` | Cross-encoder reranking via bge-reranker-v2-m3 |
| POST | `/generate` | LLM generation; `role` selects the model tier (`utility` or `generation`) |
| POST | `/generate_batch` | Concurrent fan-out of many prompts to a tier (bounded by a semaphore) — used for CRAG grading / ingest contextualization |

Models load lazily by default, so the container becomes healthy immediately and
downloads weights on first `/embed` or `/rerank` call. Set `PRELOAD_MODELS=true`
(or bake weights with `--build-arg PRELOAD_MODELS=true`) to trade cold-start time
for faster first request.

## Environment variables

| Var | Default | Notes |
| --- | --- | --- |
| `PORT` | `8080` | Injected by Cloud Run; do not set manually there |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | sentence-transformers model id |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | cross-encoder model id |
| `MODEL_DEVICE` | `cpu` | set to `cuda` on a GPU instance |
| `PRELOAD_MODELS` | `false` | load models at startup vs lazily |
| `GENERATION_OLLAMA_URL` | _(falls back to `OLLAMA_BASE_URL`)_ | URL of the **generation** LLM service (larger model, GPU) |
| `GENERATION_MODEL` | `qwen3:4b` | model served by the generation tier |
| `UTILITY_OLLAMA_URL` | _(falls back to `OLLAMA_BASE_URL`)_ | URL of the **utility** LLM service (small model, CPU, high concurrency) |
| `UTILITY_MODEL` | `qwen3:1.7b` | model served by the utility tier |
| `RAG_MAX_CONCURRENCY` | `8` | default cap on concurrent `/generate_batch` calls |
| `OLLAMA_BASE_URL` | _(empty)_ | single-service fallback used when the role-specific URLs are unset |
| `OLLAMA_MODEL` | `qwen3:4b` | fallback default model |

**Role-tiered LLMs.** The model layer is split so cheap, high-concurrency work
(routing, CRAG grading, query rewriting, ingest contextualization) hits a small
CPU model while only final generation hits the larger GPU model. Point each tier
at its own Ollama Cloud Run service via `UTILITY_OLLAMA_URL` /
`GENERATION_OLLAMA_URL`. To start simple, set just `OLLAMA_BASE_URL` and both
tiers share it.

---

## 0. One-time project setup

```bash
export PROJECT_ID="your-project-id"
export REGION="us-central1"
export REPO="eaglegis"

gcloud config set project "$PROJECT_ID"

# Enable the APIs we use.
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  iamcredentials.googleapis.com

# Create the Artifact Registry Docker repo (once).
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --description="EagleGIS containers"
```

---

## 1. Manual deploy with `gcloud`

```bash
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/eaglegis-rag:$(git rev-parse --short HEAD)"

# Authenticate Docker to Artifact Registry, build, and push.
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
docker build -t "$IMAGE" rag_service
docker push "$IMAGE"

# Deploy.
gcloud run deploy eaglegis-rag \
  --image="$IMAGE" \
  --region="$REGION" \
  --platform=managed \
  --allow-unauthenticated \
  --memory=4Gi --cpu=2 --timeout=300 --concurrency=8 --max-instances=3 \
  --set-env-vars=OLLAMA_BASE_URL="$OLLAMA_BASE_URL",OLLAMA_MODEL=qwen3:4b
```

`make docker-build` / `make docker-run` do the local build/run; `make gcp-deploy`
runs the Cloud Build flow below.

> Tip: you can skip the local Docker build entirely with
> `gcloud run deploy eaglegis-rag --source rag_service --region "$REGION"`,
> which builds the image in the cloud from the Dockerfile.

---

## 2. Cloud Build (`cloudbuild.yaml`)

One-shot from your machine:

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_REGION="$REGION",_OLLAMA_BASE_URL="$OLLAMA_BASE_URL"
```

To deploy automatically on push, create a trigger pointing at this repo and
config file:

```bash
gcloud builds triggers create github \
  --repo-name=EagleGIS --repo-owner=YOUR_GH_ORG \
  --branch-pattern='^main$' \
  --build-config=cloudbuild.yaml
```

The Cloud Build service account needs the **Cloud Run Admin**, **Artifact
Registry Writer**, and **Service Account User** roles.

---

## 3. GitHub Actions via Workload Identity Federation

The workflow `.github/workflows/deploy-cloud-run.yml` deploys on push to `main`
(paths under `rag_service/**`). It authenticates with WIF — no JSON keys.

### One-time WIF setup

```bash
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
export POOL="github-pool"
export PROVIDER="github-provider"
export GH_REPO="YOUR_GH_ORG/EagleGIS"   # owner/repo

# Deploy service account.
gcloud iam service-accounts create gh-deployer \
  --display-name="GitHub Actions deployer"
export DEPLOY_SA="gh-deployer@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant it deploy permissions.
for ROLE in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${DEPLOY_SA}" --role="$ROLE"
done

# Workload Identity Pool + provider (restricted to your repo).
gcloud iam workload-identity-pools create "$POOL" --location=global \
  --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
  --location=global --workload-identity-pool="$POOL" \
  --display-name="GitHub OIDC" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${GH_REPO}'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# Let the GitHub repo impersonate the deploy SA.
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${GH_REPO}"

# Print the provider resource name to paste into the GCP_WIF_PROVIDER secret.
echo "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVIDER}"
```

### Repo secrets / variables to set (Settings -> Secrets and variables -> Actions)

| Secret | Value |
| --- | --- |
| `GCP_WIF_PROVIDER` | the provider resource name printed above |
| `GCP_DEPLOY_SA` | `gh-deployer@PROJECT_ID.iam.gserviceaccount.com` |
| `GCP_PROJECT_ID` | your project id |
| `OLLAMA_BASE_URL` | (optional) URL of the Ollama service |
| `vars.GCP_REGION` | (optional) region, defaults to `us-central1` |

---

## 4. Ollama LLM tiers (two separate Cloud Run services)

`/generate` proxies to Ollama. Run **two** Ollama services so the model layer is
decoupled and each scales on its own: a small **utility** model (CPU, scales out
for the concurrent routing/grading/contextualization fan-out) and a larger
**generation** model (GPU, low concurrency, final answers). Then wire both URLs
into the RAG service.

```bash
# --- Utility tier: small model, CPU, scales OUT for concurrent fan-out ---
gcloud run deploy ollama-utility \
  --image=ollama/ollama \
  --region="$REGION" \
  --cpu=4 --memory=8Gi --no-cpu-throttling \
  --concurrency=16 --max-instances=10 \
  --port=11434 --allow-unauthenticated      # lock down in production
export UTILITY_OLLAMA_URL="$(gcloud run services describe ollama-utility --region "$REGION" --format='value(status.url)')"

# --- Generation tier: larger model, GPU (NVIDIA L4), low concurrency ---
# GPU on Cloud Run may require a quota request and is region-limited.
gcloud run deploy ollama-generation \
  --image=ollama/ollama \
  --region="$REGION" \
  --gpu=1 --gpu-type=nvidia-l4 \
  --cpu=4 --memory=16Gi --no-cpu-throttling \
  --concurrency=4 --max-instances=1 --timeout=600 \
  --port=11434 --allow-unauthenticated
export GENERATION_OLLAMA_URL="$(gcloud run services describe ollama-generation --region "$REGION" --format='value(status.url)')"

# Wire both tiers into the RAG service.
gcloud run services update eaglegis-rag --region "$REGION" \
  --set-env-vars=UTILITY_OLLAMA_URL="$UTILITY_OLLAMA_URL",UTILITY_MODEL=qwen3:1.7b,GENERATION_OLLAMA_URL="$GENERATION_OLLAMA_URL",GENERATION_MODEL=qwen3:4b
```

Pull each model into its service once it's up, e.g.
`POST {UTILITY_OLLAMA_URL}/api/pull` with `{"model":"qwen3:1.7b"}` and the same
for the generation model. Embeddings + reranking run fine CPU-only; only the
generation tier benefits meaningfully from the GPU.

### Simplest start: one shared Ollama

Deploy a single `ollama` service and set only `OLLAMA_BASE_URL`; both tiers fall
back to it. Split into two services later with no code change — just set the
role-specific URLs.

### CPU-only / no-LLM mode

Leave all Ollama URLs unset to deploy just the embedding + reranking endpoints;
`/generate` returns `503` until a URL is configured. This is the cheapest way to
get the service live first and add generation later.

---

## Smoke test

```bash
URL="$(gcloud run services describe eaglegis-rag --region "$REGION" --format='value(status.url)')"

curl -s "$URL/health"
curl -s "$URL/ready"
curl -s -X POST "$URL/embed" \
  -H 'content-type: application/json' \
  -d '{"texts":["BERT Rail Trail easement vote"]}' | head -c 300
```

First `/embed` after a cold start downloads model weights (unless preloaded), so
allow extra time on the initial call.
