from django.urls import path, re_path

from . import views

app_name = 'scheduling'

KINDS = r'(?P<kind>classrooms|groups|terms)'

urlpatterns = [
    # 排課人員
    path('scheduler/', views.dashboard, name='dashboard'),
    re_path(rf'^scheduler/{KINDS}/$', views.manage_list, name='manage'),
    re_path(rf'^scheduler/{KINDS}/(?P<pk>\d+)/edit/$', views.manage_list, name='manage_edit'),
    re_path(rf'^scheduler/{KINDS}/(?P<pk>\d+)/delete/$', views.manage_delete, name='manage_delete'),
    path('scheduler/terms/<int:pk>/availability/', views.term_availability, name='term_availability'),
    path('scheduler/offerings/', views.offering_list, name='offerings'),
    path('scheduler/offerings/new/', views.offering_edit, name='offering_new'),
    path('scheduler/offerings/send/', views.offering_send_all, name='offering_send_all'),
    path('scheduler/offerings/<int:pk>/edit/', views.offering_edit, name='offering_edit'),
    path('scheduler/offerings/<int:pk>/delete/', views.offering_delete, name='offering_delete'),
    path('scheduler/offerings/<int:pk>/schedule/', views.board, name='board'),
    path('scheduler/teachers/', views.teachers, name='teachers'),
    path('scheduler/invitations/<int:pk>/resend/', views.invitation_resend, name='invitation_resend'),
    path('scheduler/requests/', views.requests_list, name='requests'),
    path('scheduler/requests/<int:pk>/resolve/', views.request_resolve, name='request_resolve'),
    path('scheduler/publish/', views.publish, name='publish'),
    # 老師
    path('invite/<uuid:token>/', views.accept_invite, name='accept_invite'),
    path('teacher/', views.teacher_home, name='teacher_home'),
    path('teacher/availability/', views.availability, name='availability'),
    path('teacher/offerings/', views.teaching, name='teaching'),
    path('teacher/offerings/<int:pk>/request-change/', views.request_change, name='request_change'),
    # 學生
    path('catalog/', views.catalog, name='catalog'),
]
