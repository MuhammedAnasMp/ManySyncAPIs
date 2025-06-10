from instagrapi import Client

cl = Client()

# Load session from file
cl.load_settings("data.json")

user_id = cl.account_info()
print("Logged-in user ID:", user_id.pk)