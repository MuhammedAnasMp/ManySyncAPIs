from django.db import models
from apps.base import BaseModel

class AiGeneration(BaseModel):
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='ai_generations')
    type = models.CharField(max_length=100) # e.g., 'caption_generation', 'image_prompt'
    input_data_json = models.JSONField()
    output_text = models.TextField()

    def __str__(self):
        return f"AI Generation ({self.type}) for {self.workspace}"

# Create your models here.
