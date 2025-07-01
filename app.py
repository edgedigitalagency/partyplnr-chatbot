import os
import re
from difflib import SequenceMatcher

import pandas as pd
import openai
from flask import Flask, request, jsonify, render_template

# ── Config ────────────────────────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_API_KEY")          # set in .env or Render secret
CSV_PATH       = os.getenv("VENDORS_CSV_PATH", "VNDRs.csv")

# ── Load vendor list once at startup ──────────────────────────────────
df = pd.read_csv(CSV_PATH).fillna("")

def _format_vendor(row: pd.Series) -> str:
    """Markdown-ish block for a single vendor."""
    parts = [
        f"**{row.get('Title','Unknown Vendor')}**",
        f"Category : {row.get('Category','')}",
        f"Offers   : {row.get('Offers','')}",
        f"Location : {row.get('Location','')}",
        f"Contact  : {row.get('Contact Info','') or row.get('Phone Number','')}",
        f"Link     : {row.get('link ','')}",
    ]
    return "\n".join(p for p in parts if p.strip())

def _friendly_intro(row: pd.Series, user_msg: str) -> str:
    """Short human greeting that precedes the vendor block."""
    cat  = row.get("Category", "vendor").lower()
    city = row.get("Location", "").split(",")[0]  # “Houston, TX” → “Houston”
    return (
        f"Great! It sounds like you’re looking for a {cat}"
        f"{' in ' + city if city else ''}. 🎉\n\n"
        "Here’s someone on our list who might fit:\n\n"
    )

def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def local_lookup(message: str) -> str | None:
    """Search the CSV (substring + fuzzy) and return a formatted match."""
    msg = message.lower()

    for _, row in df.iterrows():
        title    = str(row.get("Title",    "")).lower()
        category = str(row.get("Category", "")).lower()

        # exact substring
        if (title and title in msg) or (category and category in msg):
            return _friendly_intro(row, message) + _format_vendor(row)

        # fuzzy ≥ 0.7  (“photographer” vs “photography”)
        for word in re.findall(r"\w+", msg):
            if _similar(word, category) >= 0.7 or _similar(word, title) >= 0.7:
                return _friendly_intro(row, message) + _format_vendor(row)

    return None  # nothing in CSV

SYSTEM_PROMPT = """
You are PartyPlnr, an assistant that suggests event vendors from a database.
If no match exists, politely say you couldn't find one and invite the user
to try another query. Never invent vendor details that are not in the CSV.
"""

def ai_fallback(message: str) -> str:
    """Ask GPT-4o-mini when the CSV comes up empty (or return an error string)."""
    if not openai.api_key:
        return ("I couldn’t reach the AI right now. "
                "Try another keyword like 'photography', 'mobile bar', etc.")
    try:
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": message}
            ],
            max_tokens=200,
        )
        return resp.choices[0].message.content.strip()
    except openai.AuthenticationError:
        return "The AI service isn’t configured yet."

# ── Flask app ──────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_msg = request.get_json(force=True).get("message", "")
    answer   = local_lookup(user_msg) or ai_fallback(user_msg)
    return jsonify({"response": answer})

# ── Dev entrypoint ─────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
