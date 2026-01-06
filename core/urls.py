from django.urls import path
from . import views
from django.shortcuts import redirect

# Homepage redirect → goes to login page
def home_redirect(request):
    return redirect('login')

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
    path("api/tada/purposes/", views.tada_purposes, name="tada_purposes"),
    path("api/tada/types/", views.tada_travel_types, name="tada_travel_types"),
    path("api/tada/create/", views.tada_create_request, name="tada_create_request"),
    path("api/tada/local/create/", views.local_tada_create_request, name="local_tada_create_request"),
    path("api/tada/local/purposes/", views.local_tada_purposes, name="local_tada_purposes"),
    path("api/tada/local/types/", views.local_tada_travel_types, name="local_tada_travel_types"),
    
    
    path("api/tada/create/local/", views.tada_create_local, name="tada_create_local"),
    # ==================================================================================
    path("filter-plan/", views.filter_plan_list, name="filter_plan_list"),       # GET
    path("filter-plan/post/", views.filter_plan_post, name="filter_plan_post"), # POST proxy
    path("claim-list/<int:travel_type_id>/", views.claim_list, name="claim_list"),
    path("acceptance-list/<int:travel_type_id>/", views.acceptance_list, name="acceptance_list"),
    path("claim-pdf/<str:token_hash>/", views.download_claim_pdf, name="claim_pdf"),
    # ==================================================================================




]

