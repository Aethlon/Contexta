"""LoRA supervised fine-tuning of LFM2.5-1.2B for Contexta claim extraction.

Deliberately dependency-light: a hand-rolled loop plus PEFT avoids TRL version
churn, and it makes the label masking explicit. Only the assistant response is
supervised, so the model learns the extraction contract rather than the prompt.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path
from typing import Any

import torch
from peft import LoraConfig, get_peft_model
from torch.optim import AdamW
from transformers import AutoModelForCausalLM, AutoTokenizer

DEFAULT_BASE = "LiquidAI/LFM2.5-1.2B-Instruct"
DEFAULT_DATA = Path("benchmarks/extraction/sft/data")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def build_features(rows: list[dict[str, Any]], tokenizer: Any, max_len: int) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    skipped = 0
    for row in rows:
        messages = row["messages"]
        prompt_text = tokenizer.apply_chat_template(
            messages[:-1],
            tokenize=False,
            add_generation_prompt=True,
        )
        target_text = messages[-1]["content"] + tokenizer.eos_token
        prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
        target_ids = tokenizer(target_text, add_special_tokens=False)["input_ids"]
        input_ids = prompt_ids + target_ids
        if len(input_ids) > max_len:
            skipped += 1
            continue
        labels = [-100] * len(prompt_ids) + list(target_ids)
        features.append(
            {
                "input_ids": input_ids,
                "labels": labels,
                "row": row,
            }
        )
    if skipped:
        print(f"skipped {skipped} examples longer than {max_len} tokens")
    return features


def collate(features: list[dict[str, Any]], pad_id: int) -> dict[str, Any]:
    width = max(len(item["input_ids"]) for item in features)
    input_ids, labels, mask = [], [], []
    for item in features:
        padding = width - len(item["input_ids"])
        input_ids.append(item["input_ids"] + [pad_id] * padding)
        labels.append(item["labels"] + [-100] * padding)
        mask.append([1] * len(item["input_ids"]) + [0] * padding)
    return {
        "input_ids": torch.tensor(input_ids, dtype=torch.long),
        "labels": torch.tensor(labels, dtype=torch.long),
        "attention_mask": torch.tensor(mask, dtype=torch.long),
    }


def loss_for(model: Any, batch: dict[str, Any], device: torch.device) -> torch.Tensor:
    outputs = model(
        input_ids=batch["input_ids"].to(device),
        attention_mask=batch["attention_mask"].to(device),
        labels=batch["labels"].to(device),
    )
    return outputs.loss


@torch.no_grad()
def evaluate(model: Any, features: list[dict[str, Any]], pad_id: int, device: torch.device) -> float:
    model.eval()
    total, count = 0.0, 0
    for start in range(0, len(features), 4):
        chunk = features[start : start + 4]
        batch = collate(chunk, pad_id)
        total += float(loss_for(model, batch, device))
        count += 1
    model.train()
    return round(total / max(count, 1), 4)


def main() -> int:
    parser = argparse.ArgumentParser(description="LoRA SFT for LFM2.5 claim extraction")
    parser.add_argument("--base-model", default=DEFAULT_BASE)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output-dir", type=Path, default=Path("benchmarks/extraction/sft/output"))
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--max-len", type=int, default=2048)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--merge", action="store_true", help="merge LoRA and save a standalone model")
    args = parser.parse_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise SystemExit("This training script requires a CUDA device.")

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        dtype=torch.bfloat16,
        attn_implementation="eager",
    )
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()

    lora = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "w1", "w2", "w3"],
    )
    model = get_peft_model(model, lora)
    for name, parameter in model.named_parameters():
        if parameter.requires_grad:
            parameter.data = parameter.data.float()
    model.to(device)
    model.print_trainable_parameters()

    train_rows = load_jsonl(args.data_dir / "train.jsonl")
    val_rows = load_jsonl(args.data_dir / "val.jsonl")
    train_features = build_features(train_rows, tokenizer, args.max_len)
    val_features = build_features(val_rows, tokenizer, args.max_len)
    print(f"train features: {len(train_features)}  val features: {len(val_features)}")

    steps_per_epoch = math.ceil(len(train_features) / (args.batch_size * args.grad_accum))
    total_steps = steps_per_epoch * args.epochs
    warmup = min(20, max(1, total_steps // 20))
    parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = AdamW(parameters, lr=args.learning_rate, weight_decay=0.0, betas=(0.9, 0.95))

    def learning_rate_at(step: int) -> float:
        if step < warmup:
            return args.learning_rate * (step + 1) / warmup
        progress = (step - warmup) / max(1, total_steps - warmup)
        return args.learning_rate * (0.5 * (1.0 + math.cos(math.pi * min(progress, 1.0))))

    print(f"steps/epoch: {steps_per_epoch}  total: {total_steps}  warmup: {warmup}")
    print(f"baseline val loss: {evaluate(model, val_features, tokenizer.pad_token_id, device)}")

    model.train()
    step = 0
    order: list[int] = []
    history: list[dict[str, Any]] = []
    started = time.time()
    for epoch in range(args.epochs):
        order = list(range(len(train_features)))
        random.shuffle(order)
        optimizer.zero_grad(set_to_none=True)
        running, seen = 0.0, 0
        for index in order:
            batch = collate([train_features[index]], tokenizer.pad_token_id)
            loss = loss_for(model, batch, device)
            (loss / args.grad_accum).backward()
            running += float(loss)
            seen += 1
            if seen % args.grad_accum == 0:
                for group in optimizer.param_groups:
                    group["lr"] = learning_rate_at(step)
                torch.nn.utils.clip_grad_norm_(parameters, 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                step += 1
                if step % 10 == 0:
                    elapsed = time.time() - started
                    print(
                        f"epoch {epoch + 1} step {step}/{total_steps} "
                        f"loss {running / max(seen, 1):.4f} "
                        f"lr {optimizer.param_groups[0]['lr']:.2e} "
                        f"elapsed {elapsed / 60:.1f}m"
                    )
        val_loss = evaluate(model, val_features, tokenizer.pad_token_id, device)
        history.append(
            {
                "epoch": epoch + 1,
                "train_loss": round(running / max(seen, 1), 4),
                "val_loss": val_loss,
                "minutes": round((time.time() - started) / 60, 2),
            }
        )
        print(f"epoch {epoch + 1} done: {json.dumps(history[-1])}")
        model.save_pretrained(str(args.output_dir / f"adapter-epoch{epoch + 1}"))

    model.save_pretrained(str(args.output_dir / "adapter-final"))
    (args.output_dir / "history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")

    if args.merge:
        merged = model.merge_and_unload()
        merged = merged.to(torch.bfloat16)
        merged_path = args.output_dir / "merged"
        merged.save_pretrained(str(merged_path), safe_serialization=True)
        tokenizer.save_pretrained(str(merged_path))
        print(f"merged model saved to {merged_path}")

    print(json.dumps({"history": history, "output_dir": str(args.output_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
