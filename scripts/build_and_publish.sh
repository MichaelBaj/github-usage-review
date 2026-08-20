#!/bin/bash
#
# Build and publish copilot-review docker images
# Usage: ./build_and_publish.sh
#
# Before running, authenticate with Artifactory:
#   docker login docker-tools.artifactory.ssn.juniper.net
#   (username: your Juniper email, password: Artifactory API token)

set -euo pipefail

BASE_REPO_DIR="$(git rev-parse --show-toplevel)"
BASE_REPO_URL="docker-tools.artifactory.ssn.juniper.net/copilot-review"

BACKEND_CFG="$BASE_REPO_DIR/backend/app/config.py"
FRONTEND_APP="$BASE_REPO_DIR/frontend/src/App.tsx"

BACKEND_VERSION=$(sed -n 's/^VERSION = "\([^"]*\)"/\1/p' "$BACKEND_CFG")
FRONTEND_VERSION=$(sed -n 's/^const VERSION = "\([^"]*\)";/\1/p' "$FRONTEND_APP")

echo "Building ${BASE_REPO_URL}-frontend:${FRONTEND_VERSION} from ${BASE_REPO_DIR}/frontend"
echo "Building ${BASE_REPO_URL}-backend:${BACKEND_VERSION} from ${BASE_REPO_DIR}/backend"

read -p "Do you want to continue? (y/N): " -n 1 -r
echo    # Moves to a new line
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

echo "Building and publishing Docker images for copilot-review..."

# Build the Docker images
docker build --target prod -t "${BASE_REPO_URL}-frontend:${FRONTEND_VERSION}" "${BASE_REPO_DIR}/frontend"
docker build -t "${BASE_REPO_URL}-backend:${BACKEND_VERSION}" "${BASE_REPO_DIR}/backend"

# Push the Docker images to Artifactory
echo "Pushing ${BASE_REPO_URL}-frontend:${FRONTEND_VERSION}"
docker push "${BASE_REPO_URL}-frontend:${FRONTEND_VERSION}"

echo "Pushing ${BASE_REPO_URL}-backend:${BACKEND_VERSION}"
docker push "${BASE_REPO_URL}-backend:${BACKEND_VERSION}"

echo "Done"
