from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('accounts/signup/', views.signup, name='signup'),
    path('timetable/', views.timetable, name='timetable'),
    path('courses/new/', views.course_create, name='course_create'),
    path('courses/<int:pk>/edit/', views.course_update, name='course_update'),
    path('courses/<int:pk>/delete/', views.course_delete, name='course_delete'),
    path('share/settings/', views.share_settings, name='share_settings'),
    path('s/<uuid:token>/', views.shared_timetable, name='shared_timetable'),
]
