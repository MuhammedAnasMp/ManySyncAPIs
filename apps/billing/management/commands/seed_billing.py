from django.core.management.base import BaseCommand
from apps.billing.models import Plan, Feature, PlanFeature, PlanQuota ,PlanKey

class Command(BaseCommand):
    help = 'Seeds initial billing plans and features into the database'

    def handle(self, *args, **kwargs):
        features_data = [
                {'code': 'caption', 'description': 'Basic AI Captioning'},
                {'code': 'hashtags', 'description': 'Basic AI Hashtags generation'},
                {'code': 'thumbnail', 'description': 'Custom thumbnail control'},
                {'code': 'custom_audio', 'description': 'Custom audio control'},
                {'code': 'image_to_reel', 'description': 'Image to Reel Rendering Engine'},
                {'code': 'template_image_posting', 'description': 'Template image posting'},
                {'code': 'template_reel_posting', 'description': 'Template reel posting'},
                {'code': 'template_story_posting', 'description': 'Template story posting'},
                {'code': 'template_video_posting', 'description': 'Template video posting'},
                {'code': 'intros_outros', 'description': 'Intros and Outros'},
                {'code': 'publish_template', 'description': 'Publish template to marketplace'}
        ]
        
        feature_objs = {}
        for f in features_data:
            obj, _ = Feature.objects.get_or_create(code=f['code'], defaults={'description': f['description']})
            feature_objs[f['code']] = obj
            
        plans_data = [
            {
                'name': 'Free',
                'price': 0.00,
                'quotas': [
                    {'key': 'posts_per_month', 'value': 50},
                    {'key': 'posts_per_day', 'value': 2},
                    {'key': 'template_count', 'value': 1},
                    {'key': 'account_count', 'value': 1},
                ],
                'features': ['caption', 'hashtags']    
            },
            {
                'name': 'Starter',
                'price': 149.00,
                'quotas': [
                        {'key': 'posts_per_month', 'value': 100},
                        {'key': 'posts_per_day', 'value': 5},
                        {'key': 'template_count', 'value': 5},
                        {'key': 'account_count', 'value': 2},
                    ],
                'features': ['caption', 'hashtags']
            },
            {
                'name': 'Creator',
                'price': 399.00,
                'quotas': [
                        {'key': 'posts_per_month', 'value': 500},
                        {'key': 'posts_per_day', 'value': 10},
                        {'key': 'template_count', 'value': 15},
                        {'key': 'account_count', 'value': 5},
                    ],
                'features': ['caption', 'hashtags', 'thumbnail', 'image_to_reel', 'publish_template']
            },
            {
                'name': 'Pro',
                'price': 999.00,
                'quotas': [
                        {'key': 'posts_per_month', 'value': 1500},
                        {'key': 'posts_per_day', 'value': 20},
                        {'key': 'template_count', 'value': 50},
                        {'key': 'account_count', 'value': 15},
                    ],
                'features': ['caption', 'hashtags', 'thumbnail', 'image_to_reel', 'publish_template']
            }
        ]
        
      

        # Assume feature_objs is a dict: {'caption': Feature_obj, 'hashtags': Feature_obj, ...}
        for p in plans_data:
            plan, created = Plan.objects.get_or_create(
                name=p['name'],
                defaults={'price': p['price'], 'is_active': True}
            )
            if not created:
                plan.price = p['price']
                plan.save()

            for quota in p['quotas']:
                key_obj, _ = PlanKey.objects.get_or_create(name=quota['key'])
                PlanQuota.objects.update_or_create(
                    plan=plan,
                    key=key_obj,
                    defaults={'value': quota['value']}
                )

            # Create features
            for feature_code in p['features']:
                PlanFeature.objects.update_or_create(
                    plan=plan,
                    feature=feature_objs[feature_code],
                    defaults={'enabled': True}
                )

        print("DONE! Plans, quotas, and features seeded successfully!")

        self.stdout.write(self.style.SUCCESS("Successfully seeded plans, features, and quotas!"))
