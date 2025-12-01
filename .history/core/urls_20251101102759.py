from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.login_home, name="login"),
    path("login/api/", views.login_api, name="login_api"),
    path("chat/", views.chat_page, name="chat"),
    path("logout/", views.logout_view, name="logout"),
    path("api/chat/", views.chat_api, name="chat_api"),
    path("api/train-model/", views.train_model_api, name="train_model_api"),
    path("api/model-status/", views.model_status_api, name="model_status_api"),
    path("api/load-model/", views.load_model_api, name="load_model_api"),
]
