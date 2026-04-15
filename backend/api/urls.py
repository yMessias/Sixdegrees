from django.urls import path
from . import views

urlpatterns = [
    path('health/', views.health),
    path('search/', views.search_actor),
    path('connect/', views.find_connection),
    path('connect/start/', views.start_connection_search),
    path('connect/status/<str:job_id>/', views.connection_search_status),
    path('connect/cancel/<str:job_id>/', views.cancel_connection_search),
    path('insight/', views.ai_insight),
]
