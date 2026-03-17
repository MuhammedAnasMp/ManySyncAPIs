from rest_framework import views, response, status
from rest_framework.permissions import IsAuthenticated

class DashboardStatsView(views.APIView):
    """
    View to provide mockup stats for the dashboard.
    Requires authentication to verify token passing.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Mock data for demonstration
        data = {
            "instagram": {
                "followers": 12500,
                "posts": 145,
                "engagement_rate": "4.2%"
            },
            "youtube": {
                "subscribers": 45200,
                "videos": 86,
                "views": 2800000
            }
        }
        return response.Response(data, status=status.HTTP_200_OK)
