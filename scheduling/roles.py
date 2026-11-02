"""角色判斷、權限裝飾器，以及給模板用的 context processor。"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import SCHEDULERS, TEACHERS


def _in_group(user, name):
    if not user.is_authenticated:
        return False
    # 同一個請求裡會判斷很多次，結果暫存在 user 上
    cache = getattr(user, '_group_names', None)
    if cache is None:
        cache = set(user.groups.values_list('name', flat=True))
        user._group_names = cache
    return name in cache


def is_scheduler(user):
    return user.is_authenticated and (user.is_superuser or _in_group(user, SCHEDULERS))


def is_teacher(user):
    return _in_group(user, TEACHERS)


def display_name(user):
    return user.get_full_name() or user.get_username()


def home_url_name(user):
    """登入後的首頁：排課人員到排課總覽、老師到老師首頁，其他人（學生）到我的課表。"""
    if is_scheduler(user):
        return 'scheduling:dashboard'
    if is_teacher(user):
        return 'scheduling:teacher_home'
    return 'timetable'


def _role_required(check):
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not check(request.user):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


scheduler_required = _role_required(is_scheduler)
teacher_required = _role_required(is_teacher)


def roles(request):
    user = getattr(request, 'user', None)
    if user is None:
        return {}
    scheduler, teacher = is_scheduler(user), is_teacher(user)
    # 排課人員、老師的選單只顯示自己的工作頁；個人課表與課程目錄仍可從網址進入
    return {'is_scheduler': scheduler, 'is_teacher': teacher, 'is_staff_role': scheduler or teacher}
