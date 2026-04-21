
import requests,time,os,re,random
from .renderer import render_video, render_thumbnail, render_image
BACKEND_HOST = os.getenv("BACKEND_HOST")
from urllib.parse import urlparse
from django.conf import settings

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

def remove_local_file(url):
    try:
        parsed = urlparse(url)
        
        # /media/videos/file.mp4 → videos/file.mp4
        relative_path = parsed.path.replace(settings.MEDIA_URL, "")
        
        # Build full path
        file_path = os.path.join(settings.MEDIA_ROOT, relative_path)
        
        cleanup_file(file_path)
        
    except Exception as e:
        print(f"Error during cleanup: {e}")

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
        print("file_path",file_path)
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
    file_path = download_video(video_url, folder="media/videos", filename=user_id+str(random.randint(1, 1000000)))
    # return upload_temp(file_path)


    if not file_path:
        return None
    
    filename = os.path.basename(file_path)
    return f"https://{BACKEND_HOST}/media/videos/{filename}"

def clean_caption(caption):
    if not caption: return ""
    # Remove @usernames
    caption = re.sub(r'@[A-Za-z0-9._]+', '', caption)
    # Remove #hashtags
    caption = re.sub(r'#[A-Za-z0-9_]+', '', caption)
    # Remove IG spacers (lines with solo dots/bullets)
    caption = re.sub(r'(?m)^\s*[\.\•]+\s*$', '', caption)
    # Collapse multiple newlines
    caption = re.sub(r'\n{3,}', '\n\n', caption)
    return caption.strip()



def deactivate_account(account, reason="API Error"):
    """Deactivates a DeveloperAppAccount and notifies the user."""
    if account and account.is_active:
        account.is_active = False
        account.save()
        try:
            create_notification(
                user=account.user,
                account=account,
                title="Account Deactivated",
                message=f"Your account '{account.account_name}' has been deactivated due to an error. Please re-connect it to resume posting.",
                type='error'
            )
            print(f"🔴 Account {account.account_id} deactivated due to: {reason}")
        except Exception as e:
            print(f"Failed to create deactivation notification: {e}")



def upload_reel(reel_url_from_webhook, caption, access_token, user_id, template_json=None, configuration=None):
    output_path = f"rendered_{user_id}_{random.randint(1, 1000000)}.mp4"
    thumb_output_path = f"thumb_{user_id}_{random.randint(1, 1000000)}.png"
    
    url = None
    cover_url = None
    
    # 1. Handle Rendering (Video)
    from .models import DeveloperAppAccount
    account = DeveloperAppAccount.objects.filter(account_id=user_id).first()
    
    if account and not account.is_active:
        print(f"⚠️ Account {user_id} is inactive. Skipping reel upload.")
        return None
    
    if template_json:
        print(f"🎨 Rendering reel with template for user {user_id}...")
        try:
            video_path = render_video(template_json, configuration or {}, reel_url_from_webhook, output_path, account=account, raw_caption=caption)
            url = upload_temp(video_path)
            if os.path.exists(output_path):
                os.remove(output_path)
        except Exception as render_ex:
            print(f"❌ Rendering failed: {render_ex}. Falling back to original video.")
            url = get_temp_public_url(reel_url_from_webhook, user_id)
    else:
        url = get_temp_public_url(reel_url_from_webhook, user_id)

    # 2. Handle Thumbnail
    if configuration and "thumbnail" in configuration:
        t_cfg = configuration["thumbnail"]
        t_mode = t_cfg.get("mode", "off")
        
        if t_mode == "custom" and t_cfg.get("value"):
            print(f"🖼️ Using custom thumbnail: {t_cfg['value']}")
            cover_url = t_cfg["value"]
        elif t_mode == "template" and template_json:
            print("🖼️ Generating thumbnail from template...")
            try:
                thumb_path = render_thumbnail(template_json, configuration, reel_url_from_webhook, thumb_output_path, account=account, raw_caption=caption)
                if thumb_path:
                    cover_url = upload_temp(thumb_path)
                    if os.path.exists(thumb_output_path):
                        os.remove(thumb_output_path)
            except Exception as thumb_ex:
                print(f"❌ Thumbnail generation failed: {thumb_ex}")

    if not url:
        print("❌ Failed to get a public URL for the video.")
        return None

    try:
        # Step 0: Determine caption from configuration if available
        if configuration and configuration.get("caption", {}).get("mode") == "custom":
            caption = configuration["caption"].get("value", caption)
        
        caption = clean_caption(caption)

        # Add hashtags if available
        if configuration and configuration.get("hashtags", {}).get("mode") == "custom":
            tags = configuration["hashtags"].get("value", [])
            if tags:
                tag_string = " ".join([f"#{t.strip().lstrip('#')}" for t in tags if t.strip()])
                caption = f"{caption}\n\n{tag_string}"
        
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
        
        if cover_url:
            print(f"📎 Adding cover_url: {cover_url}")
            create_payload["cover_url"] = cover_url

        
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
        if account and account.user:
            create_notification(
                user=account.user,
                account=account,
                title="Reel Uploaded Successfully",
                message=f"Your reel has been successfully uploaded to {account.account_name}.",
                type='success'
            )
        remove_local_file(url)
        return publish_res.json()
    
    except requests.exceptions.RequestException as e:
        print("Request failed:", e)
        deactivate_account(account, str(e))
        return None
    except Exception as ex:
        print("Error:", ex)
        deactivate_account(account, str(ex))
        return None

