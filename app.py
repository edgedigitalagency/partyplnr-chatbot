import os, re
from difflib import SequenceMatcher

import pandas as pd
import openai
from flask import Flask, request, jsonify, render_template

# ── Config ────────────────────────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_API_KEY")               # .env / Render secret
CSV_PATH       = os.getenv("VENDORS_CSV_PATH", "VNDRs.csv")

df = pd.read_csv(CSV_PATH).fillna("")

# Build a set of city­ names found in the CSV
def _build_city_set() -> set[str]:
    city_set: set[str] = set()
    for loc in df["Location"].dropna():
        first = str(loc).split(",")[0]         # “Alvin” from “Alvin, TX”
        for part in re.split(r"[;/&]| and ", first):
            city = part.strip().lower()
            if city:
                city_set.add(city)
    return city_set

CITIES = _build_city_set()

# ── Helpers ───────────────────────────────────────────────────────────
def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def _format_vendor(row: pd.Series) -> str:
    return "\n".join(
        p for p in [
            f"**{row.get('Title','Unknown Vendor')}**",
            f"Category : {row.get('Category','')}",
            f"Offers   : {row.get('Offers','')}",
            f"Location : {row.get('Location','')}",
            f"Contact  : {row.get('Contact Info','') or row.get('Phone Number','')}",
            f"Link     : {row.get('link ','')}",
        ] if p.strip()
    )

def _find_cities(msg: str) -> list[str]:
    """Return any known city names mentioned in the message."""
    msg_lc = msg.lower()
    return [city for city in CITIES if re.search(rf"\b{re.escape(city)}\b", msg_lc)]

# ── Local vendor lookup ───────────────────────────────────────────────
def local_lookup(message: str) -> str | None:
    msg      = message.lower()
    cities   = _find_cities(msg)
    seen_cat = set()
    results  = []

    for _, row in df.iterrows():
        title = str(row.get("Title", "")).lower()
        cat   = str(row.get("Category", "")).strip().lower()
        loc   = str(row.get("Location", "")).lower()

        # Skip vendors outside the requested city
        if cities and not any(city in loc for city in cities):
            continue

        def matches() -> bool:
            if (cat and cat in msg) or (title and title in msg):
                return True
            for word in re.findall(r"\w+", msg):
                if _similar(word, cat) >= 0.7 or _similar(word, title) >= 0.7:
                    return True
            return False

        if matches() and cat not in seen_cat:
            results.append(row)
            seen_cat.add(cat)
        if len(results) >= 5:
            break

    if not results:
        return None

    if len(results) == 1:
        cat  = results[0].get("Category", "vendor").lower()
        city = results[0].get("Location", "").split(",")[0]
        intro = (f"Great! It sounds like you’re looking for a {cat}"
                 f"{' in ' + city if city else ''}. 🎉\n\n"
                 "Here’s someone on our list who might fit:\n\n")
    else:
        intro = "Here are a few vendors that may help with your request:\n\n"

    body = "\n\n---\n\n".join(_format_vendor(r) for r in results)
    return intro + body

# ── GPT-4o-mini fallback ──────────────────────────────────────────────
SYSTEM_PROMPT = """
You are PartyPlnr, an assistant that suggests event vendors from a database.
If the CSV has no match for the requested city, politely say you couldn't find one
and invite the user to try again with different wording. Never invent vendor data.
"""

def ai_fallback(message: str) -> str:
    if not openai.api_key:
        return ("I couldn’t reach the AI right now. "
                "Please try a different keyword or city.")
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

# ── Flask setup ───────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_msg   = request.get_json(force=True).get("message", "")
    cities_in_msg = _find_cities(user_msg)

    answer = local_lookup(user_msg)
    if answer:                              # we found vendors
        return jsonify({"response": answer})

    if not cities_in_msg:                   # no city specified → ask
        return jsonify({"response": "Sure — what city will the event be in?"})

    # city given but no vendor match → ask GPT (or apologise)
    return jsonify({"response": ai_fallback(user_msg)})

# ── Local dev ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
