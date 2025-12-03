from django.db import models

# Create your models here.
# models.py mein add karo
from django.db import models
from django.contrib.auth.models import User

class ChatConversation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    employee_id = models.CharField(max_length=50)  # ya session se
    conv_id = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=200)
    messages = models.JSONField()
    timestamp = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.employee_id} - {self.title}"
