from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CourseForm, CourseTimeFormSet, SignUpForm
from .models import Course


def home(request):
    if request.user.is_authenticated:
        return redirect('timetable')
    return render(request, 'home.html')


def signup(request):
    if request.user.is_authenticated:
        return redirect('timetable')
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # 註冊完直接登入
            messages.success(request, f'歡迎，{user.username}！帳號已建立。')
            return redirect('timetable')
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})


@login_required
def timetable(request):
    # 課表格子在 10/30 實作，目前先以清單顯示
    courses = request.user.courses.prefetch_related('times__start_period', 'times__end_period')
    total_credits = courses.aggregate(total=Sum('credits'))['total'] or 0
    return render(request, 'schedule/timetable.html', {
        'courses': courses,
        'total_credits': total_credits,
    })


def _edit_course(request, course):
    """新增與修改共用：課程本體與上課時段要一起驗證、一起儲存。"""
    is_new = course.pk is None
    if request.method == 'POST':
        form = CourseForm(request.POST, instance=course)
        formset = CourseTimeFormSet(request.POST, instance=course)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                course = form.save()
                formset.instance = course
                formset.save()
            messages.success(request, f'已{"新增" if is_new else "更新"}「{course.name}」。')
            return redirect('timetable')
    else:
        form = CourseForm(instance=course)
        formset = CourseTimeFormSet(instance=course)
    return render(request, 'schedule/course_form.html', {
        'form': form,
        'formset': formset,
        'is_new': is_new,
    })


@login_required
def course_create(request):
    return _edit_course(request, Course(owner=request.user))


@login_required
def course_update(request, pk):
    # 加上 owner 條件：別人的課程一律回 404
    course = get_object_or_404(Course, pk=pk, owner=request.user)
    return _edit_course(request, course)


@login_required
def course_delete(request, pk):
    course = get_object_or_404(Course, pk=pk, owner=request.user)
    if request.method == 'POST':
        name = course.name
        course.delete()
        messages.success(request, f'已刪除「{name}」。')
        return redirect('timetable')
    return render(request, 'schedule/course_confirm_delete.html', {'course': course})
