#!/usr/bin/env bash
# Convert the merged LoRA-merged checkpoint to a Q4_K_M GGUF for Ollama.
set -euo pipefail

MERGED="${1:-/workspace/benchmarks/extraction/sft/output/merged}"
OUT_DIR="${2:-/workspace/benchmarks/extraction/sft/output/gguf}"
NAME="${3:-contexta-lfm-extract}"
WORK=/tmp/llama.cpp

if [ ! -d "$WORK" ]; then
  git clone --depth 1 https://github.com/ggml-org/llama.cpp "$WORK"
fi

if [ ! -x "$WORK/build/bin/llama-quantize" ]; then
  cmake -S "$WORK" -B "$WORK/build" -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF
  cmake --build "$WORK/build" --target llama-quantize -j "$(nproc)"
fi

pip install --quiet --no-cache-dir "gguf>=0.10.0"

mkdir -p "$OUT_DIR"
F16="$OUT_DIR/${NAME}-f16.gguf"
Q4="$OUT_DIR/${NAME}-q4_k_m.gguf"

python "$WORK/convert_hf_to_gguf.py" "$MERGED" --outfile "$F16" --outtype f16
"$WORK/build/bin/llama-quantize" "$F16" "$Q4" Q4_K_M

cp "$MERGED/tokenizer_config.json" "$OUT_DIR/" 2>/dev/null || true
ls -la "$OUT_DIR"
echo "Wrote $Q4"
