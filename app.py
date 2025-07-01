import os, re
from difflib import SequenceMatcher
import pandas as pd
import openai
from flask import Flask, request, jsonify, render_template

# ── config ────────────────────────────────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_API_KEY")          # set on Render → Env Vars
CSV_PATH       = os.getenv("VENDORS_CSV_PATH", "VNDRs.csv")

# ── load CSV once at startup ─────────────────────────────────────────────────
df = pd.read_csv(CSV_PATH).fillna("")

def _format_vendor(row: pd.Series) -> str:
    parts = [
        f"**{row.get('Title','Unknown Vendor')}**",
        f"Category  : {row.get('Category','')}",
        f"Offers    : {row.get('Offers','')}",
        f"Location  : {row.get('Location','')}",
        f"Contact   : {row.get('Contact Info','') or row.get('Phone Number','')}",
        f"Link      : {row.get('link ','')}",
    ]
    return "\n".join([p for p in parts if p.strip()])

# ── local fuzzy search ───────────────────────────────────────────────────────
def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def local_lookup(message: str) -> str | None:
    msg = message.lower()

    for _, row in df.iterrows():
        title    = str(row.get("Title",    "")).lower()
        category = str(row.get("Category", "")).lower()

        # direct substring hit
        if title and title in msg or category and category in msg:
            return _format_vendor(row)

        # fuzzy ≥ 0.7  (e.g. “photographer” vs “photography”)
        for word in re.findall(r"\w+", msg):
            if _similar(word, category) >= 0.7 or _similar(word, title) >= 0.7:
                return _format_vendor(row)
    return None

# ── OpenAI fallback ──────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are PartyPlnr, a helpful assistant suggesting event vendors from a database.
If no match exists, politely say so and suggest the user try another query.
Never invent vendor details that are not in the CSV.
"""

def ai_fallback(message: str) -> str:
    if not openai.api_key:   # graceful when key isn’t set
        return ("I couldn’t reach the AI right now. "
                "Try a different keyword (e.g. “photography”, “mobile bar”, “venue”).")

    try:
        completion = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": message},
            ],
            max_tokens=200,
        )
        return completion.choices[0].message.content.strip()
    except openai.AuthenticationError:
        return "The AI service isn’t configured yet."

# ── Flask app ────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_msg = request.get_json(force=True).get("message", "")
    answer   = local_lookup(user_msg) or ai_fallback(user_msg)
    return jsonify({"response": answer})

# local testing only:  python app.py
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
