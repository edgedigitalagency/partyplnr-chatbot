import os
import re
from difflib import SequenceMatcher

import pandas as pd
from flask import Flask, request, jsonify, render_template

# ---------------------------------------------------------------------------
#  Data ---------------------------------------------------------------------
# ---------------------------------------------------------------------------
CSV_PATH = os.getenv("VENDORS_CSV_PATH", "VNDRs.csv")      # override if you move the file
df = pd.read_csv(CSV_PATH).fillna("")                      # load once at start-up


# ---------------------------------------------------------------------------
#  Helpers ------------------------------------------------------------------
# ---------------------------------------------------------------------------
def _fmt(row: pd.Series) -> str:
    """Return a nicely formatted vendor block for chat output."""
    parts = [
        f"**{row.get('Title','Unknown Vendor')}**",
        f"Category : {row.get('Category','')}",
        f"Offers   : {row.get('Offers','')}",
        f"Location : {row.get('Location','')}",
        f"Contact  : {row.get('Contact Info','') or row.get('Phone Number','')}",
        f"Link     : {row.get('link ','')}",
    ]
    # drop empty lines and join
    return "\n".join([p for p in parts if p.strip()])


def _similar(a: str, b: str) -> float:
    """Quick similarity score between two words (0-1)."""
    return SequenceMatcher(None, a, b).ratio()


def local_lookup(message: str) -> str | None:
    """
    Scan the CSV for a match on either the vendor Title or Category.

    • Uses direct substring search first  
    • Falls back to fuzzy “photography” ≈ “photographer” matching (≥ 0.7)
    """
    msg = message.lower()
    best = None
    best_score = 0.0

    for _, row in df.iterrows():
        title    = str(row.get("Title",    "")).lower()
        category = str(row.get("Category", "")).lower()

        # exact substring
        if title and title in msg or category and category in msg:
            return _fmt(row)

        # fuzzy word-by-word
        for word in re.findall(r"\w+", msg):
            score = max(_similar(word, title), _similar(word, category))
            if score > best_score and score >= 0.7:
                best = row
                best_score = score

    return _fmt(best) if best is not None else None


def no_match() -> str:
    """Fallback text when nothing in the CSV fits."""
    return ("I couldn’t find a vendor for that keyword in our list. "
            "Try something like “photographer”, “balloons”, “mobile bar”, or a city name!")


# ---------------------------------------------------------------------------
#  Flask --------------------------------------------------------------------
# ---------------------------------------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    user = request.get_json(force=True).get("message", "")
    hit  = local_lookup(user)
    reply = hit if hit else no_match()
    return jsonify({"response": reply})


# ---------------------------------------------------------------------------
#  Local dev ----------------------------------------------------------------
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
