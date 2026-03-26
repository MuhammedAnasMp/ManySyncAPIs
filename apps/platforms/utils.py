import requests

def check_if_follows(user_id, access_token):
    url = f"https://graph.instagram.com/v25.0/{user_id}"
    params = {
        "fields": "id,username,is_user_follow_business",
        "access_token": access_token
    }

    response = requests.get(url, params=params)
    data = response.json()

    return data.get("is_user_follow_business", False)