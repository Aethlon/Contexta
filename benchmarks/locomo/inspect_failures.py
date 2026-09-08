import json
import re

data = json.load(open("benchmarks/locomo/results.json", encoding="utf-8"))
falses = [q for q in data["questions"] if not q["correct"]]
print(f"Total failed: {len(falses)}")

# Also let's inspect locomo10.json to see what turns exist for these questions
locomo_data = json.load(open("benchmarks/locomo/data/locomo10.json", encoding="utf-8"))
c0 = locomo_data[0]["conversation"]
qa0 = locomo_data[0]["qa"]

for item in falses:
    q = item["question"]
    gold = str(item.get("gold_answer", "")).lower()
    gen = str(item.get("generated_answer", "")).lower()
    cat = item["category"]
    print(f"\n--- [{cat}] {q} ---")
    print(f"  Gold: {gold}")
    print(f"  Gen: {gen[:160]}")
