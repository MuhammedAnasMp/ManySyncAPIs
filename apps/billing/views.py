from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.conf import settings
from .models import Plan, Subscription, PlanFeature, PlanQuota, Usage, Transaction 
from apps.platforms.models import DeveloperAppAccount, Template
from .utils import can_post, get_quota
import razorpay
import json
from django.utils import timezone
from datetime import timedelta

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

class PlanListView(APIView):
    # permission_classes = [IsAuthenticated] # Temporarily disabled or keep depending on usage
    
    def get(self, request):
        plans = Plan.objects.filter(is_active=True).prefetch_related('features__feature', 'quotas')
        data = []
        for p in plans:
            features = p.features.filter(enabled=True).values_list('feature__code', flat=True)
            quotas = {q.key.name: q.value for q in p.quotas.all() if q.key.name != 'posts_per_month'}
            data.append({
                'id': p.id,
                'name': p.name,
                'price': str(p.price),
                'quotas': quotas,
                'features': list(features),
            })
            
        addons = [
            {'id': 'addon_50', 'name': '100 posts add-on', 'price': 50, 'posts': 100},
            {'id': 'addon_90', 'name': '250 posts add-on', 'price': 90, 'posts': 250},
        ]
        
        return Response({'plans': data, 'addons': addons})

class CreateOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        plan_id = request.data.get('plan_id')
        addon_id = request.data.get('addon_id')
        
        amount = 0
        currency = "INR"
        notes = {}
        
        if plan_id:
            try:
                plan = Plan.objects.get(id=plan_id)
                amount = int(plan.price * 100) # Razorpay accepts paisa
                notes = {'plan_id': str(plan.id), 'user_id': str(request.user.id)}
            except Plan.DoesNotExist:
                return Response({'error': 'Plan not found'}, status=status.HTTP_404_NOT_FOUND)
                
        elif addon_id:
            if addon_id == 'addon_50':
                amount = 50 * 100
                notes = {'addon': 'addon_50', 'posts': "100", 'user_id': str(request.user.id)}
            elif addon_id == 'addon_90':
                amount = 90 * 100
                notes = {'addon': 'addon_90', 'posts': "250", 'user_id': str(request.user.id)}
            else:
                return Response({'error': 'Addon not found'}, status=status.HTTP_404_NOT_FOUND)
        else:
            return Response({'error': 'Provide plan_id or addon_id'}, status=status.HTTP_400_BAD_REQUEST)
            
        order_receipt = f"rcpt_{str(request.user.id)[:10]}_{amount}"
        try:
            order_data = {
                "amount": amount,
                "currency": currency,
                "receipt": order_receipt,
                "notes": notes
            }
            order = client.order.create(data=order_data)
            return Response({
                'order_id': order['id'],
                'amount': order['amount'],
                'currency': order['currency'],
                'key_id': settings.RAZORPAY_KEY_ID
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class VerifyPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_order_id = request.data.get('razorpay_order_id')
        razorpay_signature = request.data.get('razorpay_signature')
        
        if not all([razorpay_payment_id, razorpay_order_id, razorpay_signature]):
            return Response({'error': 'Missing parameters'}, status=status.HTTP_400_BAD_REQUEST)
            
        params_dict = {
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        }
        
        try:
            client.utility.verify_payment_signature(params_dict)
        except razorpay.errors.SignatureVerificationError:
            return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
            
        # Fetch order from Razorpay to read notes
        order = client.order.fetch(razorpay_order_id)
        notes = order.get('notes', {})
        
        user_id = notes.get('user_id')
        
        if str(request.user.id) != str(user_id):
            return Response({'error': 'Account mismatch'}, status=status.HTTP_403_FORBIDDEN)
            
        plan_id = notes.get('plan_id')
        addon = notes.get('addon')
        
        amount_in_paisa = order.get('amount', 0)
        amount = amount_in_paisa / 100
        currency = order.get('currency', 'INR')
        
        item_name = "Unknown Item"
        posts_to_add = 0

        now = timezone.now()
        sub = Subscription.objects.filter(user=request.user).first()

        PLAN_RANK = {'Free': 0, 'Starter': 1, 'Creator': 2, 'Pro': 3}
        old_rank = -1
        if sub and sub.plan:
            old_rank = PLAN_RANK.get(sub.plan.name, 0)

        if plan_id:
            plan = Plan.objects.get(id=plan_id)
            item_name = plan.name

            if sub:
                if sub.plan != plan:
                    # Changing plan
                    print(f"DEBUG: Changing plan from {sub.plan} to {plan}")
                    sub.plan = plan
                    sub.start_date = now
                    sub.end_date = now + timedelta(days=30)
                    sub.is_active = True
                    # sub.credit = 0  # Preserve existing credits
                    sub.save()
                elif sub.is_active and sub.end_date and sub.end_date > now:
                    # Renewing same plan
                    sub.end_date += timedelta(days=30)
                    print(f"DEBUG: Renewing same plan, new end date={sub.end_date}")
                    sub.save()
                else:
                    # Reactivating expired plan
                    sub.start_date = now
                    sub.end_date = now + timedelta(days=30)
                    sub.is_active = True
                    sub.plan = plan
                    # sub.credit = 0  # Preserve existing credits
                    sub.save()
                    print(f"DEBUG: Reactivating plan {plan}, start={sub.start_date}, end={sub.end_date}")
            else:
                # No subscription exists
                sub = Subscription.objects.create(
                    user=request.user,
                    plan=plan,
                    is_active=True,
                    start_date=now,
                    end_date=now + timedelta(days=30),
                    credit=0
                )
                print(f"DEBUG: Created new subscription with plan {plan}, start={sub.start_date}, end={sub.end_date}")

            # Upgrade Logic: Handled by Subscription.save()
            pass

        # If the transaction also includes manually bundled credits in notes (e.g. promotional)
        posts_to_add_note = int(notes.get('posts', 0))
        if plan_id and posts_to_add_note > 0:
            sub.credit += posts_to_add_note
            sub.save()
            print(f"DEBUG: Added manually bundled plan credits: {posts_to_add_note}")

        elif addon:
            posts_to_add = int(notes.get('posts', 0))
            
            if addon == 'addon_50':
                item_name = '100 posts Add-on'
            elif addon == 'addon_90':
                item_name = '250 posts Add-on'
            else:
                item_name = f'{posts_to_add} posts Add-on'
                
            print(f"DEBUG: Adding addon posts={posts_to_add}")
            if sub:
                sub.credit += posts_to_add
                sub.save()
                print(f"DEBUG: Updated subscription credit={sub.credit}")
            else:
                sub = Subscription.objects.create(
                    user=request.user,
                    plan=None,
                    is_active=False,
                    credit=posts_to_add
                )
                print(f"DEBUG: Created new subscription with credit={sub.credit}")
        sub.save()
        print(f"DEBUG: Subscription updated: plan={sub.plan}, start={sub.start_date}, end={sub.end_date}, credit={sub.credit}")
        # Record transaction
        if plan_id or addon:
            Transaction.objects.create(
                user=request.user,
                item_name=item_name,
                amount=amount,
                currency=currency,
                razorpay_order_id=razorpay_order_id,
                razorpay_payment_id=razorpay_payment_id,
                status='success'
            )
            msg = f'Successfully subscribed to {item_name}' if plan_id else f'Successfully added {posts_to_add} posts'
            return Response({'message': msg})
            
        return Response({'message': 'Verified but no plan or addon found in notes'})

class TransactionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        transactions = Transaction.objects.filter(user=request.user)
        data = [{
            'id': t.id,
            'item_name': t.item_name,
            'amount': str(t.amount),
            'currency': t.currency,
            'razorpay_order_id': t.razorpay_order_id,
            'razorpay_payment_id': t.razorpay_payment_id,
            'status': t.status,
            'created_at': t.created_at
        } for t in transactions]
        return Response({'transactions': data})

class UserSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # try:
            sub = request.user.subscription
            if not sub.plan or not sub.is_active:
                return Response({'has_plan': False})
                
            features = list(PlanFeature.objects.filter(plan=sub.plan, enabled=True).values_list('feature__code', flat=True))
            
            # usage_posts = Usage.objects.filter(user=request.user, key='posts_per_month').first()
            # posts_used = usage_posts.used if usage_posts else 0

            credits_available = sub.credit
            
            from apps.billing.models import UsageLog
            from django.db.models import Sum

            template_quota = get_quota(request.user, 'template_count')
            account_quota = get_quota(request.user, 'account_count')
            daily_quota = get_quota(request.user, 'posts_per_day')
            
            # Daily posts used
            today = timezone.now().date()
            daily_posts_used = UsageLog.objects.filter(
                user=request.user, 
                key='posts', 
                date=today
            ).aggregate(total=Sum('count'))['total'] or 0

            # Enforce account quota: deactivate extra accounts if necessary
            all_accounts = list(DeveloperAppAccount.objects.filter(user=request.user).order_by('created_at'))
            active_accounts_count = 0
            for acc in all_accounts:
                if acc.is_active:
                    if active_accounts_count < account_quota:
                        active_accounts_count += 1
                    else:
                        # Over limit, deactivate
                        acc.is_active = False
                        acc.save()

            templates_used = Template.objects.filter(created_by=request.user).count()
            accounts_used = DeveloperAppAccount.objects.filter(user=request.user, is_active=True).count()
            
            can_add_template = templates_used < template_quota
            can_add_account = accounts_used < account_quota
            
            return Response({
                'has_plan': True,
                'plan_name': sub.plan.name,
                'is_active': sub.is_active,
                'start_date': sub.start_date,
                'end_date': sub.end_date,
                'features': features,
                'quotas': {
                    # 'posts_per_month': get_quota(request.user, 'posts_per_month'),
                    'posts_per_day': daily_quota,
                    'template_count': template_quota,
                    'account_count': account_quota
                },
                'usage': {
                    # 'posts_used': posts_used,
                    'daily_posts_used': daily_posts_used,
                    'templates_used': templates_used,
                    'accounts_used': accounts_used,
                    'credits_available': credits_available,
                    'can_post': can_post(request.user),
                    'can_add_template': templates_used < template_quota,
                    'can_add_account': accounts_used < account_quota
                }
            })
        # except Exception:
            # return Response({'has_plan': False})
