# ──────────────────────────────────────────────────────────────────────────────
# PartyPlnr – zero-cost, CSV-only chatbot (no OpenAI key needed)
# Copy this file to your project root and deploy.  Flask serves /  and /chat
# ──────────────────────────────────────────────────────────────────────────────
import os, random, re
from difflib import SequenceMatcher

import pandas as pd
from flask import Flask, request, jsonify, render_template, session

# ── config ────────────────────────────────────────────────────────────────────
CSV_PATH       = os.getenv("VENDORS_CSV_PATH", "VNDRs.csv")
PORT           = int(os.getenv("PORT", 10000))
app            = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET", "change-me-in-prod")  # needed for session

# ── load vendor DB once at startup ────────────────────────────────────────────
df = pd.read_csv(CSV_PATH).fillna("")
df_cols = {c.lower(): c for c in df.columns}  # map for safe access

# ── helpers ───────────────────────────────────────────────────────────────────
EMOJIS  = ["🎉", "🥳", "🎈", "✨", "📸", "🍰", "💐"]
GREET   = [
    "Here’s a perfect match {e}",
    "You might love these {e}",
    "Great pick!  Check these out {e}",
    "Party on!  Try one of these {e}",
]

def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())

def _fmt(row: pd.Series) -> str:
    """Pretty-print a single vendor row."""
    parts = [
        f"**{row.get('Title','(No name)')}**",
        f"Category : {row.get('Category','')}",
        f"Offers   : {row.get('Offers','')}",
        f"Location : {row.get('Location','')}",
        f"Contact  : {row.get('Contact Info','') or row.get('Phone Number','')}",
        f"Link     : {row.get('link ','')}",
    ]
    return "\n".join(p for p in parts if p.strip())

def _best_city_hint() -> str | None:
    """Return city stored in session if we already asked user once."""
    return session.get("city")

def _save_city(city: str) -> None:
    session["city"] = city.strip()

def local_lookup(message: str, city_hint: str | None = None) -> list[pd.Series]:
    """
    Return up to three best-fit vendor rows.
    • Match on Category or semicolon-separated 'Keywords'
    • Prefer rows whose Metro column contains the user’s city hint.
    """
    toks   = _tokens(message)
    wants  = set(toks)
    hits:   list[tuple[int, pd.Series]] = []

    for _, row in df.iterrows():
        cat   = str(row.get("Category", "")).lower()
        keys  = str(row.get("Keywords", "")).lower().split(";")
        metro = str(row.get("Metro", "")).lower()

        cat_hit  = any(tok in cat for tok in wants)
        key_hit  = any(_similar(tok, kw.strip()) >= 0.76 for tok in wants for kw in keys)

        if not (cat_hit or key_hit):
            continue

        loc_score = 0 if (city_hint and city_hint.lower() in metro) else 1
        hits.append((loc_score, row))

    hits.sort(key=lambda x: x[0])
    return [row for _, row in hits[:3]]

# ── routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html")        # keep your existing HTML

@app.route("/chat", methods=["POST"])
def chat() -> str:
    user = request.get_json(force=True).get("message", "").strip()
    if not user:
        return jsonify({"response": "Say something and I’ll try to help 😊"})

    # simple “remember city” logic
    if user.lower().startswith(("i am in ", "i'm in ", "my city is ")):
        _save_city(user.split()[-1])
        return jsonify({"response": "Got it!  I’ll look near **{}**.".format(_best_city_hint())})

    city_hint = _best_city_hint()
    hits      = local_lookup(user, city_hint)

    if not hits:
        # if we don’t know the city yet, ask once
        if not city_hint:
            return jsonify({"response": "Sure — what city will the event be in?"})
        return jsonify({"response": "I don’t have anyone for that yet — try another keyword 🤔"})

    greeting = random.choice(GREET).format(e=random.choice(EMOJIS))
    body     = "\n\n---\n\n".join(_fmt(r) for r in hits)
    reply    = f"{greeting}\n\n{body}"
    return jsonify({"response": reply})

# ── local run ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
