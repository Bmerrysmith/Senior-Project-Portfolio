# Deploy runbook — Step 5 (Lambda + EventBridge Scheduler)

Region `us-east-1`, account `621554168891`. CLI runs as the
`rag-email-agent-user` profile. See PLANNING.md (2026-08-28 entry) for the
reasoning behind each choice. The initial deploy was done 2026-08-28 — this
doc is the record of what exists and how to redeploy.

> **Windows / Git Bash:** prefix `docker run -v` mounts and any `aws` call
> that takes a `/aws/...`-style value with `MSYS_NO_PATHCONV=1` to stop the
> shell rewriting the paths.

## What exists

| Resource | Name / ARN |
|---|---|
| ECR repo | `621554168891.dkr.ecr.us-east-1.amazonaws.com/rag-email-agent` |
| ECR repo policy | `LambdaECRImageRetrievalPolicy` (lets `lambda.amazonaws.com` pull) |
| Lambda | `rag-email-agent-daily` — image, 900 s, 1024 MB, x86_64 |
| Exec role | `rag-email-agent-lambda-exec` = `AWSLambdaBasicExecutionRole` + `rag-email-agent-lambda-secrets` |
| Scheduler role | `rag-email-agent-scheduler` = `rag-email-agent-scheduler-invoke` |
| Schedule | `rag-email-agent-daily` — `cron(0 7 * * ? *)` `America/New_York`, retry 2×/1h |
| Secrets (read at runtime) | `rag-email-agent/{token-encryption-key, supabase-connection-string, openai-api-key}` |

## Redeploy after a code change

```bash
deploy/build_and_push.sh
aws lambda update-function-code --function-name rag-email-agent-daily \
  --image-uri 621554168891.dkr.ecr.us-east-1.amazonaws.com/rag-email-agent:latest \
  --region us-east-1
```

`build_and_push.sh` builds with `--platform linux/amd64 --provenance=false
--sbom=false` (Lambda rejects BuildKit's default OCI manifest-list output).

## Manual invoke

```bash
aws lambda invoke --function-name rag-email-agent-daily --region us-east-1 \
  --cli-read-timeout 900 --log-type Tail --query LogResult --output text out.json \
  | base64 -d | tail -40
cat out.json      # expect {"status": "ok"}
```

A full run is ~6 min. `digest` self-sends only for the previous ET day and
is idempotent via `digest_log`, so re-invoking the same day sends nothing.

## Environment variables on the function

Non-secret only — set from `deploy/lambda_env.json` shape:

```json
{"Variables": {
  "CLIENT_ID": "5536b9ae-bddd-478b-ada2-3b48f6a1c683",
  "AUTHORITY": "https://login.microsoftonline.com/consumers",
  "GRAPH_SCOPES": "Mail.Read Mail.Send",
  "REDIRECT_URI": "http://localhost:5000/auth/callback",
  "FLASK_SECRET_KEY": "unused-in-lambda"
}}
```

`REDIRECT_URI` / `FLASK_SECRET_KEY` are only there to satisfy `config.py`'s
import; the batch pipeline never reads them.

```bash
aws lambda update-function-configuration --function-name rag-email-agent-daily \
  --region us-east-1 --environment file://env.json
```

## First-time creation commands (already run — kept for reference / rebuild)

```bash
# ECR
aws ecr create-repository --repository-name rag-email-agent --region us-east-1
# repo policy: deploy user needs ecr:SetRepositoryPolicy (added to
# rag-email-agent-deploy-policy 2026-08-28)
aws ecr set-repository-policy --repository-name rag-email-agent --region us-east-1 \
  --policy-text file://deploy/ecr_repo_policy.json

# Execution role
aws iam create-role --role-name rag-email-agent-lambda-exec \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam attach-role-policy --role-name rag-email-agent-lambda-exec \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam attach-role-policy --role-name rag-email-agent-lambda-exec \
  --policy-arn arn:aws:iam::621554168891:policy/rag-email-agent-lambda-secrets

# Function
aws lambda create-function --function-name rag-email-agent-daily \
  --package-type Image \
  --code ImageUri=621554168891.dkr.ecr.us-east-1.amazonaws.com/rag-email-agent:latest \
  --role arn:aws:iam::621554168891:role/rag-email-agent-lambda-exec \
  --timeout 900 --memory-size 1024 --architectures x86_64 \
  --environment file://deploy/lambda_env.json --region us-east-1

# Scheduler role + schedule
aws iam create-role --role-name rag-email-agent-scheduler \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"scheduler.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam attach-role-policy --role-name rag-email-agent-scheduler \
  --policy-arn arn:aws:iam::621554168891:policy/rag-email-agent-scheduler-invoke
aws scheduler create-schedule --name rag-email-agent-daily \
  --schedule-expression 'cron(0 7 * * ? *)' \
  --schedule-expression-timezone America/New_York \
  --flexible-time-window '{"Mode":"OFF"}' \
  --target file://deploy/schedule_target.json --region us-east-1
```

## Known gaps (deploy policy)

- **`lambda:PutFunctionConcurrency`** not granted — reserved concurrency of 1
  was not set. Low risk (a once-daily ~6-min job can't realistically overlap;
  `digest_log` / `triage_runs` idempotency covers a retry). To add: grant the
  action, then
  `aws lambda put-function-concurrency --function-name rag-email-agent-daily
  --reserved-concurrent-executions 1`.
- **`lambda:GetFunctionConfiguration`**, **`logs:*`** not granted — use
  `aws lambda get-function` for status; CloudWatch logs must be read from the
  console.
- No CloudWatch alarm / SNS. Failure signalling is in-handler: on an
  unhandled exception `lambda_handler` emails the traceback via Graph
  `Mail.Send`, then re-raises so the invocation records as an error and the
  Scheduler retry fires. Per-account failures inside a phase are isolated and
  logged, not raised — they don't trigger the notification.
