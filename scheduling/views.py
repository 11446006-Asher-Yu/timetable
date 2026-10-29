from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Count, ProtectedError, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext, ngettext
from django.views.decorators.http import require_POST

from schedule.conflicts import find_conflicts
from schedule.models import Course, CourseTime, Period

from . import emails
from .forms import (
    ChangeRequestForm, ClassGroupForm, ClassroomForm, DeclineForm, InvitationForm, OfferingForm, TermForm,
)
from .models import (
    TEACHERS, AvailabilitySlot, ChangeRequest, ChangeRequestSlot, ClassGroup, Classroom, Offering, OfferingTime,
    TeacherAvailability, TeacherInvitation, Term, default_expiry,
)
from .roles import display_name, scheduler_required, teacher_required
from .rules import availability_map, busy_cells, cells_to_runs, check_schedule, free_classrooms, runs_of

# 排課只用週一到週五
WEEKDAYS = [day for day in CourseTime.Weekday if day <= 5]


# ===== 共用小工具 =====

def week_grid():
    """「星期 × 節次」格子的骨架；各頁面再把自己的資料放進 cell。"""
    periods = list(Period.objects.all())
    labels = {day: str(CourseTime.WEEKDAY_SHORT[day]) for day in WEEKDAYS}
    return {
        'days': [{'value': day, 'label': labels[day]} for day in WEEKDAYS],
        'rows': [
            {'period': period, 'cells': [
                {'weekday': day, 'period': period.number, 'key': f'{day}-{period.number}', 'day_label': labels[day]}
                for day in WEEKDAYS
            ]}
            for period in periods
        ],
    }


def parse_cells(values):
    cells = set()
    for value in values:
        try:
            weekday, period = (int(part) for part in value.split('-'))
        except ValueError:
            continue
        if weekday in WEEKDAYS:
            cells.add((weekday, period))
    return cells


def save_times(offering, runs):
    periods = {period.number: period for period in Period.objects.all()}
    offering.times.all().delete()
    OfferingTime.objects.bulk_create([
        OfferingTime(offering=offering, weekday=weekday, start_period=periods[start], end_period=periods[end])
        for weekday, start, end in runs
    ])


def current_term(request, default_published=False):
    """目前操作的學期：網址 ?term= 優先，其次是記在 session 的選擇，再來是最新的學期。"""
    terms = Term.objects.all()
    if default_published:
        terms = terms.filter(published_at__isnull=False)
    term_id = request.GET.get('term') or request.session.get('term_id')
    term = terms.filter(pk=term_id).first() if term_id and str(term_id).isdigit() else None
    term = term or terms.first()
    if term and request.GET.get('term'):
        request.session['term_id'] = term.pk
    return term


def absolute(request, name, *args):
    return request.build_absolute_uri(reverse(name, args=args))


def offerings_for(term):
    return (
        Offering.objects.filter(term=term)
        .select_related('teacher', 'class_group', 'classroom')
        .prefetch_related('times__start_period', 'times__end_period')
    )


# ===== 排課人員：總覽 =====

@scheduler_required
def dashboard(request):
    term = current_term(request)
    context = {'term': term, 'terms': Term.objects.all()}
    if term:
        counts = dict(Offering.objects.filter(term=term).values_list('status').annotate(n=Count('id')))
        teachers = get_user_model().objects.filter(groups__name=TEACHERS)
        submitted = TeacherAvailability.objects.filter(
            term=term, submitted_at__isnull=False, teacher__in=teachers
        ).count()
        context.update({
            'status_counts': [(value, label, counts.get(value, 0)) for value, label in Offering.Status.choices],
            'teacher_total': teachers.count(),
            'teacher_submitted': submitted,
            'open_requests': ChangeRequest.objects.filter(offering__term=term, status=ChangeRequest.Status.OPEN).count(),
            'unscheduled': Offering.objects.filter(term=term, times__isnull=True).order_by('name'),
        })
    return render(request, 'scheduling/dashboard.html', context)


# ===== 排課人員：學期、教室、班級 =====

SIMPLE_MODELS = {
    'classrooms': (Classroom, ClassroomForm, lambda o: f'{o.get_kind_display()} · {o.capacity}'),
    'groups': (ClassGroup, ClassGroupForm, lambda o: ''),
    'terms': (Term, TermForm, None),
}


