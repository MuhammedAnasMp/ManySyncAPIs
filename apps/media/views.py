import os
import cloudinary
import cloudinary.uploader
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from dotenv import load_dotenv

# Load credentials from .env file (Recommended)
load_dotenv()

cloud_name = "dyt8amitd"
api_key = "479972762797567"
api_secret = "KxVMp1YTMVty8XzcvNZn_Gegvv0"

# Initialize Cloudinary
cloudinary.config(
    cloud_name=cloud_name,
    api_key=api_key,
    api_secret=api_secret
)

@api_view(['POST', 'DELETE'])
@permission_classes([AllowAny])
def delete_media_view(request):
    """
    Deletes an asset based on its type.
    """
    public_id = request.data.get('public_id')
    media_type = request.data.get('media_type')

    if not public_id or not media_type:
        return Response({"error": "Missing public_id or media_type."}, status=status.HTTP_400_BAD_REQUEST)
    
    # Map user-friendly types to Cloudinary resource_types
    # Note: Cloudinary stores Audio files inside the 'video' resource type
    type_map = {
        "image": "image",
        "video": "video",
        "audio": "video"  # Audio files (mp3, wav) are stored as 'video' resource
    }
    
    resource_type = type_map.get(media_type.lower())
    
    if not resource_type:
        return Response({"error": f"Invalid media type '{media_type}'. Use 'image', 'video', or 'audio'."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        response = cloudinary.uploader.destroy(
            public_id,
            resource_type=resource_type,
            invalidate=True  # Purges CDN cache immediately
        )

        if response.get("result") == "ok":
            return Response({"success": f"{media_type.upper()} '{public_id}' deleted permanently."}, status=status.HTTP_200_OK)
        elif response.get("result") == "not found":
            return Response({"success": f"'{public_id}' does not exist or was already deleted.", "not_found": True}, status=status.HTTP_200_OK)
        else:
            return Response({"error": f"FAILED: {response}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
