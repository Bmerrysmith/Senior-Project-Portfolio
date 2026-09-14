#!/usr/bin/env bash
# Build the Lambda container image and push it to ECR.
# Usage: deploy/build_and_push.sh [tag]   (tag defaults to "latest")
set -euo pipefail

ACCOUNT_ID=621554168891
REGION=us-east-1
REPO=rag-email-agent
TAG="${1:-latest}"
IMAGE_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:${TAG}"

cd "$(dirname "$0")/.."

# Create the repo on first run (no-op if it already exists).
aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$REPO" --region "$REGION" >/dev/null

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# Lambda runs linux/amd64; force it in case the build host is arm.
# --provenance=false / --sbom=false: Lambda rejects the OCI manifest-list +
# attestation output BuildKit produces by default.
docker build --platform linux/amd64 --provenance=false --sbom=false -t "${REPO}:${TAG}" .
docker tag "${REPO}:${TAG}" "$IMAGE_URI"
docker push "$IMAGE_URI"

echo "pushed: $IMAGE_URI"