def _simple_titles():
    return {'classrooms': gettext('Classrooms'), 'groups': gettext('Class groups'), 'terms': gettext('Terms')}


@scheduler_required
def manage_list(request, kind, pk=None):
    model, form_class, describe = SIMPLE_MODELS[kind]
    instance = get_object_or_404(model, pk=pk) if pk else None
    form = form_class(request.POST or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        item = form.save()
        messages.success(request, gettext('Saved “%(name)s”.') % {'name': item})
        return redirect('scheduling:manage', kind=kind)
    items = []
    for item in model.objects.all():
        if kind == 'terms':
            deadline = item.availability_deadline.isoformat() if item.availability_deadline else '—'
            detail = gettext('Availability: %(state)s · deadline %(deadline)s · %(published)s') % {
                'state': gettext('open') if item.availability_open else gettext('closed'),
                'deadline': deadline,
                'published': gettext('published') if item.published_at else gettext('not published'),
            }
        else:
            detail = describe(item)
        items.append({'object': item, 'detail': detail})
    return render(request, 'scheduling/manage_list.html', {
        'kind': kind, 'title': _simple_titles()[kind], 'items': items, 'form': form, 'editing': instance,
    })


@scheduler_required
@require_POST
def manage_delete(request, kind, pk):
    model = SIMPLE_MODELS[kind][0]
    item = get_object_or_404(model, pk=pk)
    try:
        item.delete()
        messages.success(request, gettext('Deleted “%(name)s”.') % {'name': item})
    except ProtectedError:
        messages.error(request, gettext('“%(name)s” is used by an offering and can’t be deleted.') % {'name': item})
    return redirect('scheduling:manage', kind=kind)


@scheduler_required
@require_POST
def term_availability(request, pk):
    term = get_object_or_404(Term, pk=pk)
    term.availability_open = request.POST.get('open') == '1'
    term.save(update_fields=['availability_open'])
    if term.availability_open:
        emails.availability_open(term, absolute(request, 'scheduling:availability'))
        messages.success(request, gettext('Availability form for %(term)s is open. Teachers have been notified.')
                         % {'term': term.name})
    else:
        messages.success(request, gettext('Availability form for %(term)s is closed.') % {'term': term.name})
    return redirect('scheduling:manage', kind='terms')


# ===== 排課人員：開課 =====

@scheduler_required
def offering_list(request):
    term = current_term(request)
    offerings = offerings_for(term) if term else Offering.objects.none()
    return render(request, 'scheduling/offering_list.html', {
        'term': term, 'terms': Term.objects.all(), 'offerings': offerings,
        'sendable': [o for o in offerings if o.status == Offering.Status.DRAFT and o.classroom_id and o.times.all()],
    })


@scheduler_required
def offering_edit(request, pk=None):
    offering = get_object_or_404(Offering, pk=pk) if pk else None
    initial = {'term': current_term(request)} if offering is None else None
    form = OfferingForm(request.POST or None, instance=offering, initial=initial)
    if request.method == 'POST' and form.is_valid():
        offering = form.save()
        messages.success(request, gettext('Saved “%(name)s”.') % {'name': offering.name})
        if pk is None:
            return redirect('scheduling:board', pk=offering.pk)
        return redirect('scheduling:offerings')
    return render(request, 'scheduling/offering_form.html', {'form': form, 'offering': offering})


@scheduler_required
@require_POST
def offering_delete(request, pk):
    offering = get_object_or_404(Offering, pk=pk)
    offering.delete()
    messages.success(request, gettext('Deleted “%(name)s”.') % {'name': offering.name})
    return redirect('scheduling:offerings')


def _send_for_confirmation(request, offerings):
    for offering in offerings:
        offering.status = Offering.Status.PENDING
        offering.save(update_fields=['status', 'updated_at'])
    emails.sent_for_confirmation(offerings, absolute(request, 'scheduling:teaching'))


@scheduler_required
@require_POST
def offering_send_all(request):
    term = current_term(request)
    candidates = [o for o in offerings_for(term) if o.status == Offering.Status.DRAFT and o.classroom_id]
    ready = [o for o in candidates if check_schedule(o, runs_of(o), o.classroom).ok and o.times.all()]
    _send_for_confirmation(request, ready)
    messages.success(request, ngettext('Sent %(count)s offering to teachers.', 'Sent %(count)s offerings to teachers.', len(ready))
                     % {'count': len(ready)})
    if len(ready) < len(candidates):
        messages.error(request, ngettext('%(count)s draft still has problems and was not sent.',
                                '%(count)s drafts still have problems and were not sent.',
                                len(candidates) - len(ready))
                       % {'count': len(candidates) - len(ready)})
    return redirect('scheduling:offerings')


# ===== 排課人員：排課看板 =====

def _board_state(offering, cells, classroom):
    runs = cells_to_runs(cells)
    result = check_schedule(offering, runs, classroom) if runs else None
    candidates = Classroom.objects.filter(kind=offering.room_kind, capacity__gte=offering.capacity)
    rooms = free_classrooms(offering, runs, candidates)
    if classroom and classroom not in rooms:
        rooms.append(classroom)  # 目前選的教室即使衝突也要留在選單裡，錯誤訊息會說明
    return runs, result, rooms


def _board_payload(result, rooms, classroom):
    errors = [message for _code, message in result.errors] if result else []
    if result and classroom is None:
        errors.append(gettext('Select a classroom.'))  # 規則都通過但還沒選教室，也還不能送出
    return {
        'ok': bool(result and result.ok and classroom),
        'errors': errors,
        'warnings': result.warnings if result else [],
        'rooms': [{'id': room.pk, 'name': str(room), 'selected': classroom == room} for room in rooms],
    }


@scheduler_required
def board(request, pk):
    offering = get_object_or_404(Offering.objects.select_related('term', 'teacher', 'class_group'), pk=pk)
    if offering.status == Offering.Status.PUBLISHED:
        messages.error(request, gettext('Unpublish “%(name)s” before rescheduling it.') % {'name': offering.name})
        return redirect('scheduling:publish')

    if request.method == 'POST':
        cells = parse_cells(request.POST.getlist('cell'))
        classroom = Classroom.objects.filter(pk=request.POST.get('classroom') or 0).first()
    else:
        cells = {(w, p) for w, s, e in runs_of(offering) for p in range(s, e + 1)}
        classroom = offering.classroom
        change = offering.change_requests.filter(pk=request.GET.get('from_request') or 0).first()
        if change and change.preferred_cells():
            cells = set(change.preferred_cells())  # 同意調整時，先帶入老師希望的時段

    runs, result, rooms = _board_state(offering, cells, classroom)
    action = request.POST.get('action')

    if action == 'check':
        return JsonResponse(_board_payload(result, rooms, classroom))

    if action in ('save', 'send'):
        # 草稿可以先存（節數不足也行），但不能存下衝堂；送出則要全部通過且選好教室
        blocking = result.blocking(ignore={'periods'}) if result else []
        if action == 'send':
            blocking = [message for _code, message in result.errors] if result else [gettext('Select time slots.')]
            if classroom is None:
                blocking.append(gettext('Select a classroom.'))
        if blocking:
            for message in blocking:
                messages.error(request, message)
        else:
            with transaction.atomic():
                save_times(offering, runs)
                offering.classroom = classroom
                offering.status = Offering.Status.DRAFT
                offering.save()
            if action == 'send':
                _send_for_confirmation(request, [offering])
                messages.success(request, gettext('Sent “%(name)s” to %(teacher)s for confirmation.')
                                 % {'name': offering.name, 'teacher': display_name(offering.teacher)})
            else:
                messages.success(request, gettext('Saved “%(name)s” as a draft.') % {'name': offering.name})
            return redirect('scheduling:offerings')

    availability = availability_map(offering.teacher, offering.term)
    busy = busy_cells(offering)
    grid = week_grid()
    for row in grid['rows']:
        for cell in row['cells']:
            position = (cell['weekday'], cell['period'])
            cell['status'] = availability.get(position, AvailabilitySlot.Status.AVAILABLE)
            cell['busy'] = busy.get(position, [])
            cell['selected'] = position in cells
    return render(request, 'scheduling/board.html', {
        'offering': offering, 'grid': grid, 'rooms': rooms, 'classroom': classroom,
        'payload': _board_payload(result, rooms, classroom),
        'open_request': offering.change_requests.filter(status=ChangeRequest.Status.OPEN).first(),
    })


# ===== 排課人員：調整申請 =====

@scheduler_required
def requests_list(request):
    open_requests = (
        ChangeRequest.objects.filter(status=ChangeRequest.Status.OPEN)
        .select_related('offering__teacher', 'offering__class_group', 'offering__classroom')
        .prefetch_related('slots', 'offering__times__start_period', 'offering__times__end_period')
    )
    items = []
    for change in open_requests:
        preferred = ', '.join(str(t) for t in _describe_cells(change.preferred_cells()))
        items.append({'change': change, 'preferred': preferred, 'form': DeclineForm(prefix=f'r{change.pk}')})
    resolved = ChangeRequest.objects.exclude(status=ChangeRequest.Status.OPEN).select_related('offering')[:10]
    return render(request, 'scheduling/requests.html', {'items': items, 'resolved': resolved})


def _describe_cells(cells):
    from schedule.models import describe_time
    return [describe_time(w, s, e) for w, s, e in cells_to_runs(cells)]


@scheduler_required
@require_POST
def request_resolve(request, pk):
    change = get_object_or_404(ChangeRequest.objects.select_related('offering'), pk=pk, status=ChangeRequest.Status.OPEN)
    offering = change.offering
    if request.POST.get('decision') == 'approve':
        change.status = ChangeRequest.Status.APPROVED
        change.response = gettext('Approved. A new schedule will be sent to you.')
        offering.status = Offering.Status.DRAFT
        target = reverse('scheduling:board', args=[offering.pk]) + f'?from_request={change.pk}'
    else:
        form = DeclineForm(request.POST, prefix=f'r{change.pk}')
        if not form.is_valid():
            messages.error(request, gettext('Write a reply explaining why the request is declined.'))
            return redirect('scheduling:requests')
        change.status = ChangeRequest.Status.DECLINED
        change.response = form.cleaned_data['response']
        offering.status = Offering.Status.PENDING  # 維持原排課，請老師重新確認
        target = reverse('scheduling:requests')
    change.resolved_at = timezone.now()
    change.save()
    offering.save(update_fields=['status', 'updated_at'])
    emails.request_resolved(change, absolute(request, 'scheduling:teaching'))
    messages.success(request, gettext('Request for “%(name)s” %(result)s.') % {
        'name': offering.name, 'result': change.get_status_display().lower(),
    })
    return redirect(target)


# ===== 排課人員：老師與邀請 =====

@scheduler_required
def teachers(request):
    form = InvitationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        invite = TeacherInvitation.objects.create(invited_by=request.user, **form.cleaned_data)
        emails.invitation(invite, absolute(request, 'scheduling:accept_invite', invite.token))
        messages.success(request, gettext('Invitation sent to %(email)s.') % {'email': invite.email})
        return redirect('scheduling:teachers')
    teacher_list = get_user_model().objects.filter(groups__name=TEACHERS).order_by('first_name', 'username')
    return render(request, 'scheduling/teachers.html', {
        'form': form,
        'teachers': [{'user': t, 'name': display_name(t)} for t in teacher_list],
        'invitations': TeacherInvitation.objects.filter(accepted_at__isnull=True),
    })


@scheduler_required
@require_POST
def invitation_resend(request, pk):
    invite = get_object_or_404(TeacherInvitation, pk=pk, accepted_at__isnull=True)
    invite.expires_at = default_expiry()
    invite.save(update_fields=['expires_at'])
    emails.invitation(invite, absolute(request, 'scheduling:accept_invite', invite.token))
    messages.success(request, gettext('Invitation sent to %(email)s.') % {'email': invite.email})
    return redirect('scheduling:teachers')


# ===== 排課人員：公布 =====

@scheduler_required
def publish(request):
    term = current_term(request)
    offerings = offerings_for(term) if term else Offering.objects.none()
    if request.method == 'POST' and term:
        if request.POST.get('action') == 'unpublish':
            offering = get_object_or_404(Offering, pk=request.POST.get('offering'), term=term,
                                         status=Offering.Status.PUBLISHED)
            offering.status = Offering.Status.DRAFT
            offering.save(update_fields=['status', 'updated_at'])
            # 已加入的學生課程解除連結，學生可以自行修改或刪除
            offering.student_courses.update(offering=None)
            messages.success(request, gettext('Unpublished “%(name)s”.') % {'name': offering.name})
        else:
            accepted = offerings.filter(status=Offering.Status.ACCEPTED)
            count = accepted.update(status=Offering.Status.PUBLISHED)
            term.published_at = term.published_at or timezone.now()
            term.save(update_fields=['published_at'])
            emails.published(term, absolute(request, 'scheduling:teaching'))
            messages.success(request, ngettext('Published %(count)s offering.', 'Published %(count)s offerings.', count) % {'count': count})
        return redirect('scheduling:publish')
    groups = {value: [] for value, _label in Offering.Status.choices}
    for offering in offerings:
        groups[offering.status].append(offering)
    return render(request, 'scheduling/publish.html', {
        'term': term, 'terms': Term.objects.all(),
        'groups': [(value, label, groups[value]) for value, label in Offering.Status.choices],
        'accepted_count': len(groups[Offering.Status.ACCEPTED]),
        'not_ready': len(groups[Offering.Status.DRAFT]) + len(groups[Offering.Status.PENDING])
        + len(groups[Offering.Status.CHANGE_REQUESTED]),
    })


# ===== 老師 =====

def accept_invite(request, token):
    invite = get_object_or_404(TeacherInvitation, token=token)
    if request.method == 'POST' and request.user.is_authenticated and invite.is_usable:
        request.user.groups.add(Group.objects.get(name=TEACHERS))
        if not request.user.get_full_name():
            request.user.first_name = invite.name
            request.user.save(update_fields=['first_name'])
        if not request.user.email:
            request.user.email = invite.email
            request.user.save(update_fields=['email'])
        invite.accepted_by = request.user
        invite.accepted_at = timezone.now()
        invite.save(update_fields=['accepted_by', 'accepted_at'])
        messages.success(request, gettext('Welcome! You can now use the teacher pages.'))
        return redirect('scheduling:teacher_home')
    return render(request, 'scheduling/accept_invite.html', {'invite': invite})


def _teacher_term(request):
    return current_term(request)


@teacher_required
def teacher_home(request):
    term = _teacher_term(request)
    mine = Offering.objects.filter(teacher=request.user, term=term).exclude(status=Offering.Status.DRAFT)
    availability = TeacherAvailability.objects.filter(teacher=request.user, term=term).first()
    return render(request, 'scheduling/teacher_home.html', {
        'term': term,
        'pending': mine.filter(status=Offering.Status.PENDING).count(),
        'total': mine.count(),
        'availability': availability,
        'recent': ChangeRequest.objects.filter(offering__teacher=request.user).select_related('offering')[:5],
    })


@teacher_required
def availability(request):
    term = Term.objects.filter(availability_open=True).first() or _teacher_term(request)
    if term is None:
        return render(request, 'scheduling/availability.html', {'term': None})
    record, _created = TeacherAvailability.objects.get_or_create(teacher=request.user, term=term)
    editable = term.availability_editable
    statuses = record.status_map()
    if request.method == 'POST' and editable:
        statuses = {}
        valid = set(AvailabilitySlot.Status.values)
        for key, value in request.POST.items():
            if key.startswith('a-') and value in valid and value != AvailabilitySlot.Status.AVAILABLE:
                cells = parse_cells([key[2:]])
                if cells:
                    statuses[cells.pop()] = value
        with transaction.atomic():
            record.note = request.POST.get('note', '')
            if request.POST.get('action') == 'submit':
                record.submitted_at = timezone.now()
            record.save()
            record.slots.all().delete()
            AvailabilitySlot.objects.bulk_create([
                AvailabilitySlot(availability=record, weekday=w, period=p, status=s) for (w, p), s in statuses.items()
            ])
        messages.success(request, gettext('Submitted. Thank you!') if record.submitted_at
                         and request.POST.get('action') == 'submit' else gettext('Saved.'))
        return redirect('scheduling:availability')
    grid = week_grid()
    for row in grid['rows']:
        for cell in row['cells']:
            cell['status'] = statuses.get((cell['weekday'], cell['period']), AvailabilitySlot.Status.AVAILABLE)
    return render(request, 'scheduling/availability.html', {
        'term': term, 'record': record, 'editable': editable, 'grid': grid,
        'choices': AvailabilitySlot.Status.choices,
    })


@teacher_required
def teaching(request):
    term = _teacher_term(request)
    mine = (
        offerings_for(term).filter(teacher=request.user).exclude(status=Offering.Status.DRAFT)
        if term else Offering.objects.none()
    )
    if request.method == 'POST':
        targets = mine.filter(status=Offering.Status.PENDING)
        if request.POST.get('offering') != 'all':
            targets = targets.filter(pk=request.POST.get('offering') or 0)
        count = targets.update(status=Offering.Status.ACCEPTED)
        messages.success(request, ngettext('Accepted %(count)s class.', 'Accepted %(count)s classes.', count) % {'count': count})
        return redirect('scheduling:teaching')
    grid = week_grid()
    placed = {}
    for offering in mine:
        for weekday, start, end in runs_of(offering):
            for period in range(start, end + 1):
                placed.setdefault((weekday, period), []).append(offering)
    for row in grid['rows']:
        for cell in row['cells']:
            cell['offerings'] = placed.get((cell['weekday'], cell['period']), [])
    return render(request, 'scheduling/teaching.html', {
        'term': term, 'offerings': mine, 'grid': grid,
        'pending_count': sum(1 for o in mine if o.status == Offering.Status.PENDING),
    })


@teacher_required
def request_change(request, pk):
    offering = get_object_or_404(
        Offering, pk=pk, teacher=request.user,
        status__in=[Offering.Status.PENDING, Offering.Status.ACCEPTED],
    )
    form = ChangeRequestForm(request.POST or None)
    cells = parse_cells(request.POST.getlist('cell'))
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            change = form.save(commit=False)
            change.offering = offering
            change.save()
            ChangeRequestSlot.objects.bulk_create([
                ChangeRequestSlot(request=change, weekday=w, period=p) for w, p in sorted(cells)
            ])
            offering.status = Offering.Status.CHANGE_REQUESTED
            offering.save(update_fields=['status', 'updated_at'])
        emails.change_requested(change, absolute(request, 'scheduling:requests'))
        messages.success(request, gettext('Your request has been sent to the scheduler.'))
        return redirect('scheduling:teaching')
    grid = week_grid()
    for row in grid['rows']:
        for cell in row['cells']:
            cell['selected'] = (cell['weekday'], cell['period']) in cells
    return render(request, 'scheduling/request_change.html', {'offering': offering, 'form': form, 'grid': grid})


# ===== 學生：課程目錄 =====

@login_required
def catalog(request):
    term = current_term(request, default_published=True)
    offerings = (
        offerings_for(term).filter(status=Offering.Status.PUBLISHED) if term else Offering.objects.none()
    )
    query = request.GET.get('q', '').strip()
    if query:
        offerings = offerings.filter(
            Q(name__icontains=query) | Q(teacher__first_name__icontains=query)
            | Q(teacher__last_name__icontains=query) | Q(teacher__username__icontains=query)
        )
    group_id = request.GET.get('group', '')
    if group_id.isdigit():
        offerings = offerings.filter(class_group_id=group_id)
    category = request.GET.get('category', '')
    if category in Course.Category.values:
        offerings = offerings.filter(category=category)

    conflicts, conflict_offering = [], None
    if request.method == 'POST':
        offering = get_object_or_404(Offering, pk=request.POST.get('offering'), status=Offering.Status.PUBLISHED)
        if request.user.courses.filter(offering=offering).exists():
            return redirect(request.get_full_path())
        conflicts = find_conflicts(request.user, runs_of(offering))
        if conflicts and not request.POST.get('allow_conflict'):
            conflict_offering = offering
        else:
            add_to_timetable(request.user, offering)
            messages.success(request, gettext('Added “%(name)s”.') % {'name': offering.name})
            return redirect(request.get_full_path())

    offerings = list(offerings)
    for offering in offerings:
        offering.teacher_name = display_name(offering.teacher)
        offering.color = Course.CATEGORY_COLORS[offering.category]
    added = set(request.user.courses.filter(offering__isnull=False).values_list('offering_id', flat=True))
    return render(request, 'scheduling/catalog.html', {
        'term': term,
        'terms': Term.objects.filter(published_at__isnull=False),
        'offerings': offerings,
        'added': added,
        'groups': ClassGroup.objects.filter(offerings__term=term).distinct() if term else [],
        'categories': Course.Category.choices,
        'query': query, 'group_id': group_id, 'category': category,
        'conflicts': conflicts, 'conflict_offering': conflict_offering,
    })


def add_to_timetable(user, offering):
    with transaction.atomic():
        course = Course.objects.create(
            owner=user, offering=offering, name=offering.name, teacher=display_name(offering.teacher),
            classroom=offering.classroom.name if offering.classroom else '', credits=offering.credits,
            category=offering.category,
        )
        CourseTime.objects.bulk_create([
            CourseTime(course=course, weekday=t.weekday, start_period=t.start_period, end_period=t.end_period)
            for t in offering.times.all()
        ])
    return course
