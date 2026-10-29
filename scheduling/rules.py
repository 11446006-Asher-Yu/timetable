"""排課規則 R1–R7（規劃書第七章）。伺服器端為準，排課看板的即時提示也呼叫這裡。"""

from dataclasses import dataclass, field

from django.utils.translation import gettext

from schedule.conflicts import overlaps
from schedule.models import describe_time

from .models import AvailabilitySlot, Offering, OfferingTime, TeacherAvailability


@dataclass
class CheckResult:
    errors: list = field(default_factory=list)    # (規則代碼, 說明)；有任何一項就不能送出
    warnings: list = field(default_factory=list)  # 只提醒

    @property
    def ok(self):
        return not self.errors

    def blocking(self, ignore=()):
        return [message for code, message in self.errors if code not in ignore]


def cells_to_runs(cells):
    """把選取的格子 {(星期, 節次)} 合併成連續時段 [(星期, 起, 迄)]。"""
    runs = []
    for weekday, period in sorted(cells):
        if runs and runs[-1][0] == weekday and runs[-1][2] == period - 1:
            runs[-1] = (weekday, runs[-1][1], period)
        else:
            runs.append((weekday, period, period))
    return runs


def runs_of(offering):
    return [(t.weekday, t.start_period.number, t.end_period.number) for t in offering.times.all()]


def check_schedule(offering, runs, classroom):
    """檢查把 offering 排在 runs、classroom 是否違反規則。"""
    result = CheckResult()
    others = (
        Offering.objects.filter(term=offering.term)
        .exclude(pk=offering.pk)
        .select_related('teacher', 'classroom', 'class_group')
        .prefetch_related('times__start_period', 'times__end_period')
    )

    # R6 節數
    total = sum(end - start + 1 for _, start, end in runs)
    if total != offering.periods_per_week:
        result.errors.append(('periods', gettext('Selected %(selected)s periods, but this course needs %(needed)s.')
                              % {'selected': total, 'needed': offering.periods_per_week}))

    # R7 教室類型與容量
    if classroom is not None:
        if classroom.kind != offering.room_kind:
            result.errors.append(('room_kind', gettext('%(room)s is a %(kind)s, but this course needs a %(needed)s.') % {
                'room': classroom.name, 'kind': classroom.get_kind_display().lower(),
                'needed': offering.get_room_kind_display().lower(),
            }))
        if classroom.capacity < offering.capacity:
            result.errors.append(('capacity', gettext('%(room)s holds %(capacity)s, fewer than the %(needed)s students allowed.') % {
                'room': classroom.name, 'capacity': classroom.capacity, 'needed': offering.capacity,
            }))

    # R1–R3 老師、教室、班級衝堂
    for other in others:
        for weekday, start, end in runs:
            for other_day, other_start, other_end in runs_of(other):
                if not overlaps(weekday, start, end, other_day, other_start, other_end):
                    continue
                when = describe_time(weekday, start, end)
                names = {'time': when, 'course': other.name}
                if other.teacher_id == offering.teacher_id:
                    result.errors.append(('teacher', gettext('%(time)s: the teacher already teaches “%(course)s”.') % names))
                if classroom is not None and other.classroom_id == classroom.pk:
                    result.errors.append(('room', gettext('%(time)s: %(room)s is used by “%(course)s”.')
                                          % {**names, 'room': classroom.name}))
                if other.class_group_id == offering.class_group_id:
                    result.errors.append(('group', gettext('%(time)s: %(group)s already has “%(course)s”.')
                                          % {**names, 'group': offering.class_group.name}))

    # R4、R5 老師可授課時段
    statuses = availability_map(offering.teacher, offering.term)
    for weekday, start, end in runs:
        for period in range(start, end + 1):
            status = statuses.get((weekday, period))
            when = describe_time(weekday, period, period)
            if status == AvailabilitySlot.Status.UNAVAILABLE:
                result.errors.append(('unavailable', gettext('%(time)s: the teacher is unavailable.') % {'time': when}))
            elif status == AvailabilitySlot.Status.AVOID:
                result.warnings.append(gettext('%(time)s: the teacher prefers not to teach.') % {'time': when})
    return result


def availability_map(teacher, term):
    availability = TeacherAvailability.objects.filter(teacher=teacher, term=term).first()
    return availability.status_map() if availability else {}


def busy_cells(offering):
    """排課看板用：同學期其他開課占用的格子 → 衝突原因（老師、班級）。教室要等選了教室才知道，另外處理。"""
    busy = {}
    others = (
        Offering.objects.filter(term=offering.term)
        .exclude(pk=offering.pk)
        .prefetch_related('times__start_period', 'times__end_period')
    )
    for other in others:
        reasons = []
        if other.teacher_id == offering.teacher_id:
            reasons.append(gettext('teacher'))
        if other.class_group_id == offering.class_group_id:
            reasons.append(gettext('class group'))
        if not reasons:
            continue
        for weekday, start, end in runs_of(other):
            for period in range(start, end + 1):
                busy.setdefault((weekday, period), []).append(f'{other.name} ({", ".join(reasons)})')
    return busy


def free_classrooms(offering, runs, classrooms):
    """在 runs 時段沒被同學期其他開課占用的教室。"""
    taken = set()
    for time in OfferingTime.objects.filter(offering__term=offering.term, offering__classroom__isnull=False).exclude(
        offering=offering
    ).select_related('offering', 'start_period', 'end_period'):
        for weekday, start, end in runs:
            if overlaps(weekday, start, end, time.weekday, time.start_period.number, time.end_period.number):
                taken.add(time.offering.classroom_id)
    return [room for room in classrooms if room.pk not in taken]
