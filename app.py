import os, re
from difflib import SequenceMatcher

import pandas as pd
import openai
from flask import Flask, request, jsonify, render_template

# ── Config ────────────────────────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_API_KEY")               # .env / Render secret
CSV_PATH       = os.getenv("VENDORS_CSV_PATH", "VNDRs.csv")

df = pd.read_csv(CSV_PATH).fillna("")

# set of city names known in the CSV  ──────────────────────────────────
def _build_city_set() -> set[str]:
    city_set: set[str] = set()
    for loc in df["Location"].dropna():
        first = str(loc).split(",")[0]
        for part in re.split(r"[;/&]| and ", first):
            city = part.strip().lower()
            if city:
                city_set.add(city)
    return city_set

CITIES = _build_city_set()

# simple keyword ➜ CSV category map  ───────────────────────────────────
KEYWORD_TO_CATEGORY = {
    #   keyword (lower-case)    :  CSV “Category” value
    "venue":        "Venue",
    "hall":         "Venue",
    "location":     "Venue",
    "place":        "Venue",

    "balloon":      "Balloons",
    "balloons":     "Balloons",

    "cake":         "Bakery",
    "cakes":        "Bakery",
    "bakery":       "Bakery",
    "cupcake":      "Bakery",

    "dessert":      "Bakery",
    "treat":        "Bakery",

    "dj":           "Entertainment ",
    "music":        "Entertainment ",
    "band":         "Entertainment ",

    "photo":        "Photography",
    "photographer": "Photography",
    "photography":  "Photography",

    "decor":        "Event Decorators",
    "decoration":   "Event Decorators",
    "decorator":    "Event Decorators",

    "cater":        "Food Vendors",
    "catering":     "Food Vendors",
    "chef":         "Food Vendors",
    "food":         "Food Vendors",

    "bar":          "Mobile Bars",
    "drink":        "Mobile Bars",
    "cocktail":     "Mobile Bars",
}

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
    msg_lc = msg.lower()
    return [city for city in CITIES if re.search(rf"\b{re.escape(city)}\b", msg_lc)]

def _requested_categories(msg: str) -> list[str]:
    """Return list of CSV categories inferred from keywords in the message."""
    msg_lc = msg.lower()

    # special preset for “baby shower”
    if "baby shower" in msg_lc:
        return ["Venue", "Balloons", "Bakery"]

    cats: list[str] = []
    for kw, cat in KEYWORD_TO_CATEGORY.items():
        if re.search(rf"\b{re.escape(kw)}\b", msg_lc):
            cats.append(cat)
    return list(dict.fromkeys(cats))   # keep order, remove dupes

# ── Local vendor lookup ───────────────────────────────────────────────
def local_lookup(message: str) -> str | None:
    msg       = message.lower()
    cities    = _find_cities(msg)
    req_cats  = _requested_categories(msg)

    if not req_cats:
        return None   # no idea what category they want → caller will ask

    results: list[pd.Series] = []
    for cat in req_cats:
        # pick first vendor that matches both city & category
        for _, row in df[df["Category"].str.lower() == cat.lower()].iterrows():
            loc_lc = str(row.get("Location", "")).lower()
            if cities and not any(city in loc_lc for city in cities):
                continue
            results.append(row)
            break  # only one vendor per requested category

    if not results:
        return None

    intro_city = f" in {cities[0].title()}" if cities else ""
    intro = (f"Great! Here are some options{intro_city}:\n\n"
             if len(results) > 1 else
             f"Great! It sounds like you’re planning something{intro_city}. 🎉\n\n"
             "Here’s someone on our list who might fit:\n\n")

    body = "\n\n---\n\n".join(_format_vendor(r) for r in results)
    return intro + body

# ── GPT-4o-mini fallback ──────────────────────────────────────────────
SYSTEM_PROMPT = """
You are PartyPlnr, an assistant that suggests event vendors from a database.
If the CSV has no match for the requested city or services, politely say you couldn't
find one and invite the user to try again with different wording. Never invent vendor
data or pretend to have vendors that are not in the CSV.
"""

def ai_fallback(message: str) -> str:
    if not openai.api_key:
        return ("I couldn’t find a match. Try different keywords "
                "like 'venue', 'balloons', or 'cake', plus the city name.")
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
    user_msg = request.get_json(force=True).get("message", "")
    cities   = _find_cities(user_msg)
    cats     = _requested_categories(user_msg)

    answer = local_lookup(user_msg)
    if answer:
        return jsonify({"response": answer})

    # no category keywords ➜ ask what services
    if not cats:
        return jsonify({"response":
            "Got it! What services do you need? (e.g. venue, cake, balloons, DJ)"} )

    # category present but no city ➜ ask city
    if not cities:
        return jsonify({"response": "Sure — what city will the event be in?"})

    # we had city & services but still no vendor ➜ GPT or apology
    return jsonify({"response": ai_fallback(user_msg)})

# ── Local dev ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
