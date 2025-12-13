from django.contrib import admin

# Register your models here.
# admin.py mein register karo
from .models import ChatConversation
admin.site.register(ChatConversation)
