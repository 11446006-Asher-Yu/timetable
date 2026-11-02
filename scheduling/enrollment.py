"""學生加入正式課程、候補與自動遞補。

「加入」＝從課程目錄把已公布的開課抄進自己的個人課表（schedule.Course.offering 指向該開課），
已加入人數就是指向它的 Course 數量，上限是 Offering.capacity。
"""

from django.db import transaction

from schedule.models import Course, CourseTime

from . import emails
from .models import Offering, WaitlistEntry
from .roles import display_name


class CourseFull(Exception):
    pass


def add_to_timetable(user, offering):
    course = Course.objects.create(
        owner=user, offering=offering, term=offering.term, name=offering.name, teacher=display_name(offering.teacher),
        classroom=offering.classroom.name if offering.classroom else '', credits=offering.credits,
        category=offering.category,
    )
    CourseTime.objects.bulk_create([
        CourseTime(course=course, weekday=t.weekday, start_period=t.start_period, end_period=t.end_period)
        for t in offering.times.all()
    ])
    return course


@transaction.atomic
def enroll(user, offering):
    """有名額才加入；額滿丟出 CourseFull。加入後若原本在候補名單上就移除。"""
    # 鎖住這門課，避免兩個學生同時搶最後一個名額
    offering = Offering.objects.select_for_update().get(pk=offering.pk)
    existing = user.courses.filter(offering=offering).first()
    if existing:  # 重複送出（例如連按兩下）：不要加第二份
        return existing
    if offering.seats_left <= 0:
        raise CourseFull
    course = add_to_timetable(user, offering)
    WaitlistEntry.objects.filter(offering=offering, student=user).delete()
    return course


def join_waitlist(user, offering):
    entry, _created = WaitlistEntry.objects.get_or_create(offering=offering, student=user)
    return entry


def leave_waitlist(user, offering):
    WaitlistEntry.objects.filter(offering=offering, student=user).delete()


def withdraw(offering, link=''):
    """撤回公布：從已加入學生的課表移除這門課並寄信通知、清空候補，課程回到草稿；回傳受影響的學生。

    不保留學生的複本，否則重新公布時已加入人數會從 0 算起而超收，學生課表上也會留著過時的時段。
    """
    with transaction.atomic():
        offering = Offering.objects.select_for_update().get(pk=offering.pk)
        courses = list(offering.student_courses.select_related('owner'))
        students = [course.owner for course in courses]
        offering.student_courses.all().delete()
        offering.waitlist.all().delete()
        offering.status = Offering.Status.DRAFT
        offering.save(update_fields=['status', 'updated_at'])
    for student in students:
        emails.course_withdrawn(student, offering, link)
    return students


def promote(offering, link=''):
    """有空出的名額就依序讓候補遞補，自動加進他們的課表並寄信；回傳遞補的學生。"""
    promoted = []
    with transaction.atomic():
        offering = Offering.objects.select_for_update().get(pk=offering.pk)
        if offering.status != Offering.Status.PUBLISHED:
            return promoted
        for entry in list(offering.waitlist.select_related('student')):
            if offering.seats_left <= 0:
                break
            if not offering.student_courses.filter(owner=entry.student).exists():
                add_to_timetable(entry.student, offering)
                promoted.append(entry.student)
            entry.delete()
    for student in promoted:
        emails.waitlist_promoted(student, offering, link)
    return promoted
