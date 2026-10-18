#!/usr/bin/env bash
# Idempotent Cloud Run deployment script for Stark Food Services MCP server (sfs-mcp).
# Containerizes MCP Toolbox for Databases (v1.14.0) with tools.yaml via the
# Artifact Registry OCI/Docker v2 API (no local Docker daemon or Cloud Build
# service-account IAM changes required) and deploys to Cloud Run in us-central1
# running as sfs-toolbox-sa with authentication REQUIRED.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROJECT_ID="${BQ_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
REGION="${CLOUD_RUN_REGION:-us-central1}"
SERVICE_NAME="${CLOUD_RUN_SERVICE:-sfs-mcp}"
AR_REPO="${AR_REPO:-sfs-mcp}"
TOOLBOX_VERSION="${TOOLBOX_VERSION:-1.14.0}"
SA_NAME="sfs-toolbox-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${SERVICE_NAME}:${TOOLBOX_VERSION}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "ERROR: No active GCP project configured. Set BQ_PROJECT_ID or run 'gcloud config set project <PROJECT_ID>'." >&2
  exit 1
fi

echo "======================================================================"
echo "Deploying Stark Food Services MCP Server to Cloud Run"
echo "  Project         : ${PROJECT_ID}"
echo "  Region          : ${REGION}"
echo "  Service         : ${SERVICE_NAME}"
echo "  Service Account : ${SA_EMAIL}"
echo "  Image           : ${IMAGE_URI}"
echo "  Auth            : REQUIRED (--no-allow-unauthenticated)"
echo "======================================================================"

# 1. Ensure Artifact Registry repository exists
if ! gcloud artifacts repositories describe "${AR_REPO}" \
  --project="${PROJECT_ID}" \
  --location="${REGION}" >/dev/null 2>&1; then
  echo "[deploy] Creating Artifact Registry repository '${AR_REPO}' in ${REGION}..."
  gcloud artifacts repositories create "${AR_REPO}" \
    --project="${PROJECT_ID}" \
    --location="${REGION}" \
    --repository-format=docker \
    --description="Stark Food Services MCP Toolbox container repository"
else
  echo "[deploy] Artifact Registry repository '${AR_REPO}' already exists."
fi

# 2. Package us-central1-docker.pkg.dev/database-toolbox/toolbox/toolbox:${TOOLBOX_VERSION}
#    + /app/tools.yaml and push directly to Artifact Registry
echo "[deploy] Packaging ${IMAGE_URI} with tools.yaml..."
REPO_ROOT="${REPO_ROOT}" PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" \
AR_REPO="${AR_REPO}" SERVICE_NAME="${SERVICE_NAME}" TOOLBOX_VERSION="${TOOLBOX_VERSION}" \
python3 - <<'PYEOF'
import gzip, hashlib, io, json, os, subprocess, tarfile, tempfile
from pathlib import Path

repo_root = Path(os.environ["REPO_ROOT"])
project_id = os.environ["PROJECT_ID"]
region = os.environ["REGION"]
ar_repo = os.environ["AR_REPO"]
service_name = os.environ["SERVICE_NAME"]
tag = os.environ["TOOLBOX_VERSION"]

token = subprocess.check_output(["gcloud", "auth", "print-access-token"]).decode().strip()
src_repo = "database-toolbox/toolbox/toolbox"
dst_repo = f"{project_id}/{ar_repo}/{service_name}"
registry = f"https://{region}-docker.pkg.dev/v2"
tools_yaml = (repo_root / "tools.yaml").read_bytes()

def curl_get(url, accept="*/*"):
    return subprocess.check_output([
        "curl", "-fsSL",
        "-H", f"Authorization: Bearer {token}",
        "-H", f"Accept: {accept}",
        url
    ])

def upload_blob(data: bytes, digest: str):
    chk = subprocess.run(
        ["curl", "-fsSI", "-H", f"Authorization: Bearer {token}", f"{registry}/{dst_repo}/blobs/{digest}"],
        capture_output=True
    )
    if chk.returncode == 0:
        return
    headers = subprocess.check_output([
        "curl", "-fsSL", "-D", "-", "-o", "/dev/null", "-X", "POST",
        "-H", f"Authorization: Bearer {token}",
        f"{registry}/{dst_repo}/blobs/uploads/"
    ]).decode()
    loc = next(
        line.split(":", 1)[1].strip()
        for line in headers.splitlines()
        if line.lower().startswith("location:")
    )
    if loc.startswith("/"):
        loc = f"https://{region}-docker.pkg.dev{loc}"
    sep = "&" if "?" in loc else "?"
    put_url = f"{loc}{sep}digest={digest}"
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(data)
        tf.flush()
        subprocess.check_call([
            "curl", "-fsSL", "-X", "PUT",
            "-H", f"Authorization: Bearer {token}",
            "-H", "Content-Type: application/octet-stream",
            "--data-binary", f"@{tf.name}",
            put_url
        ])

