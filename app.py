
from flask import Flask, request, jsonify, render_template
import pandas as pd

app = Flask(__name__)

vendors_df = pd.read_csv('vndrs.csv')

def find_vendor(message):
    message = message.lower()
    for _, row in vendors_df.iterrows():
        if row['Category'].lower() in message or row['Business Name'].lower() in message:
            return f"{row['Business Name']} ({row['Category']}): {row['Description']} – Located in {row['Location']}"
    return "Sorry, I couldn't find any matching vendors. Please try a different request."

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_input = data.get('user_input', '')
    response = find_vendor(user_input)
    return jsonify({'response': response})

if __name__ == '__main__':
    app.run(debug=True)
