# Qwery AI Deployment on OpenShift

Complete Helm charts for deploying Qwery AI RAG service with PostgreSQL pgvector and Ollama on OpenShift.

## Architecture

```
User Query
   ↓
Qwery API Pod
   ↓
Embedding model (Ollama / HF)
   ↓
Store embedding → pgvector
   ↓
Similarity search
   ↓
Return context
   ↓
LLM generates answer
```

## Components

1. **PostgreSQL with pgvector** - Vector database for embeddings
2. **Ollama** - Local LLM and embedding model server
3. **Qwery AI** - RAG API service

## Directory Structure

```
qwery-ai-deployment/
├── postgresql-pgvector/      # PostgreSQL with pgvector Helm chart
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
│       ├── _helpers.tpl
│       ├── deployment.yaml
│       ├── service.yaml
│       ├── secret.yaml
│       ├── pvc.yaml
│       ├── configmap.yaml
│       └── NOTES.txt
├── ollama/                    # Ollama Helm chart
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
│       ├── _helpers.tpl
│       ├── deployment.yaml
│       ├── service.yaml
│       ├── pvc.yaml
│       └── NOTES.txt
├── qwery-ai/                  # Qwery AI Helm chart
│   ├── Chart.yaml
│   ├── values.yaml
│   ├── values-dev.yaml
│   ├── values-prod.yaml
│   └── templates/
│       ├── _helpers.tpl
│       ├── deployment.yaml
│       ├── service.yaml
│       ├── route.yaml
│       ├── configmap.yaml
│       ├── secret.yaml
│       ├── hpa.yaml
│       ├── networkpolicy.yaml
│       └── NOTES.txt
├── install.sh                 # Automated installation script
└── README.md                  # This file
```

## Prerequisites

### Required Tools
- OpenShift CLI (`oc`) version 4.x
- Helm CLI version 3.x
- Access to OpenShift cluster with admin privileges

### OpenShift Requirements
- OpenShift 4.10 or later
- OpenShift AI Operator installed (already running in your lab)
- Storage class available (e.g., netapp-file-standard)
- Minimum cluster resources:
  - 8 CPU cores
  - 16 GB RAM
  - 200 GB storage

### Check Prerequisites

```bash
# Check oc CLI
oc version

# Check Helm
helm version

# Login to OpenShift
oc login https://api.ocp4.example.com:6443

# Check storage classes
oc get storageclass

# Check OpenShift AI
oc get pods -n redhat-ods-applications
```

## Quick Start

### Option 1: Automated Installation (Recommended)

```bash
# Make the script executable
chmod +x install.sh

# Run the installation script
./install.sh
```

The script will:
1. Create the namespace
2. Deploy PostgreSQL with pgvector
3. Deploy Ollama with models
4. Deploy Qwery AI (if image is ready)

### Option 2: Manual Installation

#### Step 1: Create Namespace

```bash
oc new-project qwery-ai
```

#### Step 2: Deploy PostgreSQL with pgvector

```bash
# Update storage class in values.yaml if needed
helm upgrade --install postgresql-pgvector ./postgresql-pgvector \
  --namespace qwery-ai \
  --set persistence.storageClass=netapp-file-standard \
  --wait --timeout 10m
```

Verify deployment:

```bash
# Check pod status
oc get pods -n qwery-ai -l app.kubernetes.io/name=postgresql-pgvector

# Verify pgvector extension
oc exec -n qwery-ai deployment/postgresql-pgvector -- \
  psql -U qweryai -d vectordb -c "SELECT * FROM pg_extension WHERE extname='vector';"

# Test database connection
oc exec -n qwery-ai deployment/postgresql-pgvector -- \
  psql -U qweryai -d vectordb -c "SELECT version();"
```

#### Step 3: Deploy Ollama

```bash
# Deploy Ollama
helm upgrade --install ollama ./ollama \
  --namespace qwery-ai \
  --set persistence.storageClass=netapp-file-standard \
  --wait --timeout 20m
```

Monitor model download (takes 10-15 minutes):

```bash
# Watch model download progress
oc logs -f -n qwery-ai deployment/ollama -c model-downloader

# Verify models are downloaded
POD_NAME=$(oc get pods -n qwery-ai -l app.kubernetes.io/name=ollama -o jsonpath="{.items[0].metadata.name}")
oc exec -n qwery-ai $POD_NAME -- ollama list
```

#### Step 4: Build Qwery AI Application

Before deploying, you need to build the Qwery AI Docker image:

```bash
# Create Dockerfile (example provided in the guide)
# Build image
podman build -t quay.io/your-org/qwery-ai:latest .

# Push to registry
podman push quay.io/your-org/qwery-ai:latest
```

Update `qwery-ai/values.yaml`:

```yaml
image:
  repository: quay.io/your-org/qwery-ai
  tag: "latest"
```

#### Step 5: Deploy Qwery AI

```bash
# Deploy Qwery AI
helm upgrade --install qwery-ai ./qwery-ai \
  --namespace qwery-ai \
  --wait --timeout 5m

# Get the route URL
ROUTE_URL=$(oc get route qwery-ai -n qwery-ai -o jsonpath='{.spec.host}')
echo "Qwery AI URL: https://$ROUTE_URL"
```

