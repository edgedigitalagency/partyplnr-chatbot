import os
import re
from difflib import SequenceMatcher

import pandas as pd
import openai
from flask import Flask, request, jsonify, render_template

# ── Config ────────────────────────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_API_KEY")               # .env or Render Secret
CSV_PATH       = os.getenv("VENDORS_CSV_PATH", "VNDRs.csv")

# ── Load vendor list once ─────────────────────────────────────────────
df = pd.read_csv(CSV_PATH).fillna("")

# ── Helpers ───────────────────────────────────────────────────────────
def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def _format_vendor(row: pd.Series) -> str:
    parts = [
        f"**{row.get('Title','Unknown Vendor')}**",
        f"Category : {row.get('Category','')}",
        f"Offers   : {row.get('Offers','')}",
        f"Location : {row.get('Location','')}",
        f"Contact  : {row.get('Contact Info','') or row.get('Phone Number','')}",
        f"Link     : {row.get('link ','')}",
    ]
    return "\n".join(p for p in parts if p.strip())

def _friendly_intro(row: pd.Series) -> str:
    cat  = row.get("Category", "vendor").lower()
    city = row.get("Location", "").split(",")[0]
    return (f"Great! It sounds like you’re looking for a {cat}"
            f"{' in ' + city if city else ''}. 🎉\n\n"
            "Here’s someone on our list who might fit:\n\n")

# ── Local CSV search (now multi-match) ────────────────────────────────
def local_lookup(message: str) -> str | None:
    msg = message.lower()
    seen_cats: set[str] = set()
    results: list[pd.Series] = []

    for _, row in df.iterrows():
        title = str(row.get("Title", "")).lower()
        cat   = str(row.get("Category", "")).strip().lower()

        def matches() -> bool:
            if not cat and not title:
                return False
            # direct substring
            if (cat and cat in msg) or (title and title in msg):
                return True
            # fuzzy word-by-word
            for word in re.findall(r"\w+", msg):
                if _similar(word, cat) >= 0.7 or _similar(word, title) >= 0.7:
                    return True
            return False

        if matches() and cat not in seen_cats:
            results.append(row)
            seen_cats.add(cat)

        if len(results) >= 5:       # cap at 5 suggestions
            break

    if not results:
        return None

    if len(results) == 1:
        return _friendly_intro(results[0]) + _format_vendor(results[0])

    intro = "Here are a few vendors that may help with your request:\n\n"
    body  = "\n\n---\n\n".join(_format_vendor(r) for r in results)
    return intro + body

# ── GPT-4o-mini fallback ──────────────────────────────────────────────
SYSTEM_PROMPT = """
You are PartyPlnr, an assistant that suggests event vendors from a database.
If the CSV has no match, politely say you couldn't find one and invite the user
to try again with different wording. Never invent vendor details not in the CSV.
"""

def ai_fallback(message: str) -> str:
    if not openai.api_key:
        return ("I couldn’t reach the AI right now. "
                "Please try a different keyword like 'photography', 'mobile bar', etc.")
    try:
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": message},
            ],
            max_tokens=200,
        )
        return resp.choices[0].message.content.strip()
    except openai.AuthenticationError:
        return "The AI service isn’t configured yet."

# ── Flask app ─────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")

@app.route("/")
def home() -> str:
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_msg = request.get_json(force=True).get("message", "")
    answer   = local_lookup(user_msg) or ai_fallback(user_msg)
    return jsonify({"response": answer})

# ── Dev entrypoint ────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
