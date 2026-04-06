
import requests,time,os,re,random


def check_if_follows(user_id):
    access_token = "IGAAUN0phDYERBZAFprTXBTUFVLSFlSNFpGcWJXd2Y0WGF5ZAGNGUkRnRENvbFVPWVROdjVtNDRCUG1YNE1Pa3RrUm0xamlkdHVjbGw5N09od1pPbVg3ckpNRkZA1SGUwVXRtM29PMm50czNOQ3JvNlhzR0QwMTdSODkwQVpkTDR6awZDZD"
    url = f"https://graph.instagram.com/v25.0/{user_id}"
    params = {
        "fields": "id,username,is_user_follow_business",
        "access_token": access_token
    }

    response = requests.get(url, params=params)
    data = response.json()

    return data.get("username"), data.get("is_user_follow_business", False)




def download_video(url, folder=".", filename="video"):
    print(f"--- Starting Download ---")
    print(f"Target URL: {url}")

    try:
        res = requests.get(url, stream=True, timeout=15)
        res.raise_for_status()

        content_type = res.headers.get('Content-Type', '')
        print(f"Status Code: {res.status_code}")
        print(f"Content-Type: {content_type}")

        if "text/html" in content_type.lower():
            print("ERROR: URL returned HTML instead of a video.")
            print(res.text[:200])
            return None

        # Try to guess file extension
        ext = ".mp4"
        if "video" in content_type:
            ext = "." + content_type.split("/")[-1]

        # Build full path
        os.makedirs(folder, exist_ok=True)
        save_path = os.path.join(folder, filename + ext)

        total_size = int(res.headers.get('content-length', 0))
        print(f"Total size: {total_size / (1024*1024):.2f} MB" if total_size else "Total size: Unknown")

        downloaded = 0
        with open(save_path, "wb") as f:
            for chunk in res.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    print(f"Progress: {downloaded / (1024*1024):.2f} MB", end='\r')

        print(f"\nDownload complete: {save_path}")
        return save_path

    except Exception as e:
        print(f"Download failed: {e}")
        return None



def cleanup_file(file_path):
    """Deletes the local file if it exists."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Successfully deleted local file: {file_path}")
        else:
            print(f"Cleanup skipped: {file_path} does not exist.")
    except Exception as e:
        print(f"Error during cleanup: {e}")
def upload_temp(file_path):
    if not file_path or not os.path.exists(file_path):
        return None

    print(f"\n--- Uploading to tmpfiles.org ---")
    
    # tmpfiles.org is often more script-friendly than file.io lately
    url = 'https://tmpfiles.org/api/v1/upload'
    try:
        with open(file_path, 'rb') as f:
            files = {'file': f}
            res = requests.post(url, files=files)
            
        res.raise_for_status()
        data = res.json()
        
        # tmpfiles.org returns a view URL, we need the DOWNLOAD URL
        # Convert https://tmpfiles.org/123/file.mp4 -> https://tmpfiles.org/dl/123/file.mp4
        link = data['data']['url']
        direct_link = link.replace("tmpfiles.org/", "tmpfiles.org/dl/")
        
        print(f"Direct Link for Instagram: {direct_link}")
        cleanup_file(file_path)
        return direct_link
    except Exception as e:
        print(f"Upload failed: {e}")
        return None




def get_temp_public_url(video_url, user_id):
    file_path = download_video(video_url, folder="videos", filename=user_id+str(random.randint(1, 1000000)))
    return upload_temp(file_path)

def clean_caption(caption):
    print("Caption: ",caption)
    # Remove @username patterns
    caption = re.sub(r'@\w+', '', caption).strip()
    print("Cleaned Caption: ",caption)
    return caption



def upload_reel(reel_url_from_webhook, caption , access_token, user_id):
    url = get_temp_public_url(reel_url_from_webhook , user_id)
    try:
        caption = clean_caption(caption)
        # STEP 1: Create media container
        create_url = f"https://graph.instagram.com/v25.0/{user_id}/media"
        create_payload = {
            "media_type": "REELS",
            "video_url": url,
            "caption": caption,
            "share_to_feed": "true",
            "thumb_offset": "2000",
            "access_token": access_token
        }

        
        create_res = requests.post(create_url, data=create_payload)
        create_res.raise_for_status()
        creation_id = create_res.json().get("id")
        print("Container created:", creation_id)
        
        # STEP 2: Poll until processing is complete
        status = "IN_PROGRESS"
        while status == "IN_PROGRESS":
            time.sleep(5)  # wait 5 seconds before checking again
            status_url = f"https://graph.instagram.com/v25.0/{creation_id}"
            status_params = {
                "fields": "status_code",
                "access_token": access_token
            }
            status_res = requests.get(status_url, params=status_params)
            status_res.raise_for_status()
            status = status_res.json().get("status_code")
            print("Processing status:", status)
            
            if status == "ERROR":
                raise Exception("Media processing failed")
        
        # STEP 3: Publish the media
        publish_url = f"https://graph.instagram.com/v25.0/{user_id}/media_publish"
        publish_params = {
            "creation_id": creation_id,
            "access_token": access_token
        }
        publish_res = requests.post(publish_url, params=publish_params)
        publish_res.raise_for_status()
        
        print("Published successfully:", publish_res.json())
        return publish_res.json()
    
    except requests.exceptions.RequestException as e:
        print("Request failed:", e)
        return None
    except Exception as ex:
        print("Error:", ex)
        return None