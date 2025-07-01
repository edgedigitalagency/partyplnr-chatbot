import os, re
from difflib import SequenceMatcher
import pandas as pd
import openai
from flask import Flask, request, jsonify, render_template

# ── Config ──────────────────────────────────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_API_KEY")          # set in .env or Render
CSV_PATH        = os.getenv("VENDORS_CSV_PATH", "VNDRs.csv")
MODEL           = "gpt-4o-mini"                       # swap if you like
MAX_MATCHES     = 5                                   # rows to hand GPT

# ── Load vendor database once at startup ───────────────────────────────────────
df = pd.read_csv(CSV_PATH).fillna("")

# ── Helpers ────────────────────────────────────────────────────────────────────
def _format_vendor(row: pd.Series) -> str:
    """Return a plain-text block for one vendor (fed to GPT)."""
    parts = [
        f"**{row.get('Title','Unknown Vendor')}**",
        f"Category : {row.get('Category','')}",
        f"Offers   : {row.get('Offers','')}",
        f"Location : {row.get('Location','')}",
        f"Contact  : {row.get('Contact Info','') or row.get('Phone Number','')}",
        f"Link     : {row.get('link ','')}",
    ]
    return "\n".join([p for p in parts if p.strip()])

def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def _collect_rows(msg: str) -> list[pd.Series]:
    """Return up to MAX_MATCHES vendor rows that look relevant."""
    msg_low = msg.lower()
    hits = []

    for _, row in df.iterrows():
        title    = str(row.get("Title",    "")).lower()
        category = str(row.get("Category", "")).lower()

        # direct hits
        if title and title in msg_low or category and category in msg_low:
            hits.append(row)
            continue

        # fuzzy fallback  (≥ 0.7 means fairly close)
        for word in re.findall(r"\w+", msg_low):
            if _similar(word, category) >= 0.7 or _similar(word, title) >= 0.7:
                hits.append(row)
                break

        if len(hits) >= MAX_MATCHES:
            break
    return hits

SYSTEM_PROMPT = (
    "You are PartyPlnr, an upbeat but concise assistant that helps users find "
    "event vendors.\n"
    "• If I give you vendor blocks, turn them into a short friendly answer.\n"
    "• Use second-person voice (“you”), one emoji max, ≤ 150 words.\n"
    "• If I say NO_VENDOR_FOUND, politely apologise and suggest trying other "
    "keywords or locations.\n"
    "Never invent vendor details that aren’t in the blocks."
)

def _ask_gpt(user_msg: str, vendor_blocks: str) -> str:
    """Let GPT-4o draft the final chat response."""
    completion = openai.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",
             "content": f"User asked:\n{user_msg}\n\nVendor blocks:\n{vendor_blocks}"}
        ],
        max_tokens=200,
        temperature=0.7,
    )
    return completion.choices[0].message.content.strip()

# ── Flask app ───────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_msg = request.get_json(force=True).get("message", "")

    rows = _collect_rows(user_msg)
    if rows:
        blocks = "\n\n---\n\n".join(_format_vendor(r) for r in rows)
    else:
        blocks = "NO_VENDOR_FOUND"

    reply = _ask_gpt(user_msg, blocks)
    return jsonify({"response": reply})

# ── Local dev runner ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