def mount_or_copy_blob(digest: str):
    chk = subprocess.run(
        ["curl", "-fsSI", "-H", f"Authorization: Bearer {token}", f"{registry}/{dst_repo}/blobs/{digest}"],
        capture_output=True
    )
    if chk.returncode == 0:
        return
    res = subprocess.run([
        "curl", "-fsSL", "-D", "-", "-o", "/dev/null", "-X", "POST",
        "-H", f"Authorization: Bearer {token}",
        f"{registry}/{dst_repo}/blobs/uploads/?mount={digest}&from={src_repo}"
    ], capture_output=True, text=True)
    if res.returncode == 0 and "201 " in res.stdout:
        return
    blob = curl_get(f"{registry}/{src_repo}/blobs/{digest}")
    upload_blob(blob, digest)

idx = json.loads(curl_get(
    f"{registry}/{src_repo}/manifests/{tag}",
    "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json"
))
amd64_entry = next(
    m for m in idx["manifests"]
    if m.get("platform", {}).get("os") == "linux" and m.get("platform", {}).get("architecture") == "amd64"
)
manifest = json.loads(curl_get(f"{registry}/{src_repo}/manifests/{amd64_entry['digest']}", amd64_entry["mediaType"]))
config = json.loads(curl_get(f"{registry}/{src_repo}/blobs/{manifest['config']['digest']}"))

for layer in manifest["layers"]:
    mount_or_copy_blob(layer["digest"])

tar_buf = io.BytesIO()
with tarfile.open(fileobj=tar_buf, mode="w") as tf:
    ti = tarfile.TarInfo(name="app/tools.yaml")
    ti.size = len(tools_yaml)
    ti.mode = 0o644
    ti.uid = 65532
    ti.gid = 65532
    tf.addfile(ti, io.BytesIO(tools_yaml))
uncompressed_tar = tar_buf.getvalue()
diff_id = "sha256:" + hashlib.sha256(uncompressed_tar).hexdigest()

gz_buf = io.BytesIO()
with gzip.GzipFile(filename="", mode="wb", fileobj=gz_buf, mtime=0) as gz:
    gz.write(uncompressed_tar)
compressed_layer = gz_buf.getvalue()
layer_digest = "sha256:" + hashlib.sha256(compressed_layer).hexdigest()
upload_blob(compressed_layer, layer_digest)

config["rootfs"]["diff_ids"].append(diff_id)
config.setdefault("config", {})["Cmd"] = ["--config", "/app/tools.yaml", "--address", "0.0.0.0", "--port", "8080"]
config["config"]["ExposedPorts"] = {"8080/tcp": {}}
new_config_bytes = json.dumps(config, separators=(",", ":")).encode("utf-8")
new_config_digest = "sha256:" + hashlib.sha256(new_config_bytes).hexdigest()
upload_blob(new_config_bytes, new_config_digest)

layer_mt = manifest["layers"][0]["mediaType"]
manifest["config"]["digest"] = new_config_digest
manifest["config"]["size"] = len(new_config_bytes)
manifest["layers"].append({
    "mediaType": layer_mt,
    "digest": layer_digest,
    "size": len(compressed_layer)
})
new_manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
with tempfile.NamedTemporaryFile() as tf:
    tf.write(new_manifest_bytes)
    tf.flush()
    subprocess.check_call([
        "curl", "-fsSL", "-X", "PUT",
        "-H", f"Authorization: Bearer {token}",
        "-H", f"Content-Type: {manifest['mediaType']}",
        "--data-binary", f"@{tf.name}",
        f"{registry}/{dst_repo}/manifests/{tag}"
    ])
print(f"[deploy] Pushed image {region}-docker.pkg.dev/{dst_repo}:{tag}")
PYEOF

# 3. Deploy to Cloud Run with authentication REQUIRED
echo "[deploy] Deploying Cloud Run service '${SERVICE_NAME}' in ${REGION}..."
gcloud run deploy "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${IMAGE_URI}" \
  --service-account="${SA_EMAIL}" \
  --no-allow-unauthenticated \
  --port=8080 \
  --cpu=1 \
  --memory=512Mi \
  --min-instances=0 \
  --max-instances=5

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format='value(status.url)')"

echo ""
echo "======================================================================"
echo "Cloud Run Deployment Complete"
echo "  Base URL : ${SERVICE_URL}"
echo "  MCP URL  : ${SERVICE_URL}/mcp"
echo "======================================================================"
