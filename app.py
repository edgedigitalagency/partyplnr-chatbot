import os, re, random
from difflib import SequenceMatcher
import pandas as pd
from flask import Flask, request, jsonify, render_template

# ──────────────────────────────────────────────────────────────────────────────
#  Config & data
# ──────────────────────────────────────────────────────────────────────────────
CSV_PATH = os.getenv("VENDORS_CSV_PATH", "VNDRs.csv")
df = pd.read_csv(CSV_PATH).fillna("")            # load once

#  lowercase helper columns for fast matching
df["title_lc"]      = df["Title"].str.lower()
df["category_lc"]   = df["Category"].str.lower()
df["metro_lc"]      = df["Metro"].str.lower()
df["parties_lc"]    = df["PartyTypes"].str.lower()
df["vibes_lc"]      = df["Vibes"].str.lower()

# response templates (rotates for variety)
TEMPLATES_ONE = [
    "🎉 Sweet! Planning a {party} in {city}? Check this out:\n\n{vendor}",
    "✨ Gotcha — here’s a {category} near {city} you might love:\n\n{vendor}",
    "🙌 Perfect match! Consider:\n\n{vendor}",
]
TEMPLATES_MULTI = [
    "Here are a few ideas for your {party} in {city}:\n\n{vendors}",
    "I found some great options:\n\n{vendors}",
    "Try these 🎈👇\n\n{vendors}",
]
NO_MATCH = (
    "😕 I couldn’t find anything in the list for that. "
    "Maybe try another keyword (photography, balloons, venue…) or name a nearby city."
)


# ──────────────────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _format_vendor(row: pd.Series) -> str:
    return (
        f"**{row['Title']}**\n"
        f"Category : {row['Category']}\n"
        f"Offers   : {row['Offers']}\n"
        f"Location : {row['Location']}\n"
        f"Contact  : {row.get('Contact Info','') or row.get('Phone Number','')}\n"
        f"Link     : {row.get('link ','')}"
    )


def _score_row(row: pd.Series, msg_tokens: list[str], city: str, party: str) -> float:
    """Simple weighted score: category/title + city + party type + fuzzy."""
    score = 0.0
    for token in msg_tokens:
        if token in row["title_lc"] or token in row["category_lc"]:
            score += 2
        if token in row["parties_lc"]:
            score += 1.5
        if token in row["vibes_lc"]:
            score += 0.5
        # fuzzy wiggle room
        score += max(
            _similar(token, row["title_lc"]),
            _similar(token, row["category_lc"]),
            _similar(token, row["parties_lc"]),
        )

    # city / metro bonus
    if city and city in row["metro_lc"]:
        score += 2
    return score


def find_matches(message: str, top_k: int = 3):
    msg_lc = message.lower()
    tokens  = re.findall(r"[a-z']+", msg_lc)

    # naive city & party‐type guess (first match wins)
    known_cities = set(df["metro_lc"]) - {""}
    city   = next((c for c in known_cities if c in msg_lc), "")
    party  = next((p for p in [
        "baby shower","bridal shower","wedding","birthday","kids party",
        "retirement","corporate","festival","anniversary"
    ] if p in msg_lc), "event")

    # score every vendor
    scores = df.apply(lambda row: _score_row(row, tokens, city, party), axis=1)
    top    = df.iloc[scores.nlargest(top_k).index]
    top    = top[scores.nlargest(top_k) > 2]          # threshold to ignore weak hits
    return city.title() or "your area", party, top


# ──────────────────────────────────────────────────────────────────────────────
#  Flask
# ──────────────────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    user_msg = request.get_json(force=True).get("message", "")
    city, party, matches = find_matches(user_msg)

    if matches.empty:
        reply = NO_MATCH
    elif len(matches) == 1:
        vendor = _format_vendor(matches.iloc[0])
        reply  = random.choice(TEMPLATES_ONE).format(
            party=party, city=city, category=matches.iloc[0]["Category"].lower(), vendor=vendor
        )
    else:
        vendors = "\n\n---\n\n".join(_format_vendor(r) for _, r in matches.iterrows())
        reply   = random.choice(TEMPLATES_MULTI).format(party=party, city=city, vendors=vendors)

    return jsonify({"response": reply})


# Local dev
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
