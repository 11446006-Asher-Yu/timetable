from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CourseForm, CourseTimeFormSet, SignUpForm
from .models import Course, CourseTime, Period


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


# 課表至少顯示到第 8 節，有更晚的課再往下延伸
MIN_LAST_PERIOD = 8


def build_grid(courses):
    """把課程排進「星期 × 節次」的 CSS Grid。

    第 1 列是星期標題、第 1 欄是節次，所以格子的列、欄都從 2 開始。
    """
    times = [time for course in courses for time in course.times.all()]

    # 週一到週五固定顯示，週末有課才顯示
    weekdays = [day for day in CourseTime.Weekday if day <= 5 or any(t.weekday == day for t in times)]
    last_number = max([MIN_LAST_PERIOD] + [t.end_period.number for t in times])
    periods = list(Period.objects.filter(number__lte=last_number))
    row_of = {period.number: index + 2 for index, period in enumerate(periods)}
    column_of = {day: index + 2 for index, day in enumerate(weekdays)}

    blocks = []
    for course in courses:
        for time in course.times.all():
            blocks.append({
                'course': course,
                'time': time,
                'column': column_of[time.weekday],
                'row': row_of[time.start_period.number],
                'span': time.end_period.number - time.start_period.number + 1,
            })

    return {
        'weekdays': [{'value': day, 'label': day.label[-1], 'column': column_of[day]} for day in weekdays],
        'periods': [{'period': period, 'row': row_of[period.number]} for period in periods],
        'cells': [
            {'row': row_of[period.number], 'column': column_of[day]}
            for period in periods for day in weekdays
        ],
        'blocks': blocks,
        'column_count': len(weekdays),
    }


@login_required
def timetable(request):
    courses = list(
        request.user.courses.prefetch_related('times__start_period', 'times__end_period')
    )
    subtotals = {
        row['category']: row['credits']
        for row in request.user.courses.values('category').annotate(credits=Sum('credits'))
    }
    categories = [
        {
            'label': category.label,
            'color': Course.CATEGORY_COLORS[category],
            'credits': subtotals.get(category, 0),
        }
        for category in Course.Category
    ]
    return render(request, 'schedule/timetable.html', {
        'courses': courses,
        'grid': build_grid(courses),
        'categories': categories,
        'total_credits': sum(subtotals.values()),
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
