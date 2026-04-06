from django.contrib import admin
from .models import Plan, Feature, PlanFeature, PlanQuota, Subscription, Usage, Transaction

class PlanFeatureInline(admin.TabularInline):
    model = PlanFeature
    extra = 1

class PlanQuotaInline(admin.TabularInline):
    model = PlanQuota
    extra = 1


    

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'is_active')
    inlines = [PlanFeatureInline, PlanQuotaInline]

@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ('code', 'description')

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'is_active', 'start_date', 'end_date')

@admin.register(Usage)
class UsageAdmin(admin.ModelAdmin):
    list_display = ('user', 'key', 'used', 'period_start')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'item_name', 'amount', 'status', 'created_at')
