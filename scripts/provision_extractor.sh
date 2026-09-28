#!/bin/sh
# Provision the fine-tuned extractor into Ollama. Idempotent.
#
# Contexta's extraction model is a LoRA fine-tune of LiquidAI/LFM2.5-1.2B that
# was merged and quantised to Q4_K_M. Ollama has to be told about that GGUF once
# per volume, and forgetting to is the single most common reason a fresh install
# silently degrades to the regex fallback assembler: the stack accepts
# observations, extraction returns nothing usable, and no container reports why.
#
# This runs as a one-shot container before the inference server starts, so a
# first boot needs no manual step.
#
# Two sources, tried in order:
#   1. a registry reference (CONTEXTA_EXTRACTOR_MODEL_REF), e.g.
#        ghcr.io/contexta/contexta-lfm-extract:latest
#      pulled with `ollama pull`. This is the path that makes a one-command
#      install work for someone who has never run this before.
#   2. a local GGUF (CONTEXTA_EXTRACTOR_GGUF, default /models/contexta-lfm-extract-q4_k_m.gguf)
#      created with `ollama create`. This is the path for someone who has the
#      weights already, or who wants to run fully air-gapped.
#
# Exits 0 if the model ends up present, non-zero if it does not — so Compose
# reports the failure instead of starting a server that cannot extract.

set -eu

MODEL="${CONTEXTA_INFERENCE_MODEL:-contexta-lfm-extract}"
OLLAMA_HOST="${CONTEXTA_INFERENCE_OLLAMA_URL:-http://ollama:11434}"
GGUF="${CONTEXTA_EXTRACTOR_GGUF:-/models/contexta-lfm-extract-q4_k_m.gguf}"
MODELFILE="${CONTEXTA_EXTRACTOR_MODELFILE:-/models/Modelfile}"
REGISTRY_REF="${CONTEXTA_EXTRACTOR_MODEL_REF:-}"
OLLAMA_BIN="${OLLAMA_BIN:-ollama}"
export OLLAMA_HOST

log() { echo "[provision-extractor] $*"; }

wait_for_ollama() {
  i=0
  while [ "$i" -lt 120 ]; do
    if "$OLLAMA_BIN" list >/dev/null 2>&1; then
      return 0
    fi
    i=$((i + 1))
    sleep 2
  done
  log "ERROR: Ollama did not become ready at $OLLAMA_HOST"
  return 1
}

model_present() {
  "$OLLAMA_BIN" list 2>/dev/null | awk 'NR>1 {print $1}' | grep -q "^${MODEL%%:*}"
}

create_from_gguf() {
  [ -f "$GGUF" ] || return 1
  [ -f "$MODELFILE" ] || return 1
  log "creating '$MODEL' from local GGUF $GGUF"
  tmp="$(mktemp -d)"
  cp "$MODELFILE" "$tmp/Modelfile"
  # The Modelfile references the GGUF by relative name, so place both together.
  cp "$GGUF" "$tmp/$(basename "$GGUF")"
  ( cd "$tmp" && "$OLLAMA_BIN" create "$MODEL" -f Modelfile )
  rm -rf "$tmp"
}

main() {
  log "target model: $MODEL"
  log "ollama host : $OLLAMA_HOST"

  wait_for_ollama || exit 1

  if model_present; then
    log "already present, nothing to do"
    exit 0
  fi

  if [ -n "$REGISTRY_REF" ]; then
    log "pulling from registry: $REGISTRY_REF"
    if "$OLLAMA_BIN" pull "$REGISTRY_REF"; then
      # `pull` stores it under the reference name, so alias it to the short name
      # the inference server asks for. Copy is preferred: it keeps both.
      if "$OLLAMA_BIN" cp "$REGISTRY_REF" "$MODEL" 2>/dev/null; then
        log "copied $REGISTRY_REF -> $MODEL"
      else
        log "note: could not copy $REGISTRY_REF to $MODEL; set CONTEXTA_INFERENCE_MODEL=$REGISTRY_REF if the short name does not resolve"
      fi
      log "done"
      exit 0
    fi
    log "registry pull failed, falling back to a local GGUF"
  fi

  if create_from_gguf; then
    log "done"
    exit 0
  fi

  cat >&2 <<EOF
[provision-extractor] ERROR: could not provision '$MODEL'.

Neither source was available:
  - registry ref: ${REGISTRY_REF:-<unset>}
  - local GGUF   : $GGUF$( [ -f "$GGUF" ] || echo " (missing)" )

Do one of:
  1. Set CONTEXTA_EXTRACTOR_MODEL_REF to a published Ollama model, e.g.
       CONTEXTA_EXTRACTOR_MODEL_REF=ghcr.io/contexta/contexta-lfm-extract:latest
  2. Drop the Q4_K_M GGUF and its Modelfile into ./models/ (host ./models maps
     to /models), producing:
       models/contexta-lfm-extract-q4_k_m.gguf
       models/Modelfile
  3. Build them yourself with benchmarks/extraction/sft/export_gguf.sh

Until then the worker will fall back to a regex assembler and extraction
quality will be poor. This is the only manual step in a first boot.
EOF
  exit 1
}

main "$@"
