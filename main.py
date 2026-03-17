import requests
import json
from main import Flask, request, jsonify

app = Flask(__name__)

# Constants (Move to top for clarity)
APP_ID = '747038104584957'
APP_SECRET = '31ba50ef31397be2f1c36850b4a5ddce'
REDIRECT_URI = 'http://127.0.0.1:5000/auth/callback'

@app.route('/')
def hello_world():
    return "<p>Hello, World!</p>"

@app.route('/privacy_policy')
def privacy_policy():
    try:
        with open("privacy_policy.html", "rt") as file:
            privacy_policy_html = file.read()
        return privacy_policy_html
    except FileNotFoundError:
        return "<p>Privacy policy not found.</p>", 404

@app.route('/webhook', methods=["GET", "POST"])
def webhook():
    if request.method == "POST":
        try:
            print(json.dumps(request.get_json(), indent=4))
        except Exception as e:
            print("Failed to parse POST JSON:", str(e))
        return "<p>This is POST request, Hello Webhook</p>"

    elif request.method == "GET":
        hub_mode = request.args.get("hub.mode")
        hub_challenge = request.args.get("hub.challenge")
        hub_verify_token = request.args.get("hub.verify_token")

        # You may want to validate verify_token here
        if hub_challenge:
            return hub_challenge
        else:
            return "<p>This is GET request, Hello Webhook</p>"

@app.route('/auth/callback')
def auth_callback():
    code = request.args.get('code')
    if not code:
        return "Error: No code received", 400

    token_url = 'https://graph.facebook.com/v19.0/oauth/access_token'
    params = {
        'client_id': APP_ID,
        'redirect_uri': REDIRECT_URI,
        'client_secret': APP_SECRET,
        'code': code
    }

    response = requests.get(token_url, params=params)
    data = response.json()
    print(data)

    if 'access_token' in data:
        return jsonify({
            'access_token': data['access_token'],
            'token_type': data.get('token_type'),
            'expires_in': data.get('expires_in')
        })
    else:
        return jsonify({'error': data}), 400

if __name__ == '__main__':
    app.run(debug=True)
