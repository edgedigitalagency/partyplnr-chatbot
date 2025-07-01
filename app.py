
from flask import Flask, request, jsonify, render_template
import pandas as pd

app = Flask(__name__)

# Load vendor data
vendors_df = pd.read_csv('vndrs.csv')

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')
    if not user_message:
        return jsonify({'response': 'Please enter a message.'})

    # Simple keyword-based matching (placeholder logic)
    response = "Sorry, I couldn't find a match for your message."
    for _, row in vendors_df.iterrows():
        if row['Category'].lower() in user_message.lower():
            response = f"You might want to check out: {row['Business Name']} - {row['Description']}"
            break

    return jsonify({'response': response})

if __name__ == '__main__':
    app.run(debug=True)