## Configuration

### PostgreSQL Configuration

Edit `postgresql-pgvector/values.yaml`:

```yaml
persistence:
  storageClass: "your-storage-class"
  size: 100Gi

resources:
  requests:
    memory: "4Gi"
    cpu: "2"

postgresql:
  password: "YourSecurePassword"
```

### Ollama Configuration

Edit `ollama/values.yaml`:

```yaml
models:
  - llama2
  - nomic-embed-text
  - mistral  # Add more models

persistence:
  size: 100Gi  # Increase for more models
```

### Qwery AI Configuration

Edit `qwery-ai/values.yaml`:

```yaml
replicaCount: 2

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10

config:
  embedding:
    provider: "ollama"
    modelName: "llama2"
```

## Testing

### Test PostgreSQL

```bash
# Connect to database
oc exec -it -n qwery-ai deployment/postgresql-pgvector -- \
  psql -U qweryai -d vectordb

# Inside psql:
# Check pgvector
SELECT * FROM pg_extension WHERE extname='vector';

# Insert test vector
INSERT INTO documents (content, embedding, metadata) 
VALUES ('test', '[0.1,0.2,0.3]', '{"source": "test"}');

# Query vectors
SELECT * FROM documents;
```

### Test Ollama

```bash
# List models
oc exec -n qwery-ai deployment/ollama -- ollama list

# Generate embedding
oc exec -n qwery-ai deployment/ollama -- \
  curl -X POST http://localhost:11434/api/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model": "llama2", "prompt": "Hello world"}'
```

### Test Qwery AI

```bash
# Get route URL
ROUTE_URL=$(oc get route qwery-ai -n qwery-ai -o jsonpath='{.spec.host}')

# Health check
curl -k https://$ROUTE_URL/health

# Add document
curl -k -X POST https://$ROUTE_URL/api/documents \
  -H "Content-Type: application/json" \
  -d '{
    "content": "OpenShift is a Kubernetes platform",
    "metadata": {"source": "docs"}
  }'

# Search documents
curl -k -X POST https://$ROUTE_URL/api/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is OpenShift?",
    "limit": 5
  }'

# Access API documentation
open https://$ROUTE_URL/docs
```

## Monitoring

```bash
# Check all pods
oc get pods -n qwery-ai

# View logs
oc logs -f deployment/qwery-ai -n qwery-ai
oc logs -f deployment/postgresql-pgvector -n qwery-ai
oc logs -f deployment/ollama -n qwery-ai

# Check resource usage
oc adm top pods -n qwery-ai

# Check HPA status
oc get hpa -n qwery-ai
```

## Troubleshooting

### PostgreSQL Issues

```bash
# Check pod status
oc describe pod -n qwery-ai -l app.kubernetes.io/name=postgresql-pgvector

# Check PVC
oc get pvc -n qwery-ai

# Check logs
oc logs -n qwery-ai deployment/postgresql-pgvector --tail=100
```

### Ollama Issues

```bash
# Check if models are downloaded
oc exec -n qwery-ai deployment/ollama -- ollama list

# Re-download models
oc exec -n qwery-ai deployment/ollama -- ollama pull llama2

# Check storage
oc exec -n qwery-ai deployment/ollama -- df -h
```

### Qwery AI Issues

```bash
# Check logs
oc logs -n qwery-ai deployment/qwery-ai --tail=100

# Check database connectivity
oc exec -n qwery-ai deployment/qwery-ai -- \
  curl -v postgresql-pgvector:5432

# Check Ollama connectivity
oc exec -n qwery-ai deployment/qwery-ai -- \
  curl -v http://ollama:11434
```

## Upgrading

```bash
# Upgrade PostgreSQL
helm upgrade postgresql-pgvector ./postgresql-pgvector -n qwery-ai

# Upgrade Ollama
helm upgrade ollama ./ollama -n qwery-ai

# Upgrade Qwery AI
helm upgrade qwery-ai ./qwery-ai -n qwery-ai
```

## Uninstalling

```bash
# Uninstall all components
helm uninstall qwery-ai -n qwery-ai
helm uninstall ollama -n qwery-ai
helm uninstall postgresql-pgvector -n qwery-ai

# Delete PVCs (optional - this will delete all data)
oc delete pvc --all -n qwery-ai

# Delete namespace
oc delete project qwery-ai
```

## Production Considerations

1. **Security**
   - Change default passwords in secrets
   - Enable network policies
   - Use private image registry
   - Enable TLS for all services

2. **High Availability**
   - Use PostgreSQL replication
   - Increase replica count
   - Configure pod anti-affinity

3. **Backup**
   - Schedule regular database backups
   - Backup PVCs
   - Test restore procedures

4. **Monitoring**
   - Enable ServiceMonitor for Prometheus
   - Set up alerts
   - Configure log aggregation

5. **Performance**
   - Use faster storage class
   - Increase resources
   - Optimize database indexes
   - Enable connection pooling

## Support

For issues or questions:
- Check logs: `oc logs -f deployment/<name> -n qwery-ai`
- Review events: `oc get events -n qwery-ai --sort-by='.lastTimestamp'`
- Contact: platform@example.com

## License

Internal use only - Platform Engineering Team
