from django.urls import path
from . import views
from django.shortcuts import redirect

# Homepage redirect → goes to login page
def home_redirect(request):
    return redirect('chat')

urlpatterns = [
    path("", home_redirect),  # Fix homepage 404
    path("login/", views.login_home, name="login"),
    path("login/api/", views.login_api, name="login_api"),
    path("chat/", views.chat_page, name="chat"),
    path("logout/", views.logout_view, name="logout"),
    path("api/chat/", views.chat_api, name="chat_api"),
    path("api/train-model/", views.train_model_api, name="train_model_api"),
    path("api/model-status/", views.model_status_api, name="model_status_api"),
    path("api/load-model/", views.load_model_api, name="load_model_api"),
    # path("api/get-intent/", views.get_intent_api, name="get_intent_api"),
    
    
        # ✅ Conversation history endpoints
    path('api/conversations/', views.get_conversations, name='get_conversations'),
    path('api/conversations/save/', views.save_conversation, name='save_conversation'),
    path('api/conversations/load/', views.load_conversation, name='load_conversation'),
    path('api/conversations/delete/', views.delete_conversation, name='delete_conversation'),
    path("api/chat/search/", views.search_conversations, name="chat_search"),
]
