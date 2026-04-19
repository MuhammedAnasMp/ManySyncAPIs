import os
import django
import random
from datetime import timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'corebackend.settings')
django.setup()

from apps.accounts.models import User
from apps.platforms.models import DeveloperAppAccount
from apps.billing.models import UsageLog

def seed_usage_logs():
    user_id = 'ea2678ab-c5f6-4619-b569-2e536be6e0b2'
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        print(f"User {user_id} not found.")
        return

    accounts = DeveloperAppAccount.objects.filter(user=user)
    if not accounts.exists():
        print("No accounts found for user. Creating dummy accounts...")
        for i in range(3):
            DeveloperAppAccount.objects.create(
                user=user,
                account_name=f"Demo Account {i+1}",
                account_id=f"demo_acc_{random.randint(1000, 9999)}",
                is_active=True
            )
        accounts = DeveloperAppAccount.objects.filter(user=user)

    post_types = ['reel', 'image', 'story', 'video']
    today = timezone.now().date()

    print(f"Seeding logs for user: {user.email}")

    # Create logs for the last 15 days
    for i in range(15):
        log_date = today - timedelta(days=i)
        
        # Pick 2-3 random accounts for each day
        daily_accounts = random.sample(list(accounts), min(len(accounts), random.randint(2, 3)))
        
        for acc in daily_accounts:
            # Create 1-2 different post types per account per day
            for pt in random.sample(post_types, random.randint(1, 2)):
                count = random.randint(1, 4)
                plan_count = random.randint(0, count)
                free_count = count - plan_count
                
                log, created = UsageLog.objects.get_or_create(
                    user=user,
                    account=acc,
                    key=pt,
                    date=log_date,
                    defaults={
                        'count': count,
                        'credit_from_plan': plan_count,
                        'credit_from_free': free_count,
                        'last_success_at': timezone.now() - timedelta(days=i, hours=random.randint(1, 12))
                    }
                )
                
                if not created:
                    log.count += count
                    log.credit_from_plan += plan_count
                    log.credit_from_free += free_count
                    log.save()
                
                print(f"  [{log_date}] {acc.account_name}: {count} {pt}(s)")

    print("Seeding complete.")

if __name__ == "__main__":
    seed_usage_logs()