def upload_post(image_url_from_webhook, caption, access_token, user_id, template_json=None, configuration=None):
    output_path = f"rendered_post_{user_id}_{random.randint(1, 1000000)}.png"
    
    # Check if we should render as a reel even if it's a post, based on ENV
    from django.conf import settings
    render_mode_env = os.getenv("RENDER_MODE", "POST").strip().upper()
    print(f"DEBUG: Current RENDER_MODE from ENV: '{render_mode_env}'")
    
    render_as_reel = render_mode_env == "REEL"
    
    # Determine if we should use the visual template or fall back to a simple full-frame image-to-reel
    # We use default if: no template provided OR user explicitly disabled 'use_template' in config
    use_visual_template = True
    if configuration and "custom_audio" in configuration:
        use_visual_template = configuration["custom_audio"].get("use_template", True)

    if render_as_reel and (not template_json or not use_visual_template):
        print(f"ℹ️ {'No template found' if not template_json else 'Template disabled'} for user {user_id}. Using default aspect-ratio Reel template.")
        
        # Determine image aspect ratio to avoid stretching
        img_h = 720
        img_y = 0
        try:
            temp_dim_filename = f"dim_{user_id}_{random.randint(1, 1000000)}"
            local_img = download_video(image_url_from_webhook, folder="temp_dims", filename=temp_dim_filename)
            if local_img:
                from PIL import Image as PILImage
                with PILImage.open(local_img) as img:
                    iw, ih = img.size
                    # Scale to width 405
                    ratio = 405.0 / iw
                    img_h = ih * ratio
                    # Center vertically on 720 canvas
                    img_y = (720 - img_h) / 2.0
                if os.path.exists(local_img): os.remove(local_img)
        except Exception as e:
            print(f"⚠️ Could not determine image dimensions: {e}")

        template_json = {
            "bgColor": "#000000",
            "bgEnabled": True,
            "objects": [
                {
                    "id": "main_image",
                    "type": "image",
                    "x": 0,
                    "y": img_y,
                    "width": 405,
                    "height": img_h,
                    "opacity": 1,
                    "visible": True,
                    "src": image_url_from_webhook
                }
            ]
        }

    from .models import DeveloperAppAccount
    account = DeveloperAppAccount.objects.filter(account_id=user_id).first()

    if account and not account.is_active:
        print(f"⚠️ Account {user_id} is inactive. Skipping post upload.")
        return None

    if template_json:
        print(f"🎨 Rendering post with template for user {user_id} (As Reel: {render_as_reel})...")
        try:
            if render_as_reel:
                # Use standard reel rendering
                output_path_reel = output_path.replace(".png", ".mp4")
                video_path = render_video(template_json, configuration or {}, image_url_from_webhook, output_path_reel, account=account, raw_caption=caption)
                url = upload_temp(video_path)
                media_type = "REELS"
            else:
                # Use image rendering
                image_path = render_image(template_json, configuration or {}, image_url_from_webhook, output_path, account=account, raw_caption=caption)
                url = upload_temp(image_path)
                media_type = "IMAGE"
        except Exception as render_ex:
            print(f"❌ Rendering failed: {render_ex}. Falling back to original image.")
            url = get_temp_public_url(image_url_from_webhook, user_id)
            media_type = "IMAGE"
    else:
        url = get_temp_public_url(image_url_from_webhook, user_id)
        media_type = "IMAGE"

    if not url:
        print("❌ Failed to get a public URL for the image.")
        return None

    try:
        # Step 0: Determine caption from configuration if available
        if configuration and configuration.get("caption", {}).get("mode") == "custom":
            caption = configuration["caption"].get("value", caption)
        
        caption = clean_caption(caption)

        # Add hashtags if available
        if configuration and configuration.get("hashtags", {}).get("mode") == "custom":
            tags = configuration["hashtags"].get("value", [])
            if tags:
                tag_string = " ".join([f"#{t.strip().lstrip('#')}" for t in tags if t.strip()])
                caption = f"{caption}\n\n{tag_string}"
        
        # STEP 1: Create media container
        create_url = f"https://graph.instagram.com/v25.0/{user_id}/media"
        print(f"🚀 Creating Instagram {media_type} container for user {user_id}...")
        create_payload = {
            "caption": caption,
            "access_token": access_token
        }
        
        if media_type == "REELS":
            create_payload["media_type"] = "REELS"
            create_payload["video_url"] = url
            create_payload["share_to_feed"] = "true"
            create_payload["thumb_offset"] = "2000"
        else:
            # Default to IMAGE
            create_payload["image_url"] = url

        create_res = requests.post(create_url, data=create_payload)
        create_res.raise_for_status()
        creation_id = create_res.json().get("id")
        print("Container created (Post):", creation_id)
        
        # STEP 2: Poll until processing is complete
        status = "IN_PROGRESS"
        while status == "IN_PROGRESS":
            time.sleep(5)
            status_url = f"https://graph.instagram.com/v25.0/{creation_id}"
            status_params = {"fields": "status_code", "access_token": access_token}
            status_res = requests.get(status_url, params=status_params)
            status_res.raise_for_status()
            status = status_res.json().get("status_code", "FINISHED")
            print("Processing status (Post):", status)
            if status == "ERROR": raise Exception("Media processing failed")
        
        # STEP 3: Publish the media
        publish_url = f"https://graph.instagram.com/v25.0/{user_id}/media_publish"
        publish_params = {"creation_id": creation_id, "access_token": access_token}
        publish_res = requests.post(publish_url, params=publish_params)
        publish_res.raise_for_status()
        
        print("Post published successfully:", publish_res.json())
        if account and account.user:
            create_notification(
                user=account.user,
                account=account,
                title="Post Uploaded Successfully",
                message=f"Your post has been successfully uploaded to {account.account_name}.",
                type='success'
            )
        remove_local_file(url)
        return publish_res.json()
    
    except requests.exceptions.RequestException as e:
        print("Request failed (Post):", e)
        deactivate_account(account, str(e))
        return None
    except Exception as ex:
        print("Error (Post):", ex)
        deactivate_account(account, str(ex))
        return None

