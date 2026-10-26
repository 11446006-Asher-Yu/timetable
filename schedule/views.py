from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .conflicts import assign_lanes, find_conflicts
from .forms import CourseForm, CourseTimeFormSet, SignUpForm
from .models import Course, CourseTime, Period, ShareLink


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
    assign_lanes(blocks)

    # 手機版依星期分頁，每天的課依開始節次排序
    days = [
        {
            'value': day,
            'label': day.label[-1],
            'blocks': sorted(
                (b for b in blocks if b['time'].weekday == day),
                key=lambda b: b['time'].start_period.number,
            ),
        }
        for day in weekdays
    ]

    return {
        'weekdays': [{'value': day, 'label': day.label[-1], 'column': column_of[day]} for day in weekdays],
        'days': days,
        'periods': [{'period': period, 'row': row_of[period.number]} for period in periods],
        'cells': [
            {'row': row_of[period.number], 'column': column_of[day], 'weekday': day}
            for period in periods for day in weekdays
        ],
        'blocks': blocks,
        'column_count': len(weekdays),
        'conflict_count': sum(1 for block in blocks if block['conflict']),
    }


def course_details(courses, can_edit):
    """詳細資料視窗用的資料，以 json_script 交給前端 JavaScript。"""
    details = {}
    for course in courses:
        item = {
            'name': course.name,
            'category': course.get_category_display(),
            'color': course.display_color,
            'teacher': course.teacher,
            'classroom': course.classroom,
            'credits': course.credits,
            'times': [str(time) for time in course.times.all()],
            'note': course.note,
        }
        if can_edit:
            item['edit_url'] = reverse('course_update', args=[course.pk])
            item['delete_url'] = reverse('course_delete', args=[course.pk])
        details[course.pk] = item
    return details


def timetable_context(owner, can_edit):
    """「我的課表」與分享頁共用的資料。"""
    courses = list(owner.courses.prefetch_related('times__start_period', 'times__end_period'))
    subtotals = {
        row['category']: row['credits']
        for row in owner.courses.values('category').annotate(credits=Sum('credits'))
    }
    categories = [
        {
            'label': category.label,
            'color': Course.CATEGORY_COLORS[category],
            'credits': subtotals.get(category, 0),
        }
        for category in Course.Category
    ]
    return {
        'owner': owner,
        'courses': courses,
        'grid': build_grid(courses),
        'details': course_details(courses, can_edit=can_edit),
        'categories': categories,
        'total_credits': sum(subtotals.values()),
    }


@login_required
def timetable(request):
    return render(request, 'schedule/timetable.html', timetable_context(request.user, can_edit=True))


@login_required
def share_settings(request):
    link, _ = ShareLink.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'enable':
            link.is_active = True
            link.save(update_fields=['is_active'])
            messages.success(request, '已開啟分享，把連結傳給想分享的人吧。')
        elif action == 'disable':
            link.is_active = False
            link.save(update_fields=['is_active'])
            messages.success(request, '已停止分享，原本的連結已無法開啟。')
        elif action == 'regenerate':
            link.regenerate()
            messages.success(request, '已產生新連結，舊連結已失效。')
        return redirect('share_settings')
    share_url = request.build_absolute_uri(reverse('shared_timetable', args=[link.token]))
    return render(request, 'schedule/share_settings.html', {'link': link, 'share_url': share_url})


def shared_timetable(request, token):
    # 停止分享或換過連結時一律 404，不透露這個連結是否存在過
    link = get_object_or_404(ShareLink.objects.select_related('user'), token=token, is_active=True)
    return render(request, 'schedule/shared_timetable.html', timetable_context(link.user, can_edit=False))


def _edit_course(request, course):
    """新增與修改共用：課程本體與上課時段要一起驗證、一起儲存。"""
    is_new = course.pk is None
    conflicts = []
    if request.method == 'POST':
        form = CourseForm(request.POST, instance=course)
        formset = CourseTimeFormSet(request.POST, instance=course)
        if form.is_valid() and formset.is_valid():
            new_times = [
                (data['weekday'], data['start_period'].number, data['end_period'].number)
                for data in formset.cleaned_data
                if data and not data.get('DELETE')
            ]
            conflicts = find_conflicts(course.owner, new_times, exclude_course=course)
            # 衝堂不擋下，但要使用者勾選確認後才儲存（例如旁聽、隔週上課）
            if not conflicts or request.POST.get('allow_conflict'):
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
        'conflicts': conflicts,
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
