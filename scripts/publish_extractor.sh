#!/usr/bin/env bash
# Build a distributable Contexta extractor image, and optionally push it.
#
# `docker compose up` provisions the extractor automatically from a local GGUF
# or a registry ref. This script is the missing half for people who do not have
# the GGUF: it turns the fine-tune into a tiny image that provisions itself.
#
#   scripts/publish_extractor.sh                     # build ./dist/extractor
#   scripts/publish_extractor.sh --push ghcr.io/... # build, tag, push
#
# The image is deliberately small: the Modelfile plus a `FROM` that pulls the
# GGUF from a published location, so the GGUF is stored once in a registry rather
# than duplicated in a Docker layer. If you would rather ship the GGUF inside
# the image, use --embed and expect a ~700 MB image.

set -euo pipefail

NAME="${CONTEXTA_EXTRACTOR_MODEL:-contexta-lfm-extract}"
GGUF_REL="contexta-lfm-extract-q4_k_m.gguf"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$REPO_ROOT/dist/extractor"
GGUF_URL="${CONTEXTA_EXTRACTOR_GGUF_URL:-}"
PUSH_REF=""
EMBED=0

while [ $# -gt 0 ]; do
  case "$1" in
    --push) PUSH_REF="$2"; shift 2 ;;
    --gguf-url) GGUF_URL="$2"; shift 2 ;;
    --embed) EMBED=1; shift ;;
    --name) NAME="$2"; shift 2 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

LOCAL_GGUF="$REPO_ROOT/models/$GGUF_REL"
MODELFILE="$REPO_ROOT/models/Modelfile"

if [ ! -f "$MODELFILE" ]; then
  echo "error: $MODELFILE not found." >&2
  echo "  Produce it with:  benchmarks/extraction/sft/export_gguf.sh" >&2
  exit 1
fi

if [ "$EMBED" -eq 1 ]; then
  if [ ! -f "$LOCAL_GGUF" ]; then
    echo "error: --embed needs $LOCAL_GGUF" >&2
    exit 1
  fi
  cp "$MODELFILE" "$WORK/Modelfile"
  cp "$LOCAL_GGUF" "$WORK/$GGUF_REL"
  echo "==> embedding the GGUF (image will be ~700 MB)"
else
  if [ -z "$GGUF_URL" ]; then
    echo "error: pass --gguf-url <https url to $GGUF_REL>" >&2
    echo "       or pass --embed to bake in ./models/$GGUF_REL" >&2
    exit 1
  fi
  # Rewrite the FROM line to the published URL.
  sed "s#^FROM .*#FROM $GGUF_URL#" "$MODELFILE" > "$WORK/Modelfile"
  echo "==> pointing at $GGUF_URL"
fi

cat > "$WORK/Dockerfile" <<'DOCKERFILE'
FROM ollama/ollama:0.12.3
COPY Modelfile /tmp/Modelfile
# Runs as the ollama service on container start. The provisioning script the
# compose stack uses checks `ollama list` first, so this is idempotent with it.
CMD ["sh", "-c", "ollama serve & until ollama list >/dev/null 2>&1; do sleep 1; done; \
     ollama list | grep -q contexta-lfm-extract || \
     (cd /tmp && ollama create contexta-lfm-extract -f Modelfile); tail -f /dev/null"]
DOCKERFILE

mkdir -p "$OUT_DIR"
echo "==> building $NAME"
docker build -t "$NAME:latest" "$WORK"

if [ -n "$PUSH_REF" ]; then
  echo "==> tagging $PUSH_REF"
  docker tag "$NAME:latest" "$PUSH_REF"
  echo "==> pushing (this is the step that makes `docker compose up` work for everyone)"
  docker push "$PUSH_REF"
  cat <<EOF

Done. To make a fresh clone work with no manual steps, put this in .env:

  CONTEXTA_EXTRACTOR_MODEL_REF=$PUSH_REF

scripts/provision_extractor.sh will then `ollama pull` it on first boot instead
of looking for a local GGUF.
EOF
else
  cat <<EOF

Built $NAME:latest. Try it locally with:

  docker run -d --name ctx-extractor $NAME:latest

To publish it, re-run with:

  scripts/publish_extractor.sh --push <registry>/<repo> --gguf-url <url>
EOF
fi
