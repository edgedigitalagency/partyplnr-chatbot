#!/usr/bin/env python3
"""
PartyPlnr – ultra-offline edition
No OpenAI key required.
"""

import os, re, random, time, json
import pandas as pd
from flask import Flask, request, jsonify, render_template
from collections import defaultdict
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
CSV_PATH   = os.getenv("VENDORS_CSV_PATH", "VNDRs.csv")
CACHE_TTL  = 120                       # seconds (simple in-memory cache)
TOP_K      = 3                         # max vendors to show

# ── Load database & helpers ────────────────────────────────────────────────
df = pd.read_csv(CSV_PATH).fillna("")
CITIES = {c.lower() for c in df["Location"].str.split(",").str[0].dropna().unique()}
CITIES.update({"houston","galveston","pearland","league city","friendswood",
               "alvin","kemah","katy","clear lake","woodlands","sugar land"})

# synonym buckets (extend anytime)
CATEGORY_SYNS = {
    "photography": {"photographer","photography","photo","photos","pictures","pics"},
    "bakery":      {"baker","bakery","cake","cookies","cakes","cupcakes","sweets","dessert"},
    "balloons":    {"balloon","balloons","garland","arch"},
    "decor":       {"decor","decorator","setup","styling","design","backdrop"},
    "mobile bar":  {"bar","bartender","cocktail","drinks","daiquiri","margarita"},
    "venue":       {"venue","hall","location","space","place"},
    "catering":    {"cater","catering","food","chef","bbq","ice cream","truck"},
    "rentals":     {"bounce","inflatables","chairs","tables","rental","photobooth"},
    "florist":     {"flower","florals","florist","bloom"},
    "entertainment":{"dj","music","petting zoo","face paint","content","planner"},
    "party favors":{"favors","gifts","3d print","pinata","piñata","party favor"},
}

PARTY_CUES = {
    "baby":      {"baby shower","gender reveal","sprinkle"},
    "wedding":   {"wedding","bridal","rehearsal"},
    "birthday":  {"birthday","b-day","turning","anniversary"},
    "corporate": {"corporate","office","team","grand opening","expo","trade show"},
    "kids":      {"kid","children","child","toddler"},
    "holiday":   {"christmas","easter","halloween","thanksgiving","holiday"},
    "graduation":{"graduation","grad party","commencement"},
}

TEMPLATES = [
    "All set! {emoji}  Here are a few hand-picked options:\n\n{vendors}",
    "Party time {emoji}\nCheck these out:\n\n{vendors}",
    "Great choice!  {emoji}\nI’d look at these folks:\n\n{vendors}",
    "Here’s who I’d ping first {emoji}\n\n{vendors}",
    "Try these 🎈👇\n\n{vendors}",
    "Sweet! {emoji}  My favorites:\n\n{vendors}",
]

FOLLOWUP_NEED_CITY = [
    "Sure — what city will the event be in?",
    "Got it!  Which city should I search around?",
    "Cool ✨  And the party’s happening where?",
]

FOLLOWUP_NEED_CAT = [
    "Fun!  What kind of vendor do you still need? (e.g. bakery, balloons, venue…)",
    "Great—do you need a florist, a DJ, a caterer, or something else?",
]

EMOJIS = "🎉🥳🎈✨🍰📸🎤🎶🍹🍩🌸🤩".split(" ")

# ── Simple cache ───────────────────────────────────────────────────────────
_cache: dict[str, tuple[float,str]] = {}

def cached(key, builder):
    now = time.time()
    if key in _cache and now - _cache[key][0] < CACHE_TTL:
        return _cache[key][1]
    value = builder()
    _cache[key] = (now, value)
    return value

# ── Core matching logic ────────────────────────────────────────────────────
def detect_city(msg: str) -> str|None:
    for city in CITIES:
        if re.search(rf"\b{re.escape(city)}\b", msg):
            return city
    return None

def detect_category(msg: str) -> str|None:
    for cat, syns in CATEGORY_SYNS.items():
        for s in syns:
            if re.search(rf"\b{re.escape(s)}\b", msg):
                return cat
    return None

def detect_party_type(msg: str) -> str|None:
    for ptype, cues in PARTY_CUES.items():
        for cue in cues:
            if cue in msg:
                return ptype
    return None

def score_row(row, target_cat, target_city, ptype):
    score = row.get("Score",3)         # base vendor score
    if target_cat and row["Category"].lower()==target_cat: score += 4
    if target_city and target_city in row["Location"].lower(): score += 3
    if ptype and ptype in (row.get("PartyTags","")+"").lower(): score += 2
    return score

def choose_vendors(msg: str):
    target_city = detect_city(msg)
    target_cat  = detect_category(msg)
    ptype       = detect_party_type(msg)

    if not target_cat:
        return None, random.choice(FOLLOWUP_NEED_CAT)

    # Score & rank
    df["__score"] = df.apply(score_row, axis=1,
                             args=(target_cat, target_city, ptype))
    best = (df[df["__score"]>0]
            .sort_values("__score", ascending=False)
            .head(TOP_K))
    if best.empty:
        return None, "I couldn’t find a match—try another keyword?"

    payload = []
    for _, r in best.iterrows():
        txt = [f"**{r['Title']}**",
               f"_{r['Category']}_ · {r['Location'] or '—'}",
               f"{r['Offers'][:120]}…" if len(r['Offers'])>120 else r['Offers'],
               (f"Contact: {r['Contact Info']}" if r['Contact Info'] else ""),
               (f"Link: {r['link ']}"            if r['link ']      else "")]
        payload.append("\n".join([t for t in txt if t.strip()]))

    vendors_block = "\n\n---\n\n".join(payload)
    template = random.choice(TEMPLATES)
    reply = template.format(emoji=random.choice(EMOJIS), vendors=vendors_block)
    return reply, None

# ── Flask app ──────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user = request.get_json(force=True).get("message","").strip()
    if not user:
        return jsonify({"response":"Say something like *“Need a balloon arch in Pearland”* 😄"})

    # cache
    response = cached(user.lower(), lambda: choose_vendors(user.lower()))
    reply, follow = response
    if reply:     return jsonify({"response": reply})
    if follow:    return jsonify({"response": follow})
    # safety-net
    return jsonify({"response": "Hmm, I’m stumped 🤔. Try a different keyword?"})

# ── local run ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)), debug=True)
