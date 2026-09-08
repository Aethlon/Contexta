import re

STOPWORDS = {
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "with", "by",
    "about", "from", "as", "into", "like", "through", "after", "over",
    "between", "out", "against", "during", "without", "before", "under",
    "around", "among", "and", "or", "but", "if", "then", "else", "so",
    "i", "me", "my", "myself", "we", "us", "our", "ours", "you", "your", "yours",
    "he", "him", "his", "she", "her", "hers", "they", "them", "their", "theirs",
    "it", "its", "have", "has", "had", "having", "ve", "ll", "re", "d", "m",
    "date", "pm", "am", "yeah", "yes", "yep", "thanks", "thank", "hey", "hello",
    "hi", "good", "great", "really", "just", "gonna", "wanna", "gotta", "well",
    "sure", "that", "this", "these", "those", "there", "here", "what", "where",
    "when", "who", "which", "why", "how", "does", "did", "do",
}

def normalize_stem(word: str) -> str:
    w = word.lower().strip(".,;:!?()[]\"'")
    synonyms = {
        "adopting": "adopt", "adoption": "adopt", "children": "child", "kids": "child", "kid": "child",
        "counselor": "counsel", "counseling": "counsel", "reading": "book", "books": "book",
        "liberal": "progressive", "hiking": "hike", "hikes": "hike", "religious": "religion",
        "religions": "religion", "outdoors": "park", "outdoor": "park", "camping": "camp",
        "camped": "camp", "pets": "pet", "paintings": "paint", "painted": "paint", "painting": "paint",
        "moved": "move", "moving": "move", "shoes": "shoe", "drawings": "draw", "drawing": "draw",
        "traits": "personality", "trait": "personality", "ally": "support", "supportive": "support",
    }
    if w in synonyms:
        return synonyms[w]
    for suffix in ("ing", "tion", "tions", "ies", "es", "ed", "s", "or", "er", "ic", "al"):
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            return w[:-len(suffix)]
    return w

def terms(text: str) -> set[str]:
    raw = set(re.findall(r"[a-z0-9]+", text.lower()))
    filtered = {normalize_stem(w) for w in raw if w not in STOPWORDS and len(w) > 1}
    return filtered

def score(query: str, doc: str) -> float:
    q_terms = terms(query)
    d_terms = terms(doc)
    if not q_terms:
        return 0.0
    common_names = {"melanie", "caroline"}
    total_w = 0.0
    matched_w = 0.0
    for t in q_terms:
        w = 0.2 if t in common_names else 1.0
        total_w += w
        if t in d_terms:
            matched_w += w
    return matched_w / total_w if total_w > 0 else 0.0

q = "What pet does Caroline have?"
doc_good = "Caroline: [Date: 3:31 pm on 23 August, 2023] Thanks, Mel! Exciting but kinda nerve-wracking. Parenting's such a big responsibility. And yup, I do- Oscar, my guinea pig. He's been great. How are your pets?"
doc_generic = "Melanie: [Date: 8:56 pm on 20 July, 2023] That's awesome, Caroline! Glad to hear you found a great group where you can have an impact."

print("Good doc score:", score(q, doc_good))
print("Generic doc score:", score(q, doc_generic))
