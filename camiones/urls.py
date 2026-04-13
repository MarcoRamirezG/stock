from django.urls import path

from camiones import views

app_name = 'camiones'

urlpatterns = [
    path('', views.pesaje_list, name='pesaje_list'),
    path('pesaje/<int:pesaje_id>/', views.pesaje_detail, name='pesaje_detail'),
]