def upload_story(media_url_from_webhook, caption, access_token, user_id, template_json=None, configuration=None):
    # Determine if it's a video or image
    is_video = False
    try:
        res = requests.head(media_url_from_webhook)
        content_type = res.headers.get('Content-Type', '')
        if 'video' in content_type:
            is_video = True
    except Exception as e:
        print(f"⚠️ Error checking content type: {e}")
    
    output_path = f"rendered_story_{user_id}_{random.randint(1, 1000000)}" + (".mp4" if is_video else ".png")
    
    from .models import DeveloperAppAccount
    account = DeveloperAppAccount.objects.filter(account_id=user_id).first()
    
    if account and not account.is_active:
        print(f"⚠️ Account {user_id} is inactive. Skipping story upload.")
        return None

    # Determine caption from configuration if available
    if configuration and configuration.get("caption", {}).get("mode") == "custom":
        caption = configuration["caption"].get("value", caption)

    url = None
    if template_json:
        print(f"🎨 Rendering story with template for user {user_id}...")
        try:
            if is_video:
                rendered_path = render_video(template_json, configuration or {}, media_url_from_webhook, output_path, account=account, raw_caption=caption)
            else:
                rendered_path = render_image(template_json, configuration or {}, media_url_from_webhook, output_path, account=account, raw_caption=caption)
            
            url = upload_temp(rendered_path)
            if os.path.exists(output_path):
                os.remove(output_path)
        except Exception as render_ex:
            print(f"❌ Rendering failed: {render_ex}. Falling back to original.")
            url = get_temp_public_url(media_url_from_webhook, user_id)
    else:
        url = get_temp_public_url(media_url_from_webhook, user_id)

    if not url:
        print("❌ Failed to get a public URL for the story.")
        return None

    try:
        # STEP 1: Create media container
        create_url = f"https://graph.instagram.com/v25.0/{user_id}/media"
        create_payload = {
            "media_type": "STORIES",
            "access_token": access_token
        }
        
        if is_video:
            create_payload["video_url"] = url
        else:
            create_payload["image_url"] = url

        create_res = requests.post(create_url, data=create_payload)
        create_res.raise_for_status()
        creation_id = create_res.json().get("id")
        print("Container created (Story):", creation_id)
        
        # STEP 2: Poll until processing is complete
        status = "IN_PROGRESS"
        while status == "IN_PROGRESS":
            time.sleep(5)
            status_url = f"https://graph.instagram.com/v25.0/{creation_id}"
            status_params = {"fields": "status_code", "access_token": access_token}
            status_res = requests.get(status_url, params=status_params)
            status_res.raise_for_status()
            status = status_res.json().get("status_code", "FINISHED")
            print("Processing status (Story):", status)
            if status == "ERROR": raise Exception("Media processing failed")
        
        # STEP 3: Publish the media
        publish_url = f"https://graph.instagram.com/v25.0/{user_id}/media_publish"
        publish_params = {"creation_id": creation_id, "access_token": access_token}
        publish_res = requests.post(publish_url, params=publish_params)
        publish_res.raise_for_status()
        
        print("Story published successfully:", publish_res.json())
        if account and account.user:
            create_notification(
                user=account.user,
                account=account,
                title="Story Uploaded Successfully",
                message=f"Your story has been successfully uploaded to {account.account_name}.",
                type='success'
            )
        remove_local_file(url)
        return publish_res.json()
    
    except Exception as ex:
        print("Error (Story):", ex)
        deactivate_account(account, str(ex))
        return None

def create_notification(user, title, message, account=None, type='info'):
    from .models import Notification
    return Notification.objects.create(
        user=user,
        account=account,
        title=title,
        message=message,
        type=type
    )