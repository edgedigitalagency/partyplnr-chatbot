
from flask import Flask, request, render_template
import pandas as pd
import openai
import os

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")

# Load vendor data
vendors = pd.read_csv("VNDRs.csv")

# Normalize for easier matching
vendors['Title'] = vendors['Title'].fillna("").str.lower()
vendors['Category'] = vendors['Category'].fillna("").str.lower()
vendors['Location'] = vendors['Location'].fillna("")

def find_vendor(message):
    message = message.lower()
    matching_vendors = []

    for _, row in vendors.iterrows():
        if row['Category'] in message or row['Title'] in message:
            matching_vendors.append({
                'name': row['Title'].title(),
                'category': row['Category'].title(),
                'location': row['Location'],
                'contact': row['Contact Info'] or "No contact listed"
            })

    if matching_vendors:
        reply = "Here are some vendors that might work for you:\n\n"
        for v in matching_vendors[:5]:
            reply += f"- {v['name']} ({v['category']}) – {v['location']} – {v['contact']}\n"
    else:
        reply = "I couldn’t find an exact match in your area, but I’ll show you the closest options available.\n\n"
        for _, row in vendors.head(3).iterrows():
            reply += f"- {row['Title'].title()} ({row['Category'].title()}) – {row['Location']} – {row['Contact Info']}\n"

    reply += "\n*Note: These are suggestions, not official quotes. Vendor details may vary.*"
    return reply

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.form["user_input"]
    response = find_vendor(user_input)
    return response

if __name__ == "__main__":
    app.run(debug=True)
