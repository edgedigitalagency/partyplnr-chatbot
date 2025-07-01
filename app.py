#!/usr/bin/env python3
"""
PartyPlnr – ultra-offline edition
Filename expectations:
  • VNDRs.csv  ← your vendor list (must contain the columns shown below)
"""

import os, re, random, time
import pandas as pd
from flask import Flask, request, jsonify, render_template

# ── Config ──────────────────────────────────────────────────────────────────
CSV_PATH   = os.getenv("VENDORS_CSV_PATH", "VNDRs.csv")
CACHE_TTL  = 120     # seconds
TOP_K      = 3       # how many vendors we print

# ── Load database ───────────────────────────────────────────────────────────
df = pd.read_csv(CSV_PATH).fillna("")
# …required columns → Title, Category, Offers, Location, Contact Info, link ,
#                      Score (int, optional), PartyTags (str, optional)

CITIES = {c.lower() for c in df["Location"].str.split(",").str[0].dropna().unique()}
CITIES.update({"houston","galveston","pearland","league city","friendswood",
               "alvin","kemah","katy","clear lake","woodlands","sugar land"})

CATEGORY_SYNS = {
    "photography":  {"photographer","photography","photo","photos","pictures","pics"},
    "bakery":       {"baker","bakery","cake","cookies","cupcakes","dessert","sweets"},
    "balloons":     {"balloon","balloons","garland","arch"},
    "decor":        {"decor","decorator","setup","styling","backdrop"},
    "mobile bar":   {"bar","bartender","cocktail","drinks","daiquiri","margarita"},
    "venue":        {"venue","hall","location","space"},
    "catering":     {"cater","catering","chef","food","bbq","ice cream","truck"},
    "rentals":      {"bounce","inflatables","chairs","tables","rental","photobooth"},
    "florist":      {"flower","florals","florist","bloom"},
    "entertainment":{"dj","music","petting zoo","face paint","content","planner"},
    "party favors": {"favors","gifts","3d print","pinata","piñata"},
}

# optional party-type cues (baby shower, wedding, etc.)
PARTY_CUES = {
    "baby":      {"baby shower","gender reveal","sprinkle"},
    "wedding":   {"wedding","bridal","rehearsal"},
    "birthday":  {"birthday","b-day","turning","anniversary"},
    "corporate": {"corporate","office","grand opening","expo"},
}

EMOJIS       = "🎉🥳🎈✨🍰📸🎤🎶🍹🍩🌸🤩".split(" ")
ANSWER_TMPLS = [
    "All set! {emoji}\nHere are a few hand-picked options:\n\n{vendors}",
    "Party time {emoji}\nCheck these out:\n\n{vendors}",
    "Great choice! {emoji}\nI’d start with:\n\n{vendors}",
    "Try these 🎈👇\n\n{vendors}",
]

NEED_CITY_PROMPTS = [
    "Sure — what city will the event be in?",
    "Got it! Which city should I search around?",
]

NEED_CAT_PROMPTS = [
    "Fun! What kind of vendor do you still need? (e.g. bakery, balloons, venue…)",
]

# ── Mini cache ──────────────────────────────────────────────────────────────
_cache: dict[str, tuple[float,str]] = {}
def cached(key, builder):
    now = time.time()
    if key in _cache and now - _cache[key][0] < CACHE_TTL:
        return _cache[key][1]
    val = builder()
    _cache[key] = (now, val)
    return val

# ── recognizers ─────────────────────────────────────────────────────────────
def detect_city(msg:str)->str|None:
    for c in CITIES:
        if re.search(rf"\b{re.escape(c)}\b", msg): return c
    return None

def detect_category(msg:str)->str|None:
    for cat,syns in CATEGORY_SYNS.items():
        if any(re.search(rf"\b{re.escape(s)}\b", msg) for s in syns):
            return cat
    return None

def detect_party(msg:str)->str|None:
    for tag,cues in PARTY_CUES.items():
        if any(cue in msg for cue in cues): return tag
    return None

# ── chooser ─────────────────────────────────────────────────────────────────
def choose_vendors(msg:str):
    city = detect_city(msg)
    cat  = detect_category(msg)
    ptag = detect_party(msg)

    # ask follow-up if user didn’t specify vendor type
    if not cat:
        return None, random.choice(NEED_CAT_PROMPTS)
    # ask follow-up if they gave a type but no city (optional)
    if not city:
        # comment this out if you *don’t* want the follow-up
        pass

    # === filter FIRST by category if known ===
    subset = df if not cat else df[df["Category"].str.lower()==cat]
    if subset.empty:
        return None, "I couldn’t find anyone in that category 😕."

    # simple scoring
    def score(row):
        s = row.get("Score",3)
        if city and city in row["Location"].lower(): s += 3
        if ptag and ptag in str(row.get("PartyTags","")).lower(): s += 2
        return s
    subset["__score"] = subset.apply(score, axis=1)
    picks = subset.sort_values("__score",ascending=False).head(TOP_K)
    if picks.empty:
        return None, "No matches yet — maybe try another keyword?"

    blocks=[]
    for _,r in picks.iterrows():
        txt=[f"**{r['Title']}**",
             f"_{r['Category']}_ · {r['Location'] or '—'}",
             r['Offers'][:120]+"…" if len(r['Offers'])>120 else r['Offers'],
             (f"Contact: {r['Contact Info']}" if r['Contact Info'] else ""),
             (f"Link: {r['link ']}"           if r['link ']      else "")]
        blocks.append("\n".join([t for t in txt if t.strip()]))

    return random.choice(ANSWER_TMPLS).format(
        emoji=random.choice(EMOJIS),
        vendors="\n\n---\n\n".join(blocks)
    ), None

# ── Flask endpoints ─────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")

@app.route("/")
def home(): return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user = request.get_json(force=True).get("message","").strip()
    if not user:
        return jsonify({"response":"Say something like *“Need a balloon arch in Pearland”* 😄"})
    reply, follow = cached(user.lower(), lambda: choose_vendors(user.lower()))
    return jsonify({"response": follow or reply})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)), debug=True)
