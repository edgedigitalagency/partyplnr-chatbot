import os, re
import pandas as pd
from difflib import SequenceMatcher
from flask import Flask, request, jsonify, render_template

CSV_PATH = os.getenv("VENDORS_CSV_PATH", "VNDRs.csv")
df = pd.read_csv(CSV_PATH).fillna("")

def similar(a, b): return SequenceMatcher(None, a, b).ratio()

def _fmt(row: pd.Series) -> str:
    return "\n".join([
        f"**{row['Title']}**",
        f"Category : {row['Category']}",
        f"Offers   : {row['Offers']}",
        f"Location : {row['Location']}",
        f"Contact  : {row['Contact Info'] or row['Phone Number']}",
        f"Link     : {row['link ']}",
    ])

def local_lookup(msg: str) -> str | None:
    msg = msg.lower()
    best = None ; best_score = 0
    for _, row in df.iterrows():
        for field in ("Title", "Category"):
            target = str(row[field]).lower()
            score  = max(similar(word, target) for word in re.findall(r"\w+", msg))
            if score > best_score and score >= 0.7:
                best_score, best = score, row
    return _fmt(best) if best else None

app = Flask(__name__, template_folder="templates", static_folder="static")

@app.route("/")
def home(): return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user = request.get_json(force=True).get("message", "")
    hit  = local_lookup(user)
    if hit:
        # very light “human” wrapper
        reply = (f"Great! Here’s someone who might help:\n\n{hit}")
    else:
        reply = ("I couldn’t find a perfect match. "
                 "Try another keyword like “photographer”, “mobile bar”, or a city name!")
    return jsonify({"response": reply})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
