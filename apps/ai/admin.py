from django.contrib import admin
from .models import AiGeneration

@admin.register(AiGeneration)
class AiGenerationAdmin(admin.ModelAdmin):
    list_display = ('type', 'workspace', 'created_at')
    list_filter = ('type', 'workspace')
    search_fields = ('output_text', 'workspace__name')
