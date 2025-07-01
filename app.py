import os, random, re
import pandas as pd
from flask import Flask, request, jsonify, render_template

CSV_PATH = os.getenv("VENDORS_CSV_PATH", "VNDRs.csv")
df = pd.read_csv(CSV_PATH).fillna("")

# ---------- helpers ----------
_intros = [
    "Great pick! Check these out 🎉",
    "Party on! Try one of these 🥳",
    "Here’s a perfect match 👇",
    "You might love these 🎈",
    "Look what I found 🤩"
]
_no_city     = "Sure — what city will the event be in?"
_no_category = "Got it! What kind of vendor are you looking for (e.g. bakery, balloons)?"
_no_match    = "I don’t have anyone for that combo yet 🙈. Try another keyword or city?"

# category → canonical form
_cat_map = {
    r"\bphoto|photograph":      "photography",
    r"\bbaker|cake|dessert":    "bakery",
    r"\bballoon":               "balloons",
    r"\bvenue|hall|location":   "venue",
    r"\bbar\b|bartend":         "mobile bars",
    r"\bflorist|flower":        "florists / flowers",
    r"\bdecor":                 "event decorators",
    r"\bcontent":               "content",
    r"\bapparel|shirt":         "apparel",
    r"\brental|bounce":         "rentals",
    r"\bpiñata|pinata":         "pinatas",
    r"\bbakery":                "bakery"            # exact stays the same
}
_city_regex = re.compile(r"\b(?:in|near|around|close to)\s+([a-z\s]+)", re.I)

def _pick_category(text: str) -> str | None:
    for pat, canon in _cat_map.items():
        if re.search(pat, text, re.I):
            return canon
    return None

def _pick_city(text: str) -> str | None:
    # explicit “… in Houston”
    m = _city_regex.search(text)
    if m:
        return m.group(1).strip().lower()
    # or single word city (houston, alvin…) with no verb
    words = text.lower().split()
    for w in words:
        if w in {"houston", "galveston", "alvin", "katy", "pearland", "league", "league city"}:
            return w
    return None

def _format_vendor(row: pd.Series) -> str:
    bits = [
        f"**{row['Title']}**",
        f"Category : {row['Category']}",
        f"Offers   : {row['Offers']}",
        f"Location : {row['Location']}",
        f"Contact  : {row['Contact Info']}" if row['Contact Info'] else "",
        f"Link     : {row['link ']}" if row['link '] else "",
    ]
    return "\n".join(b for b in bits if b.strip())

def _search(cat: str | None, city: str | None) -> list[pd.Series]:
    subset = df
    if cat:
        subset = subset[subset["Category"].str.lower() == cat]
    if city:
        subset = subset[
            subset["AreaTags"].str.contains(city, case=False) |
            subset["Location"].str.contains(city, case=False)
        ]
    return subset.sort_values("Score", ascending=False).head(3).to_dict("records")

# ---------- Flask ----------
app = Flask(__name__, template_folder="templates", static_folder="static")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user = request.get_json(force=True).get("message", "")
    cat  = _pick_category(user)
    city = _pick_city(user)

    if not cat and not city:
        return jsonify({"response": _no_category})

    if cat and not city:
        return jsonify({"response": _no_city})

    results = _search(cat, city)
    if not results:
        return jsonify({"response": _no_match})

    intro = random.choice(_intros)
    blocks = "\n\n---\n\n".join(_format_vendor(pd.Series(r)) for r in results)
    return jsonify({"response": f"{intro}\n\n{blocks}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
