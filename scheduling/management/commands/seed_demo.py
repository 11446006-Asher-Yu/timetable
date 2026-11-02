"""建立 Demo 用的示範資料：python manage.py seed_demo

會建立三個能登入的示範帳號（學生、排課人員、老師）、學生的個人課表，以及一個學期的排課資料。
可以重複執行，每次都會把示範資料恢復成初始狀態，不影響其他帳號。

示範帳號的密碼是公開的，所以只能在本機開發模式（DEBUG=True）使用，正式網站要加 --force 才會執行。
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from schedule.models import Course, CourseTime, Period, ShareLink
from scheduling.models import (
    SCHEDULERS, TEACHERS, AvailabilitySlot, ChangeRequest, ChangeRequestSlot, ClassGroup, Classroom, Offering,
    TeacherAvailability, TeacherInvitation, Term,
)
from scheduling.rules import cells_to_runs, check_schedule
from scheduling.views import save_times

DEMO_PASSWORD = 'demo-pass-2026'

# 能登入的示範帳號：(帳號, 姓名, 角色)
LOGIN_ACCOUNTS = [
    ('demo_student', '', None),
    ('demo_scheduler', '排課人員（示範）', SCHEDULERS),
    ('demo_teacher', '王老師（示範）', TEACHERS),
]

# 其他示範老師只用來排課，不能登入
OTHER_TEACHERS = [('demo_lee', '李老師（示範）'), ('demo_chang', '張老師（示範）'), ('demo_chen', '陳老師（示範）')]

# 學生的個人課表：(課名, 類別, 學分, 教室, 老師, [(星期, 起, 迄)])
PERSONAL_COURSES = [
    ('經濟學', 'required', 3, '五教 201', '林老師', [(1, 2, 4)]),
    ('會計學', 'required', 3, '五教 305', '周老師', [(3, 6, 8)]),
    ('行銷管理', 'elective', 2, '四教 210', '吳老師', [(2, 6, 7)]),
    ('台灣文化概論', 'general', 2, '中正堂', '許老師', [(5, 3, 4)]),
    ('體育（羽球）', 'pe', 1, '體育館', '鄭老師', [(4, 7, 8)]),
    ('日文（一）', 'other', 2, '七教 105', '蔡老師', [(1, 9, 10)]),
]

ROOMS = [('六教 601', 60, 'general'), ('六教 602', 60, 'general'), ('五教 302', 45, 'general'),
         ('電腦教室 A', 40, 'computer'), ('電腦教室 B', 40, 'computer')]
GROUPS = ['資管一甲', '資管二甲', '資管三甲']

# 開課：(課名, 班級, 老師帳號, 學分, 類別, 節數, 教室類型, 人數, 時段, 教室, 狀態)
OFFERINGS = [
    ('程式設計（一）', '資管一甲', 'demo_teacher', 3, 'required', 3, 'computer', 40, [(2, 2), (2, 3), (2, 4)], '電腦教室 A', 'accepted'),
    ('計算機概論', '資管一甲', 'demo_chang', 3, 'required', 3, 'general', 55, [(4, 2), (4, 3), (4, 4)], '六教 601', 'accepted'),
    ('資料結構', '資管二甲', 'demo_teacher', 3, 'required', 3, 'general', 55, [(3, 2), (3, 3), (3, 4)], '六教 602', 'pending'),
    ('統計學', '資管二甲', 'demo_lee', 3, 'required', 3, 'general', 55, [(2, 6), (2, 7), (2, 8)], '六教 601', 'change_requested'),
    ('資料庫系統', '資管三甲', 'demo_lee', 3, 'required', 3, 'computer', 40, [(4, 6), (4, 7), (4, 8)], '電腦教室 B', 'accepted'),
    ('網頁程式設計', '資管三甲', 'demo_teacher', 3, 'elective', 3, 'computer', 40, [(5, 2), (5, 3), (5, 4)], '電腦教室 A', 'draft'),
    ('台灣文化概論', '資管二甲', 'demo_chen', 2, 'general', 2, 'general', 60, [], None, 'draft'),
    ('英文（一）', '資管一甲', 'demo_chen', 2, 'other', 2, 'general', 45, [], None, 'draft'),
]


class Command(BaseCommand):
    help = 'Create demo accounts, a personal timetable and a scheduling term for presentations.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Run even when DEBUG is False (not recommended).')

    def handle(self, *args, force=False, **options):
        if not settings.DEBUG and not force:
            raise CommandError('seed_demo creates accounts with a public password. Use it only in local '
                               'development (DEBUG=True), or pass --force if you really mean it.')
        if not Period.objects.exists():
            call_command('loaddata', 'periods', verbosity=0)

        with transaction.atomic():
            users = self.create_users()
            self.create_personal_timetable(users['demo_student'])
            self.create_scheduling(users)

        self.stdout.write(self.style.SUCCESS('Demo data is ready. 示範資料已建立。'))
        self.stdout.write('')
        self.stdout.write(f'  Password for all demo accounts / 示範帳號密碼：{DEMO_PASSWORD}')
        for username, _name, role in LOGIN_ACCOUNTS:
            self.stdout.write(f'  {username:<15} {role or "Student"}')
        self.stdout.write('')
        self.stdout.write('  Open http://127.0.0.1:8000/ after running: python manage.py runserver')

    # ===== 帳號 =====

    def create_users(self):
        User = get_user_model()
        groups = {name: Group.objects.get(name=name) for name in (SCHEDULERS, TEACHERS)}
        users = {}
        for username, name, role in LOGIN_ACCOUNTS:
            user, _ = User.objects.get_or_create(username=username)
            user.first_name = name
            user.email = f'{username}@example.com'
            user.set_password(DEMO_PASSWORD)
            user.save()
            user.groups.clear()
            if role:
                user.groups.add(groups[role])
            users[username] = user
        for username, name in OTHER_TEACHERS:
            user, created = User.objects.get_or_create(
                username=username, defaults={'first_name': name, 'email': f'{username}@example.com'}
            )
            if created:
                user.set_unusable_password()
                user.save()
            user.groups.add(groups[TEACHERS])
            users[username] = user
        return users

    # ===== 學生的個人課表 =====

    def create_personal_timetable(self, student):
        periods = {p.number: p for p in Period.objects.all()}
        student.courses.all().delete()
        for name, category, credits, room, teacher, times in PERSONAL_COURSES:
            course = Course.objects.create(
                owner=student, name=name, category=category, credits=credits, classroom=room, teacher=teacher,
            )
            CourseTime.objects.bulk_create([
                CourseTime(course=course, weekday=w, start_period=periods[s], end_period=periods[e])
                for w, s, e in times
            ])
        ShareLink.objects.update_or_create(user=student, defaults={'is_active': True})

    # ===== 排課 =====

    def create_scheduling(self, users):
        term, _ = Term.objects.update_or_create(name='115-1', defaults={
            'availability_open': True,
            'availability_deadline': timezone.localdate() + timedelta(days=7),
            'published_at': None,
        })
        rooms = {}
        for name, capacity, kind in ROOMS:
            rooms[name], _ = Classroom.objects.update_or_create(name=name, defaults={'capacity': capacity, 'kind': kind})
        groups = {name: ClassGroup.objects.get_or_create(name=name)[0] for name in GROUPS}

        self.availability(users['demo_teacher'], term, unavailable=[(1, p) for p in range(1, 9)],
                          avoid=[(5, 7), (5, 8)])
        self.availability(users['demo_lee'], term, unavailable=[(3, p) for p in range(1, 5)])
        self.availability(users['demo_chang'], term, avoid=[(w, 1) for w in range(1, 6)])
        self.availability(users['demo_chen'], term, submitted=False)

        TeacherInvitation.objects.filter(email__endswith='@example.com', accepted_at__isnull=True).delete()
        TeacherInvitation.objects.create(name='林老師（示範）', email='demo_lin@example.com',
                                         invited_by=users['demo_scheduler'])

        Offering.objects.filter(term=term).delete()
        for name, group, teacher, credits, category, periods, kind, capacity, cells, room, status in OFFERINGS:
            offering = Offering.objects.create(
                term=term, name=name, class_group=groups[group], teacher=users[teacher], credits=credits,
                category=category, periods_per_week=periods, room_kind=kind, capacity=capacity,
            )
            if cells:
                runs = cells_to_runs(cells)
                result = check_schedule(offering, runs, rooms[room])
                if not result.ok:
                    raise CommandError(f'Demo data for {name} breaks a scheduling rule: {result.errors}')
                save_times(offering, runs)
                offering.classroom = rooms[room]
            offering.status = status
            offering.save()
            if status == Offering.Status.CHANGE_REQUESTED:
                change = ChangeRequest.objects.create(offering=offering, reason='週二晚上有研究計畫會議，希望改到週四上午。')
                ChangeRequestSlot.objects.bulk_create(
                    [ChangeRequestSlot(request=change, weekday=4, period=p) for p in (2, 3, 4)]
                )

    def availability(self, teacher, term, unavailable=(), avoid=(), submitted=True):
        record, _ = TeacherAvailability.objects.get_or_create(teacher=teacher, term=term)
        record.slots.all().delete()
        AvailabilitySlot.objects.bulk_create(
            [AvailabilitySlot(availability=record, weekday=w, period=p, status='unavailable') for w, p in unavailable]
            + [AvailabilitySlot(availability=record, weekday=w, period=p, status='avoid') for w, p in avoid]
        )
        record.submitted_at = timezone.now() if submitted else None
        record.save()
