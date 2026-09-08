import json

data = json.load(open("benchmarks/locomo/results.json", encoding="utf-8"))
falses = [q for q in data["questions"] if not q["correct"]]
print(f"Total failed: {len(falses)}")

by_cat = {}
for q in falses:
    cat = q["category"]
    by_cat.setdefault(cat, []).append(q)

for cat, items in sorted(by_cat.items()):
    print(f"\n=== Category {cat} ({len(items)} failures) ===")
    for item in items:
        q = item["question"]
        gold = item.get("gold_answer")
        adv = item.get("adversarial_answer")
        ans = item.get("generated_answer", "")
        # print first 200 chars of ans
        ans_short = ans.replace("\n", " ")[:200] if ans else ""
        print(f"Q: {q}")
        print(f"   Gold: {gold}")
        if adv:
            print(f"   Adv: {adv}")
        print(f"   Ans: {ans_short}")
