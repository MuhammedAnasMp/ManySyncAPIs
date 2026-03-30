from django.core.management.base import BaseCommand
from apps.billing.models import Plan, Feature, PlanFeature, PlanQuota

class Command(BaseCommand):
    help = 'Seeds initial billing plans and features into the database'

    def handle(self, *args, **kwargs):
        features_data = [
            {'code': 'caption', 'description': 'Basic AI Captioning'},
            {'code': 'hashtags', 'description': 'Basic AI Hashtags generation'},
            {'code': 'scheduling', 'description': 'Automated post scheduling'},
            {'code': 'thumbnail', 'description': 'Custom thumbnail control'},
            {'code': 'location', 'description': 'Location tagging for posts'},
            {'code': 'creator_credit', 'description': 'Dynamic creator crediting'},
            {'code': 'priority_queue', 'description': 'Skip ahead in server queue'},
            {'code': 'advanced_caption', 'description': 'Advanced AI caption tools'},
            {'code': 'share_to_post', 'description': 'Share to Post functionality'},
        ]
        
        feature_objs = {}
        for f in features_data:
            obj, _ = Feature.objects.get_or_create(code=f['code'], defaults={'description': f['description']})
            feature_objs[f['code']] = obj
            
        plans_data = [
            {
                'name': 'Free',
                'price': 0.00,
                'quotas': {'apps_limit': 1, 'accounts_limit': 1, 'posts_per_month': 50, 'posts_per_day': 2},
                'features': ['caption', 'hashtags', 'scheduling']    
            },
            {
                'name': 'Starter',
                'price': 149.00,
                'quotas': {'apps_limit': 1, 'accounts_limit': 1, 'posts_per_month': 100, 'posts_per_day': 5},
                'features': ['caption', 'hashtags', 'scheduling']
            },
            {
                'name': 'Creator',
                'price': 399.00,
                'quotas': {'apps_limit': 1, 'accounts_limit': 3, 'posts_per_month': 500, 'posts_per_day': 10},
                'features': ['caption', 'hashtags', 'scheduling', 'thumbnail', 'location', 'creator_credit', 'share_to_post']
            },
            {
                'name': 'Pro',
                'price': 999.00,
                'quotas': {'apps_limit': 100, 'accounts_limit': 10, 'posts_per_month': 1500, 'posts_per_day': 20},
                'features': ['caption', 'hashtags', 'scheduling', 'thumbnail', 'location', 'creator_credit', 'priority_queue', 'advanced_caption', 'share_to_post']
            }
        ]
        
        for p in plans_data:
            plan, created = Plan.objects.get_or_create(name=p['name'], defaults={'price': p['price'], 'is_active': True})
            if not created:
                plan.price = p['price']
                plan.save()
            
            for k, v in p['quotas'].items():
                PlanQuota.objects.update_or_create(plan=plan, key=k, defaults={'value': v})
                
            for feature_code in p['features']:
                PlanFeature.objects.update_or_create(plan=plan, feature=feature_objs[feature_code], defaults={'enabled': True})
                
        self.stdout.write(self.style.SUCCESS("Successfully seeded plans, features, and quotas!"))
