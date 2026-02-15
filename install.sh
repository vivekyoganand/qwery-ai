#!/bin/bash
# Qwery AI Deployment Script for OpenShift
# This script deploys PostgreSQL with pgvector, Ollama, and Qwery AI

set -e

# Configuration
NAMESPACE="qwery-ai"
STORAGE_CLASS="netapp-file-standard"  # Change to your storage class

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Qwery AI Deployment Script${NC}"
echo -e "${GREEN}========================================${NC}"

# Check prerequisites
echo -e "\n${YELLOW}Checking prerequisites...${NC}"

if ! command -v oc &> /dev/null; then
    echo -e "${RED}Error: oc CLI not found. Please install OpenShift CLI.${NC}"
    exit 1
fi

if ! command -v helm &> /dev/null; then
    echo -e "${RED}Error: helm CLI not found. Please install Helm 3.x.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Prerequisites check passed${NC}"

# Check if logged in to OpenShift
echo -e "\n${YELLOW}Checking OpenShift connection...${NC}"
if ! oc whoami &> /dev/null; then
    echo -e "${RED}Error: Not logged in to OpenShift. Please run 'oc login' first.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Connected to OpenShift as $(oc whoami)${NC}"

# Create namespace
echo -e "\n${YELLOW}Creating namespace: $NAMESPACE${NC}"
oc new-project $NAMESPACE 2>/dev/null || oc project $NAMESPACE

# Check storage class
echo -e "\n${YELLOW}Checking storage class: $STORAGE_CLASS${NC}"
if ! oc get storageclass $STORAGE_CLASS &> /dev/null; then
    echo -e "${RED}Warning: Storage class '$STORAGE_CLASS' not found.${NC}"
    echo -e "${YELLOW}Available storage classes:${NC}"
    oc get storageclass
    read -p "Enter the storage class name to use: " STORAGE_CLASS
fi

echo -e "${GREEN}✓ Using storage class: $STORAGE_CLASS${NC}"

# Deploy PostgreSQL with pgvector
echo -e "\n${YELLOW}========================================${NC}"
echo -e "${YELLOW}Deploying PostgreSQL with pgvector...${NC}"
echo -e "${YELLOW}========================================${NC}"

helm upgrade --install postgresql-pgvector ./postgresql-pgvector \
  --namespace $NAMESPACE \
  --set persistence.storageClass=$STORAGE_CLASS \
  --wait --timeout 10m

echo -e "${GREEN}✓ PostgreSQL deployed successfully${NC}"

# Wait for PostgreSQL to be ready
echo -e "\n${YELLOW}Waiting for PostgreSQL to be ready...${NC}"
oc wait --for=condition=ready pod -l app.kubernetes.io/name=postgresql-pgvector -n $NAMESPACE --timeout=300s

# Verify pgvector extension
echo -e "\n${YELLOW}Verifying pgvector extension...${NC}"
oc exec -n $NAMESPACE deployment/postgresql-pgvector -- \
  psql -U qweryai -d vectordb -c "SELECT * FROM pg_extension WHERE extname='vector';"

echo -e "${GREEN}✓ pgvector extension verified${NC}"

# Deploy Ollama
echo -e "\n${YELLOW}========================================${NC}"
echo -e "${YELLOW}Deploying Ollama...${NC}"
echo -e "${YELLOW}========================================${NC}"

helm upgrade --install ollama ./ollama \
  --namespace $NAMESPACE \
  --set persistence.storageClass=$STORAGE_CLASS \
  --wait --timeout 20m

echo -e "${GREEN}✓ Ollama deployed successfully${NC}"

# Wait for Ollama models to download
echo -e "\n${YELLOW}Waiting for Ollama models to download (this may take 10-15 minutes)...${NC}"
oc logs -f -n $NAMESPACE deployment/ollama -c model-downloader || true

# Verify Ollama
echo -e "\n${YELLOW}Verifying Ollama models...${NC}"
POD_NAME=$(oc get pods -n $NAMESPACE -l app.kubernetes.io/name=ollama -o jsonpath="{.items[0].metadata.name}")
oc exec -n $NAMESPACE $POD_NAME -- ollama list

echo -e "${GREEN}✓ Ollama models verified${NC}"

# Deploy Qwery AI
echo -e "\n${YELLOW}========================================${NC}"
echo -e "${YELLOW}Deploying Qwery AI...${NC}"
echo -e "${YELLOW}========================================${NC}"

echo -e "${RED}IMPORTANT: Before deploying Qwery AI, you need to:${NC}"
echo -e "${YELLOW}1. Build and push your Qwery AI Docker image${NC}"
echo -e "${YELLOW}2. Update the image repository in qwery-ai/values.yaml${NC}"
echo ""
read -p "Have you built and pushed the Qwery AI image? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Skipping Qwery AI deployment. Deploy manually when ready:${NC}"
    echo -e "${YELLOW}  helm upgrade --install qwery-ai ./qwery-ai --namespace $NAMESPACE${NC}"
else
    helm upgrade --install qwery-ai ./qwery-ai \
      --namespace $NAMESPACE \
      --wait --timeout 5m

    echo -e "${GREEN}✓ Qwery AI deployed successfully${NC}"

    # Get the route URL
    ROUTE_URL=$(oc get route qwery-ai -n $NAMESPACE -o jsonpath='{.spec.host}')
    echo -e "\n${GREEN}========================================${NC}"
    echo -e "${GREEN}Deployment Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Qwery AI URL: https://$ROUTE_URL${NC}"
    echo -e "${GREEN}Health Check: https://$ROUTE_URL/health${NC}"
    echo -e "${GREEN}API Docs: https://$ROUTE_URL/docs${NC}"
fi

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Summary${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "Namespace: $NAMESPACE"
echo -e "Storage Class: $STORAGE_CLASS"
echo ""
echo -e "To check the status:"
echo -e "  oc get pods -n $NAMESPACE"
echo ""
echo -e "To view logs:"
echo -e "  oc logs -f deployment/qwery-ai -n $NAMESPACE"
echo ""
echo -e "To uninstall:"
echo -e "  helm uninstall qwery-ai postgresql-pgvector ollama -n $NAMESPACE"
