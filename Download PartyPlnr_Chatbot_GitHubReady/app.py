from flask import Flask, render_template, request, jsonify
import pandas as pd
import openai
import os
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
vendors = pd.read_csv("vndrs.csv")

def find_vendors(category, location):
    matches = vendors[
        (vendors['Category'].str.lower() == category.lower()) &
        (vendors['Location'].str.lower().str.contains(location.lower()))
    ]
    if matches.empty:
        fallback = vendors[vendors['Category'].str.lower() == category.lower()]
        return fallback.head(3).to_dict(orient='records')
    return matches.head(3).to_dict(orient='records')

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    user_message = request.json["message"]
    words = user_message.lower().split()
    location = next((w for w in words if w in vendors["Location"].str.lower().unique()), "")
    category = next((w for w in words if w in vendors["Category"].str.lower().unique()), "")

    matches = find_vendors(category, location)
    if not matches:
        return jsonify({"reply": "Sorry, I couldn't find any matching vendors."})

    vendor_list = "\n".join([f"{v['Title']} — {v['Location']} — {v.get('Offers', '')}" for v in matches])

    prompt = f"""You are PartyPlnr AI. Only respond using these real vendors:
{vendor_list}

Never make up vendors. User asked: {user_message}"""

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )

    return jsonify({"reply": response.choices[0].message["content"]})

if __name__ == "__main__":
    app.run(debug=True)
