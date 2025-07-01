import os
import re
from difflib import SequenceMatcher
import pandas as pd
import openai
from flask import Flask, request, jsonify, render_template

# ── Configuration ────────────────────────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_API_KEY")               # set in Render “Secrets”
CSV_PATH       = os.getenv("VENDORS_CSV_PATH", "VNDRs.csv")  # path to vendor CSV
MODEL          = "gpt-3.5-turbo"                            # only used if key present

# ── Load vendor database once at startup ─────────────────────────────────────
df = pd.read_csv(CSV_PATH).fillna("")

# ── Helper functions ─────────────────────────────────────────────────────────
def _fmt(row: pd.Series) -> str:
    """Pretty-print a single vendor row."""
    lines = [
        f"**{row.get('Title', 'Unknown Vendor')}**",
        f"Category : {row.get('Category', '')}",
        f"Offers   : {row.get('Offers', '')}",
        f"Location : {row.get('Location', '')}",
        f"Contact  : {row.get('Contact Info', '') or row.get('Phone Number', '')}",
        f"Link     : {row.get('link ', '')}",
    ]
    return "\n".join(l for l in lines if l.split(':',1)[1].strip())

def similar(a: str, b: str) -> float:
    """Quick fuzzy similarity score (0–1)."""
    return SequenceMatcher(None, a, b).ratio()

def local_lookup(message: str) -> str | None:
    """Return best-matching vendor (fuzzy on Title + Category) or None."""
    msg = message.lower()
    best = None
    best_score = 0.0

    for _, row in df.iterrows():
        for field in ("Title", "Category"):
            target = str(row.get(field, "")).lower()
            # score each word against the target
            score = max(similar(word, target) for word in re.findall(r"\w+", msg))
            if score >= 0.7 and score > best_score:
                best_score, best = score, row

    return _fmt(best) if best is not None else None   # ← fixed line

SYSTEM_PROMPT = (
    "You are PartyPlnr, a helpful assistant that suggests event vendors from "
    "our database. If none match, politely say so and prompt the user for a "
    "different keyword or location. Never invent vendor details."
)

def ai_fallback(message: str) -> str:
    """Call OpenAI if a key is set; otherwise return a polite fallback message."""
    if not openai.api_key:
        return ("Sorry, I couldn't find a matching vendor. "
                "Try another keyword like 'photographer', 'bakery', or a city name!")
    try:
        completion = openai.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": message},
            ],
            max_tokens=200,
            temperature=0.7,
        )
        return completion.choices[0].message.content.strip()
    except openai.OpenAIError as err:
        # covers quota errors, etc.
        return (f"I couldn't reach the AI service ({err}). "
                "Please try a different keyword.")

# ── Flask app ────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user = request.get_json(force=True).get("message", "").strip()
    hit  = local_lookup(user)

    reply = hit if hit else ai_fallback(user)
    return jsonify({"response": reply})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
