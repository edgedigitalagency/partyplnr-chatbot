import os
import pandas as pd
import openai
from flask import Flask, request, jsonify, render_template

# --- Config ---
openai.api_key = os.getenv("OPENAI_API_KEY")          # set in .env or Render secret
CSV_PATH = os.getenv("VENDORS_CSV_PATH", "VNDRs.csv") # override if you move the CSV

# --- Load vendor database once at startup ---
df = pd.read_csv(CSV_PATH).fillna("")

def _format_vendor(row: pd.Series) -> str:
    """Nicely format a single vendor row for chat output."""
    parts = [
        f"**{row.get('Title','Unknown Vendor')}**",
        f"Category  : {row.get('Category','')}",
        f"Offers    : {row.get('Offers','')}",
        f"Location  : {row.get('Location','')}",
        f"Contact   : {row.get('Contact Info','') or row.get('Phone Number','')}",
        f"Link      : {row.get('link ','')}",
    ]
    return "\n".join([p for p in parts if p.strip()])

def local_lookup(message: str) -> str | None:
    """Quick pass through the CSV; return formatted vendor if we find a match."""
    msg = message.lower()
    for _, row in df.iterrows():
        title    = str(row.get("Title",    "")).lower()
        category = str(row.get("Category", "")).lower()
        if title and title in msg:
            return _format_vendor(row)
        if category and category in msg:
            return _format_vendor(row)
    return None

SYSTEM_PROMPT = """
You are PartyPlnr, a helpful assistant that suggests event vendors from a database.
When no match exists, politely say you couldn't find one and encourage the user to try
another query. Never invent vendor details that are not in the CSV.
"""

def ai_fallback(message: str) -> str:
    """Ask GPT-4o-mini for help when the CSV had no matches."""
    completion = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": message}
        ],
        max_tokens=200,
    )
    return completion.choices[0].message.content.strip()

# --- Flask ---
app = Flask(__name__, template_folder="templates", static_folder="static")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_msg = request.get_json(force=True).get("message", "")
    answer = local_lookup(user_msg) or ai_fallback(user_msg)
    return jsonify({"response": answer})

if __name__ == "__main__":
    # local dev → python app.py
    app.run(host="0.0.0.0", port=10000, debug=True)

import re
from difflib import SequenceMatcher

def similar(a, b):               # quick similarity score 0-1
    return SequenceMatcher(None, a, b).ratio()

def local_lookup(message: str) -> str | None:
    msg = message.lower()

    for _, row in df.iterrows():
        title    = str(row.get("Title",    "")).lower()
        category = str(row.get("Category", "")).lower()

        # direct substring match
        if title and title in msg or category and category in msg:
            return _format_vendor(row)

        # fuzzy match ≥ 0.7 (“photographer” ≈ “photography”)
        for word in re.findall(r"\w+", msg):
            if similar(word, category) >= 0.7 or similar(word, title) >= 0.7:
                return _format_vendor(row)
    return None

def ai_fallback(message: str) -> str:
    if not openai.api_key:
        return ("I couldn't reach the AI right now. "
                "Please try a different keyword (e.g. 'photography', "
                "'mobile bar', 'venue', etc.).")

    try:
        completion = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": message}
            ],
            max_tokens=200,
        )
        return completion.choices[0].message.content.strip()
    except openai.AuthenticationError:
        return "The AI service isn’t configured yet."
