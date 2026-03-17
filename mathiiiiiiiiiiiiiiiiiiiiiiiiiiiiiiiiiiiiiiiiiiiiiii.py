import time
import random
import os
from datetime import datetime
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ClientError

# Function to get readable timestamp
def timestamp(time_value):
    return datetime.fromtimestamp(time_value).strftime('%Y-%m-%d %H:%M:%S')

# Initialize Instagram Client
cl = Client()

# Check if session file exists, if not, log in manually
session_file = "session.json"
if os.path.exists(session_file):
    try:
        cl.load_settings(session_file)
        cl.login("kaattu_kozhi_", "15036*Kk")
        print("Logged in using saved session.")
    except Exception as e:
        print(f"Failed to load session: {e}. Logging in manually.")
        cl.login("kaattu_kozhi_", "15036*Kk")
        cl.dump_settings(session_file)  # Save new session
        print("New session saved.")
else:
    print("No session file found. Logging in manually.")
    cl.login("kaattu_kozhi_", "15036*Kk")
    cl.dump_settings(session_file)
    print("New session saved.")

# Verify login success
try:
    user_info = cl.account_info()
    print("Instagram Account Information:")
    print(f"Username: {user_info.username}")
    print(f"Full Name: {user_info.full_name}")
    print(f"Profile Picture URL: {user_info.profile_pic_url}")
    print(f"Is Private: {user_info.is_private}")
    print(f"Is Verified: {user_info.is_verified}")
    print(f"Biography: {user_info.biography}")
    print(f"External URL: {user_info.external_url}")
    print(f"Email: {user_info.email}")
    print(f"Phone Number: {user_info.phone_number}")
    print(f"Gender: {user_info.gender}")
    print(f"Is Business Account: {user_info.is_business}")
    print(f"Birthday: {user_info.birthday}")
    public_info = cl.user_info_by_username(user_info.username)
    print("\nPublic User Info:")
    print(f"Followers Count: {public_info.follower_count}")
    print(f"Following Count: {public_info.following_count}")
    print(f"Total Posts: {public_info.media_count}")

    print(user_info)

except Exception as e:
    print(f"Login verification failed: {e}")
    exit()  # Exit script if login failed

# Get the media ID from the reel URL
reel_url = "https://www.instagram.com/p/DLwSx_WIC09/"
try:
    media_id = cl.media_id(cl.media_pk_from_url(reel_url))
    print(f"Fetched media ID: {media_id}")
except Exception as e:
    print(f"Failed to get media ID: {e}")
    exit()

# List of plain text comments (no emojis)
comments = [
    "Really love this!", "Amazing creativity!", "Great vibes on this post!",
    "Your content is always inspiring!", "Keep up the fantastic work!",
    "Love your style!", "Super cool edit!", "This is simply beautiful!",
    "Such a unique perspective!", "I'm really enjoying your content!",
    "Brilliant as always!", "Great lighting in this shot!", 
    "Your work keeps getting better!", "Very impressive!",
    "Top-tier creativity!", "Just wow!", "Keep going!", "Love the energy here!"
]

i = 1705
while True:
    i += 1
    try:

        # **Step 2: Choose a random comment**
        comment_text = random.choice(comments)
        cl.media_comment(media_id, comment_text)
        print(f"Posted Comment {i}: {comment_text}")
        i += 1
        # **Step 2: Choose a random comment**
        comment_text = random.choice(comments)
        cl.media_comment(media_id, comment_text)
        print(f"Posted Comment {i}: {comment_text}")
        i += 1
        # **Step 2: Choose a random comment**
        comment_text = random.choice(comments)
        cl.media_comment(media_id, comment_text)
        print(f"Posted Comment {i}: {comment_text}")
        
        
        
        
        
        # **Step 3: Randomized delay to prevent spam detection**
        sleep_time = random.randint(60, 300)  # Wait between 80-120 seconds
        print(f"\rSleeping for {sleep_time} seconds...", end="", flush=True)
        time.sleep(sleep_time)
        print("\r" + " " * 40, end="\r")  # Clear the line after sleeping

        # **Step 4: Every 5 comments, take a longer break**
        if i % 5 == 0:
            break_time = random.randint(600, 1800)  # Pause for 5-15 minutes
            print(f"\rTaking a long break for {break_time} seconds...", end="", flush=True)
            time.sleep(break_time)
            print("\r" + " " * 40, end="\r")  # Clear the line after sleeping

    except LoginRequired:
        print("Session expired. Trying to re-login...")
        try:
            cl.login("kaattu_kozhi_", "15036*Kk")
            cl.dump_settings(session_file)  # Save session again
            print("Re-logged in successfully.")
        except Exception as e:
            print(f"Re-login failed: {e}")
            break  # Stop the script if login fails

    except ClientError as e:
        print(e)
        if "feedback_required" in str(e).lower():
            print("Instagram detected bot-like behavior. Stopping script.")
            print("Pausing for 3 hours to avoid a full block...", end="", flush=True)
            time.sleep(6800)  # Wait for ~3 hours before retrying
            print("\r" + " " * 40, end="\r")  # Clear the line after sleeping
            continue  # Restart the loop after waiting
        else:
            print(f"Instagram API error: {e}")
        break  # Exit loop on other API errors

    except Exception as e:
        print(f"Unexpected error: {e}")
        break  # Stop script if any unexpected issue happens
