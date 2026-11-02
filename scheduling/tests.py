from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from schedule.models import Course, CourseTime, Period

from .models import (
    SCHEDULERS, TEACHERS, AvailabilitySlot, ChangeRequest, ClassGroup, Classroom, Offering, StudentProfile,
    TeacherAvailability, TeacherInvitation, Term,
)
from .rules import cells_to_runs, check_schedule
from .views import save_times

User = get_user_model()


class SchedulingTestCase(TestCase):
    """共用資料：排課人員、兩位老師、一位學生、一個學期、教室、班級。"""

    fixtures = ['periods']

    def setUp(self):
        self.scheduler = self.make_user('sched', SCHEDULERS)
        self.teacher = self.make_user('wang', TEACHERS, first_name='王老師')
        self.teacher2 = self.make_user('lee', TEACHERS, first_name='李老師')
        self.student = self.make_user('student')
        self.term = Term.objects.create(name='115-1', availability_open=True)
        self.room = Classroom.objects.create(name='六教 601', capacity=60)
        self.room2 = Classroom.objects.create(name='六教 602', capacity=60)
        self.lab = Classroom.objects.create(name='電腦教室 A', capacity=40, kind=Classroom.Kind.COMPUTER)
        self.group = ClassGroup.objects.create(name='資管三甲')
        self.group2 = ClassGroup.objects.create(name='資管二乙')

    def make_user(self, username, group=None, **extra):
        user = User.objects.create_user(username, email=f'{username}@example.com', password='pw-12345678', **extra)
        if group:
            user.groups.add(Group.objects.get(name=group))
        return user

    def offering(self, name='網頁程式設計', teacher=None, group=None, periods=3, **extra):
        extra.setdefault('capacity', 50)
        return Offering.objects.create(
            term=self.term, name=name, teacher=teacher or self.teacher, class_group=group or self.group,
            periods_per_week=periods, **extra,
        )

    def place(self, offering, cells, room=None, status=Offering.Status.DRAFT):
        save_times(offering, cells_to_runs(cells))
        offering.classroom = room
        offering.status = status
        offering.save()
        return offering


class RoleTests(SchedulingTestCase):
    def test_role_groups_exist(self):
        self.assertTrue(Group.objects.filter(name=SCHEDULERS).exists())
        self.assertTrue(Group.objects.filter(name=TEACHERS).exists())

    def test_student_cannot_open_scheduler_or_teacher_pages(self):
        self.client.force_login(self.student)
        for name in ['scheduling:dashboard', 'scheduling:offerings', 'scheduling:teachers',
                     'scheduling:requests', 'scheduling:publish', 'scheduling:teacher_home',
                     'scheduling:availability', 'scheduling:teaching']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_teacher_cannot_open_scheduler_pages(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse('scheduling:dashboard')).status_code, 403)
        self.assertEqual(self.client.get(reverse('scheduling:teacher_home')).status_code, 200)

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(reverse('scheduling:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def nav_links(self, user):
        import re

        self.client.force_login(user)
        html = self.client.get(reverse('timetable')).content.decode()
        nav = re.search(r'<nav class="site-nav">(.*?)</nav>', html, re.S).group(1)
        return set(re.findall(r'<a href="([^"]+)"', nav))

    def test_nav_links_follow_roles(self):
        # 排課人員、老師只看到自己的工作頁；學生看到課程目錄與我的課表
        self.assertEqual(self.nav_links(self.scheduler), {reverse('scheduling:dashboard')})
        self.assertEqual(self.nav_links(self.teacher), {reverse('scheduling:teacher_home')})
        self.assertEqual(self.nav_links(self.student), {reverse('scheduling:catalog'), reverse('timetable')})

    def test_login_lands_on_role_home(self):
        for user, target in [(self.scheduler, 'scheduling:dashboard'),
                             (self.teacher, 'scheduling:teacher_home'),
                             (self.student, 'timetable')]:
            self.client.logout()
            response = self.client.post(reverse('login'), {'username': user.username, 'password': 'pw-12345678'},
                                        follow=True)
            self.assertRedirects(response, reverse(target), msg_prefix=user.username)

    def test_hidden_pages_still_open_by_url(self):
        # 只是隱藏選單，排課人員仍可自行輸入網址使用個人課表與課程目錄
        self.client.force_login(self.scheduler)
        self.assertEqual(self.client.get(reverse('timetable')).status_code, 200)
        self.assertEqual(self.client.get(reverse('scheduling:catalog')).status_code, 200)

    def test_teacher_cannot_touch_other_teachers_offering(self):
        offering = self.place(self.offering(teacher=self.teacher2), {(1, 1), (1, 2), (1, 3)}, self.room,
                              Offering.Status.PENDING)
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse('scheduling:request_change', args=[offering.pk])).status_code, 404)
        self.client.post(reverse('scheduling:teaching'), {'offering': offering.pk})
        offering.refresh_from_db()
        self.assertEqual(offering.status, Offering.Status.PENDING)


class RuleTests(SchedulingTestCase):
    def test_cells_to_runs_merges_consecutive_periods(self):
        self.assertEqual(cells_to_runs({(2, 3), (2, 1), (2, 2), (4, 5)}), [(2, 1, 3), (4, 5, 5)])

    def test_valid_schedule_passes(self):
        result = check_schedule(self.offering(), [(2, 1, 3)], self.room)
        self.assertTrue(result.ok, result.errors)

    def test_r1_teacher_conflict(self):
        self.place(self.offering('資料庫', group=self.group2), {(2, 2)}, self.room2)
        codes = [code for code, _ in check_schedule(self.offering(), [(2, 1, 3)], self.room).errors]
        self.assertIn('teacher', codes)

    def test_r2_classroom_conflict(self):
        self.place(self.offering('統計學', teacher=self.teacher2, group=self.group2), {(2, 3)}, self.room)
        codes = [code for code, _ in check_schedule(self.offering(), [(2, 1, 3)], self.room).errors]
        self.assertEqual(codes, ['room'])

    def test_r3_class_group_conflict(self):
        self.place(self.offering('統計學', teacher=self.teacher2), {(2, 1)}, self.room2)
        codes = [code for code, _ in check_schedule(self.offering(), [(2, 1, 3)], self.room).errors]
        self.assertEqual(codes, ['group'])

    def test_r4_unavailable_blocks_and_r5_avoid_warns(self):
        availability = TeacherAvailability.objects.create(teacher=self.teacher, term=self.term)
        AvailabilitySlot.objects.create(availability=availability, weekday=2, period=1, status='unavailable')
        AvailabilitySlot.objects.create(availability=availability, weekday=2, period=3, status='avoid')
        result = check_schedule(self.offering(), [(2, 1, 3)], self.room)
        self.assertEqual([code for code, _ in result.errors], ['unavailable'])
        self.assertEqual(len(result.warnings), 1)

    def test_r6_period_count_must_match(self):
        codes = [code for code, _ in check_schedule(self.offering(), [(2, 1, 2)], self.room).errors]
        self.assertEqual(codes, ['periods'])

    def test_r7_room_kind_and_capacity(self):
        offering = self.offering(room_kind=Classroom.Kind.COMPUTER)
        codes = {code for code, _ in check_schedule(offering, [(2, 1, 3)], self.room).errors}
        self.assertIn('room_kind', codes)
        offering = self.offering('大班課', capacity=80)
        codes = {code for code, _ in check_schedule(offering, [(2, 1, 3)], self.room).errors}
        self.assertIn('capacity', codes)

    def test_other_terms_do_not_conflict(self):
        other_term = Term.objects.create(name='114-2')
        Offering.objects.create(term=other_term, name='舊課', teacher=self.teacher, class_group=self.group,
                                periods_per_week=3, classroom=self.room)
        self.assertTrue(check_schedule(self.offering(), [(2, 1, 3)], self.room).ok)


class FlowTests(SchedulingTestCase):
    def board_post(self, offering, cells, room, action):
        data = {'cell': [f'{w}-{p}' for w, p in cells], 'classroom': room.pk if room else '', 'action': action}
        return self.client.post(reverse('scheduling:board', args=[offering.pk]), data)

    def test_full_flow_from_invitation_to_catalog(self):
        # 排課人員邀請新老師
        self.client.force_login(self.scheduler)
        self.client.post(reverse('scheduling:teachers'), {'name': '陳老師', 'email': 'chen@example.com'})
        invite = TeacherInvitation.objects.get(email='chen@example.com')
        self.assertIn(str(invite.token), mail.outbox[-1].body)

        # 老師註冊後回到邀請頁接受
        self.client.logout()
        accept_url = reverse('scheduling:accept_invite', args=[invite.token])
        response = self.client.post(reverse('signup') + f'?next={accept_url}', {
            'username': 'chen', 'email': 'chen@example.com',
            'password1': 'Sch3dule-pass!', 'password2': 'Sch3dule-pass!', 'next': accept_url,
        })
        self.assertRedirects(response, accept_url)
        self.client.post(accept_url)
        chen = User.objects.get(username='chen')
        self.assertTrue(chen.groups.filter(name=TEACHERS).exists())
        self.assertEqual(chen.first_name, '陳老師')

        # 老師填可授課時段：週一第 1–8 節不行
        data = {f'a-1-{p}': 'unavailable' for p in range(1, 9)}
        data.update({'action': 'submit', 'note': '週一校外授課'})
        self.client.post(reverse('scheduling:availability'), data)
        self.assertIsNotNone(TeacherAvailability.objects.get(teacher=chen).submitted_at)

        # 排課人員排課：排在週一被擋下，排在週三通過並送出
        self.client.force_login(self.scheduler)
        offering = self.offering(teacher=chen)
        self.board_post(offering, {(1, 1), (1, 2), (1, 3)}, self.room, 'send')
        offering.refresh_from_db()
        self.assertEqual(offering.status, Offering.Status.DRAFT)
        self.assertFalse(offering.times.exists())
        self.board_post(offering, {(3, 2), (3, 3), (3, 4)}, self.room, 'send')
        offering.refresh_from_db()
        self.assertEqual(offering.status, Offering.Status.PENDING)
        self.assertEqual(offering.time_list, ['Wednesday, periods 2–4'])

        # 老師申請調整 → 排課人員同意並改排 → 老師接受
        self.client.force_login(chen)
        self.client.post(reverse('scheduling:request_change', args=[offering.pk]),
                         {'reason': '週三有會議', 'cell': ['4-2', '4-3', '4-4']})
        offering.refresh_from_db()
        self.assertEqual(offering.status, Offering.Status.CHANGE_REQUESTED)
        change = ChangeRequest.objects.get(offering=offering)

        self.client.force_login(self.scheduler)
        response = self.client.post(reverse('scheduling:request_resolve', args=[change.pk]), {'decision': 'approve'})
        self.assertRedirects(response, reverse('scheduling:board', args=[offering.pk]) + f'?from_request={change.pk}')
        board = self.client.get(response['Location'])
        self.assertContains(board, 'value="4-2" checked')  # 帶入老師希望的時段
        self.board_post(offering, {(4, 2), (4, 3), (4, 4)}, self.room, 'send')

        self.client.force_login(chen)
        self.client.post(reverse('scheduling:teaching'), {'offering': 'all'})
        offering.refresh_from_db()
        self.assertEqual(offering.status, Offering.Status.ACCEPTED)

        # 公布 → 學生從目錄加入，時段、老師、教室自動帶入
        self.client.force_login(self.scheduler)
        self.client.post(reverse('scheduling:publish'), {'action': 'publish'})
        offering.refresh_from_db()
        self.assertEqual(offering.status, Offering.Status.PUBLISHED)

        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse('scheduling:catalog')), '網頁程式設計')
        self.client.post(reverse('scheduling:catalog'), {'offering': offering.pk})
        course = Course.objects.get(owner=self.student, offering=offering)
        self.assertEqual(course.teacher, '陳老師')
        self.assertEqual(course.classroom, '六教 601')
        self.assertEqual([str(t) for t in course.times.all()], ['Thursday, periods 2–4'])

    def test_save_draft_allows_incomplete_periods_but_not_conflicts(self):
        self.client.force_login(self.scheduler)
        offering = self.offering()
        self.board_post(offering, {(2, 1)}, self.room, 'save')
        self.assertEqual(offering.times.count(), 1)
        self.place(self.offering('統計學', teacher=self.teacher2), {(5, 1)}, self.room2)
        self.board_post(offering, {(5, 1)}, self.room, 'save')
        self.assertEqual([str(t) for t in offering.times.all()], ['Tuesday, period 1'])

    def test_check_endpoint_returns_json(self):
        self.client.force_login(self.scheduler)
        offering = self.offering()
        data = self.board_post(offering, {(2, 1), (2, 2), (2, 3)}, self.room, 'check').json()
        self.assertTrue(data['ok'])
        self.assertIn(self.room.pk, [room['id'] for room in data['rooms']])
        self.assertNotIn(self.lab.pk, [room['id'] for room in data['rooms']])  # 類型不符的教室不列出

    def test_decline_keeps_schedule_and_asks_teacher_again(self):
        offering = self.place(self.offering(), {(2, 1), (2, 2), (2, 3)}, self.room, Offering.Status.CHANGE_REQUESTED)
        change = ChangeRequest.objects.create(offering=offering, reason='想換時段')
        self.client.force_login(self.scheduler)
        self.client.post(reverse('scheduling:request_resolve', args=[change.pk]),
                         {'decision': 'decline', f'r{change.pk}-response': '教室已滿'})
        change.refresh_from_db()
        offering.refresh_from_db()
        self.assertEqual(change.status, ChangeRequest.Status.DECLINED)
        self.assertEqual(offering.status, Offering.Status.PENDING)
        self.assertIn('教室已滿', mail.outbox[-1].body)

    def test_publish_only_accepted_and_unpublish_unlinks_students(self):
        accepted = self.place(self.offering(), {(2, 1), (2, 2), (2, 3)}, self.room, Offering.Status.ACCEPTED)
        pending = self.place(self.offering('統計學', teacher=self.teacher2, group=self.group2),
                             {(3, 1), (3, 2), (3, 3)}, self.room, Offering.Status.PENDING)
        self.client.force_login(self.scheduler)
        self.client.post(reverse('scheduling:publish'), {'action': 'publish'})
        accepted.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(accepted.status, Offering.Status.PUBLISHED)
        self.assertEqual(pending.status, Offering.Status.PENDING)

        course = Course.objects.create(owner=self.student, name=accepted.name, offering=accepted)
        self.client.post(reverse('scheduling:publish'), {'action': 'unpublish', 'offering': accepted.pk})
        course.refresh_from_db()
        self.assertIsNone(course.offering)

    def test_send_all_skips_drafts_with_problems(self):
        good = self.place(self.offering(), {(2, 1), (2, 2), (2, 3)}, self.room)
        bad = self.place(self.offering('統計學', teacher=self.teacher2, group=self.group2), {(3, 1)}, self.room2)
        self.client.force_login(self.scheduler)
        self.client.post(reverse('scheduling:offering_send_all'))
        good.refresh_from_db()
        bad.refresh_from_db()
        self.assertEqual(good.status, Offering.Status.PENDING)
        self.assertEqual(bad.status, Offering.Status.DRAFT)


class AvailabilityTests(SchedulingTestCase):
    def test_closed_form_is_read_only(self):
        self.term.availability_deadline = timezone.localdate() - timedelta(days=1)
        self.term.save()
        self.client.force_login(self.teacher)
        self.client.post(reverse('scheduling:availability'), {'a-1-1': 'unavailable', 'action': 'submit'})
        self.assertFalse(AvailabilitySlot.objects.exists())

    def test_opening_form_emails_teachers(self):
        self.term.availability_open = False
        self.term.save()
        self.client.force_login(self.scheduler)
        self.client.post(reverse('scheduling:term_availability', args=[self.term.pk]), {'open': '1'})
        self.term.refresh_from_db()
        self.assertTrue(self.term.availability_open)
        self.assertEqual(sorted(mail.outbox[-1].to), ['lee@example.com', 'wang@example.com'])


class InvitationTests(SchedulingTestCase):
    def test_expired_or_used_invitation_cannot_be_accepted(self):
        invite = TeacherInvitation.objects.create(name='X', email='x@example.com', invited_by=self.scheduler,
                                                  expires_at=timezone.now() - timedelta(minutes=1))
        self.client.force_login(self.student)
        self.client.post(reverse('scheduling:accept_invite', args=[invite.token]))
        self.assertFalse(self.student.groups.filter(name=TEACHERS).exists())

    def test_signup_next_must_be_local(self):
        response = self.client.post(reverse('signup'), {
            'username': 'newbie', 'email': 'newbie@example.com',
            'password1': 'Sch3dule-pass!', 'password2': 'Sch3dule-pass!', 'next': 'https://evil.example.com/',
            'class_group': self.group.pk,
        })
        self.assertRedirects(response, reverse('timetable'))


class CapacityTests(SchedulingTestCase):
    """A：事後修改與公布前的容量檢查。"""

    def offering_post(self, offering, **changes):
        data = {
            'term': offering.term_id, 'name': offering.name, 'credits': offering.credits, 'category': offering.category,
            'class_group': offering.class_group_id, 'teacher': offering.teacher_id,
            'periods_per_week': offering.periods_per_week, 'room_kind': offering.room_kind, 'capacity': offering.capacity,
        }
        data.update(changes)
        return self.client.post(reverse('scheduling:offering_edit', args=[offering.pk]), data)

    def test_offering_capacity_cannot_exceed_scheduled_room(self):
        offering = self.place(self.offering(), {(2, 1), (2, 2), (2, 3)}, self.room)  # 六教 601 容量 60
        self.client.force_login(self.scheduler)
        response = self.offering_post(offering, capacity=80)
        self.assertContains(response, 'holds only 60')
        offering.refresh_from_db()
        self.assertEqual(offering.capacity, 50)

    def test_offering_capacity_cannot_drop_below_enrolled(self):
        offering = self.place(self.offering(capacity=3), {(2, 1), (2, 2), (2, 3)}, self.room, Offering.Status.PUBLISHED)
        for name in ('s1', 's2'):
            Course.objects.create(owner=self.make_user(name), name=offering.name, offering=offering)
        self.client.force_login(self.scheduler)
        self.assertContains(self.offering_post(offering, capacity=1), '2 students have already added')

    def test_classroom_cannot_shrink_below_scheduled_course(self):
        self.place(self.offering(), {(2, 1), (2, 2), (2, 3)}, self.room)
        self.client.force_login(self.scheduler)
        response = self.client.post(reverse('scheduling:manage_edit', args=['classrooms', self.room.pk]),
                                    {'name': self.room.name, 'capacity': 30, 'kind': 'general'})
        self.assertContains(response, 'need more seats')
        self.room.refresh_from_db()
        self.assertEqual(self.room.capacity, 60)

    def test_publish_skips_offerings_that_break_rules(self):
        good = self.place(self.offering(), {(2, 1), (2, 2), (2, 3)}, self.room, Offering.Status.ACCEPTED)
        bad = self.place(self.offering('大班課', teacher=self.teacher2, group=self.group2), {(3, 1), (3, 2), (3, 3)},
                         self.room2, Offering.Status.ACCEPTED)
        Classroom.objects.filter(pk=self.room2.pk).update(capacity=10)  # 繞過表單，模擬資料已不一致
        self.client.force_login(self.scheduler)
        response = self.client.post(reverse('scheduling:publish'), {'action': 'publish'}, follow=True)
        good.refresh_from_db()
        bad.refresh_from_db()
        self.assertEqual(good.status, Offering.Status.PUBLISHED)
        self.assertEqual(bad.status, Offering.Status.ACCEPTED)
        self.assertContains(response, 'Not published: 大班課')


class SeatsAndWaitlistTests(SchedulingTestCase):
    """B：名額顯示與額滿；C：候補與自動遞補。"""

    def setUp(self):
        super().setUp()
        self.term.published_at = timezone.now()
        self.term.save()
        self.seminar = self.place(self.offering('專題討論', capacity=1), {(2, 1), (2, 2), (2, 3)}, self.room,
                                  Offering.Status.PUBLISHED)
        self.first = self.make_user('first')
        self.second = self.make_user('second')
        self.third = self.make_user('third')

    def catalog_post(self, user, action='add'):
        self.client.force_login(user)
        return self.client.post(reverse('scheduling:catalog'), {'offering': self.seminar.pk, 'action': action},
                                follow=True)

    def test_catalog_shows_seats_and_blocks_when_full(self):
        self.catalog_post(self.first)
        response = self.catalog_post(self.second)
        self.assertContains(response, 'is full')
        self.assertContains(response, 'Enrolled 1 / 1')
        self.assertContains(response, 'Join waitlist')
        self.assertFalse(Course.objects.filter(owner=self.second, offering=self.seminar).exists())

    def test_waitlist_positions_and_leave(self):
        self.catalog_post(self.first)
        self.catalog_post(self.second, 'waitlist')
        response = self.catalog_post(self.third, 'waitlist')
        self.assertContains(response, 'Waitlist #2')
        self.catalog_post(self.second, 'leave_waitlist')
        self.client.force_login(self.third)
        self.assertContains(self.client.get(reverse('scheduling:catalog')), 'Waitlist #1')

    def test_teacher_sees_enrolled_and_waitlist_counts(self):
        self.catalog_post(self.first)
        self.catalog_post(self.second, 'waitlist')
        self.client.force_login(self.seminar.teacher)
        response = self.client.get(reverse('scheduling:teaching'))
        self.assertContains(response, 'Enrolled 1 / 1')
        self.assertContains(response, 'Waitlist 1')

    def test_cannot_waitlist_when_seats_left(self):
        response = self.catalog_post(self.first, 'waitlist')
        self.assertContains(response, 'still has seats')
        self.assertFalse(self.seminar.waitlist.exists())

    def test_dropping_promotes_first_on_waitlist(self):
        self.catalog_post(self.first)
        self.catalog_post(self.second, 'waitlist')
        self.catalog_post(self.third, 'waitlist')
        course = Course.objects.get(owner=self.first, offering=self.seminar)
        self.client.force_login(self.first)
        self.client.post(reverse('course_delete', args=[course.pk]))
        self.assertTrue(Course.objects.filter(owner=self.second, offering=self.seminar).exists())
        self.assertFalse(Course.objects.filter(owner=self.third, offering=self.seminar).exists())
        self.assertEqual(list(self.seminar.waitlist.values_list('student__username', flat=True)), ['third'])
        self.assertIn('You got a seat', mail.outbox[-1].subject)

    def test_raising_capacity_promotes_waitlist(self):
        self.catalog_post(self.first)
        self.catalog_post(self.second, 'waitlist')
        self.catalog_post(self.third, 'waitlist')
        self.client.force_login(self.scheduler)
        data = {
            'term': self.term.pk, 'name': '專題討論', 'credits': 3, 'category': 'required',
            'class_group': self.group.pk, 'teacher': self.teacher.pk, 'periods_per_week': 3,
            'room_kind': 'general', 'capacity': 3,
        }
        self.client.post(reverse('scheduling:offering_edit', args=[self.seminar.pk]), data)
        self.assertEqual(self.seminar.enrolled_count, 3)
        self.assertFalse(self.seminar.waitlist.exists())

    def test_unpublish_clears_waitlist(self):
        self.catalog_post(self.first)
        self.catalog_post(self.second, 'waitlist')
        self.client.force_login(self.scheduler)
        self.client.post(reverse('scheduling:publish'), {'action': 'unpublish', 'offering': self.seminar.pk})
        self.assertFalse(self.seminar.waitlist.exists())

    def test_offering_list_shows_enrolled_and_waitlist(self):
        self.catalog_post(self.first)
        self.catalog_post(self.second, 'waitlist')
        self.client.force_login(self.scheduler)
        response = self.client.get(reverse('scheduling:offerings'))
        self.assertContains(response, '1 / 1')
        self.assertContains(response, 'Waitlist 1')


class SeedDemoTests(TestCase):
    def test_refuses_without_debug(self):
        from django.core.management import CommandError, call_command

        with self.assertRaises(CommandError):
            call_command('seed_demo', stdout=None)  # 測試時 DEBUG=False

    def test_creates_demo_data_and_can_run_twice(self):
        from io import StringIO

        from django.core.management import call_command

        for _ in range(2):
            call_command('seed_demo', force=True, stdout=StringIO())
        student = User.objects.get(username='demo_student')
        self.assertTrue(student.check_password('demo-pass-2026'))
        term, previous = Term.objects.get(name='115-1'), Term.objects.get(name='114-2')
        self.assertEqual(student.courses.filter(term=term).count(), 7)  # 6 門自己新增＋1 門正式課程
        self.assertEqual(student.courses.filter(term=previous).count(), 5)  # 上學期，示範切換學期
        self.assertEqual(student.courses.filter(offering__isnull=False).count(), 1)
        self.assertEqual(student.student_profile.class_group.name, '資管一甲')
        self.assertTrue(User.objects.get(username='demo_scheduler').groups.filter(name=SCHEDULERS).exists())
        self.assertTrue(User.objects.get(username='demo_teacher').groups.filter(name=TEACHERS).exists())
        self.assertEqual(term.offerings.count(), 9)
        self.assertEqual(term.offerings.filter(status=Offering.Status.PUBLISHED).count(), 3)
        self.assertEqual(term.offerings.get(name='專題討論').seats_left, 0)  # 已額滿，可示範候補
        self.assertEqual(ChangeRequest.objects.filter(offering__term=term).count(), 1)

        self.client.login(username='demo_student', password='demo-pass-2026')
        response = self.client.get(reverse('timetable'))
        self.assertContains(response, '經濟學')
        self.assertNotContains(response, '微積分（二）')
        self.assertContains(self.client.get(reverse('timetable'), {'term': previous.pk}), '微積分（二）')


class CatalogTests(SchedulingTestCase):
    def setUp(self):
        super().setUp()
        self.term.published_at = timezone.now()
        self.term.save()
        self.published = self.place(self.offering(), {(2, 1), (2, 2), (2, 3)}, self.room, Offering.Status.PUBLISHED)
        self.client.force_login(self.student)

    def test_only_published_offerings_are_listed(self):
        self.place(self.offering('統計學', teacher=self.teacher2, group=self.group2), {(3, 1)}, self.room2,
                   Offering.Status.ACCEPTED)
        response = self.client.get(reverse('scheduling:catalog'))
        self.assertContains(response, '網頁程式設計')
        self.assertNotContains(response, '統計學')

    def test_conflict_with_personal_course_needs_confirmation(self):
        own = Course.objects.create(owner=self.student, name='社團')
        CourseTime.objects.create(course=own, weekday=2, start_period=Period.objects.get(number=2),
                                  end_period=Period.objects.get(number=2))
        response = self.client.post(reverse('scheduling:catalog'), {'offering': self.published.pk})
        self.assertContains(response, 'overlaps with')
        self.assertFalse(Course.objects.filter(offering=self.published).exists())
        self.client.post(reverse('scheduling:catalog'), {'offering': self.published.pk, 'allow_conflict': '1'})
        self.assertTrue(Course.objects.filter(offering=self.published).exists())

    def test_official_course_times_cannot_be_edited(self):
        self.client.post(reverse('scheduling:catalog'), {'offering': self.published.pk})
        course = Course.objects.get(offering=self.published)
        url = reverse('course_update', args=[course.pk])
        self.assertContains(self.client.get(url), 'Official course')
        self.client.post(url, {'color': '#123456', 'note': '帶筆電', 'name': '改名', 'times-TOTAL_FORMS': 0})
        course.refresh_from_db()
        self.assertEqual((course.color, course.note, course.name), ('#123456', '帶筆電', '網頁程式設計'))
        self.assertEqual(course.times.count(), 1)

    def test_filters(self):
        response = self.client.get(reverse('scheduling:catalog'), {'q': '王老師'})
        self.assertContains(response, '網頁程式設計')
        response = self.client.get(reverse('scheduling:catalog'), {'q': '不存在'})
        self.assertNotContains(response, '網頁程式設計</strong>')


class ClassGroupTests(SchedulingTestCase):
    """學生的班級：註冊時選、個人設定可改、課程目錄預設只顯示自己班、排課人員看得到班級人數。"""

    def signup(self, **extra):
        data = {'username': 'newbie', 'email': 'newbie@example.com',
                'password1': 'Sch3dule-pass!', 'password2': 'Sch3dule-pass!'}
        data.update(extra)
        return self.client.post(reverse('signup'), data)

    def test_signup_requires_class_group(self):
        response = self.signup()
        self.assertContains(response, 'This field is required')
        self.assertFalse(User.objects.filter(username='newbie').exists())
        self.signup(class_group=self.group.pk)
        self.assertEqual(User.objects.get(username='newbie').student_profile.class_group, self.group)

    def test_teacher_signup_from_invitation_skips_class_group(self):
        invite = TeacherInvitation.objects.create(name='陳老師', email='newbie@example.com', invited_by=self.scheduler)
        response = self.signup(next=reverse('scheduling:accept_invite', args=[invite.token]))
        self.assertRedirects(response, reverse('scheduling:accept_invite', args=[invite.token]),
                             fetch_redirect_response=False)
        self.assertFalse(StudentProfile.objects.filter(user__username='newbie').exists())

    def test_profile_changes_class_group(self):
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse('profile')), 'Class group')
        self.client.post(reverse('profile'), {'class_group': self.group2.pk})
        self.assertEqual(self.student.student_profile.class_group, self.group2)

    def test_catalog_defaults_to_own_class(self):
        self.term.published_at = timezone.now()
        self.term.save()
        self.place(self.offering(), {(2, 1)}, self.room, Offering.Status.PUBLISHED)
        self.place(self.offering('統計學', teacher=self.teacher2, group=self.group2), {(3, 1)}, self.room2,
                   Offering.Status.PUBLISHED)
        StudentProfile.objects.create(user=self.student, class_group=self.group2)
        self.client.force_login(self.student)
        response = self.client.get(reverse('scheduling:catalog'))
        self.assertContains(response, '統計學')
        self.assertNotContains(response, '網頁程式設計</strong>')
        self.assertContains(response, 'Showing courses for your class')
        response = self.client.get(reverse('scheduling:catalog'), {'group': ''})  # 所有班級
        self.assertContains(response, '網頁程式設計</strong>')
        self.assertContains(response, '統計學')

    def test_scheduler_sees_student_count_per_class(self):
        StudentProfile.objects.create(user=self.student, class_group=self.group)
        StudentProfile.objects.create(user=self.make_user('other'), class_group=self.group)
        self.client.force_login(self.scheduler)
        response = self.client.get(reverse('scheduling:manage', args=['groups']))
        self.assertContains(response, '2 students')
        self.assertContains(response, '0 students')


class TermTimetableTests(SchedulingTestCase):
    """個人課表分學期：切換學期、新增到目前學期、衝堂只看同一學期。"""

    def setUp(self):
        super().setUp()
        self.term.published_at = timezone.now()
        self.term.save()
        self.previous = Term.objects.create(name='114-2', published_at=timezone.now() - timedelta(days=180))
        self.client.force_login(self.student)

    def course(self, name, term, weekday=1, start=1, end=2):
        course = Course.objects.create(owner=self.student, name=name, term=term, credits=3)
        CourseTime.objects.create(course=course, weekday=weekday, start_period=Period.objects.get(number=start),
                                  end_period=Period.objects.get(number=end))
        return course

    def test_shows_latest_published_term_by_default_and_can_switch(self):
        self.course('經濟學', self.term)
        self.course('微積分', self.previous)
        response = self.client.get(reverse('timetable'))
        self.assertContains(response, '經濟學')
        self.assertNotContains(response, '微積分')
        self.assertEqual(response.context['total_credits'], 3)
        response = self.client.get(reverse('timetable'), {'term': self.previous.pk})
        self.assertContains(response, '微積分')
        self.assertNotContains(response, '經濟學')

    def test_new_course_goes_to_selected_term(self):
        url = reverse('course_create') + f'?term={self.previous.pk}'
        response = self.client.post(url, {
            'term': self.previous.pk, 'name': '英文', 'credits': 2, 'category': 'other',
            'times-TOTAL_FORMS': 1, 'times-INITIAL_FORMS': 0, 'times-MIN_NUM_FORMS': 1, 'times-MAX_NUM_FORMS': 1000,
            'times-0-weekday': 1, 'times-0-start_period': Period.objects.get(number=1).pk,
            'times-0-end_period': Period.objects.get(number=2).pk,
        })
        self.assertRedirects(response, reverse('timetable') + f'?term={self.previous.pk}')
        self.assertEqual(Course.objects.get(name='英文').term, self.previous)

    def test_conflicts_only_within_same_term(self):
        self.course('微積分', self.previous, weekday=1, start=1, end=2)
        data = {
            'term': self.term.pk, 'name': '經濟學', 'credits': 3, 'category': 'required',
            'times-TOTAL_FORMS': 1, 'times-INITIAL_FORMS': 0, 'times-MIN_NUM_FORMS': 1, 'times-MAX_NUM_FORMS': 1000,
            'times-0-weekday': 1, 'times-0-start_period': Period.objects.get(number=1).pk,
            'times-0-end_period': Period.objects.get(number=2).pk,
        }
        response = self.client.post(reverse('course_create'), data)
        self.assertEqual(response.status_code, 302)  # 和上學期的課同時段不算衝堂
        data.update(name='會計學')
        response = self.client.post(reverse('course_create'), data)
        self.assertContains(response, 'overlaps with')

    def test_course_without_term_shows_in_default_term(self):
        self.course('社團', None)
        self.assertContains(self.client.get(reverse('timetable')), '社團')
        self.assertNotContains(self.client.get(reverse('timetable'), {'term': self.previous.pk}), '社團')

    def test_catalog_course_uses_offering_term(self):
        offering = self.place(self.offering(), {(2, 1)}, self.room, Offering.Status.PUBLISHED)
        self.client.post(reverse('scheduling:catalog'), {'offering': offering.pk, 'group': ''})
        self.assertEqual(Course.objects.get(offering=offering).term, self.term)

    def test_shared_page_can_switch_term(self):
        from schedule.models import ShareLink

        self.course('微積分', self.previous)
        link = ShareLink.objects.create(user=self.student, is_active=True)
        url = reverse('shared_timetable', args=[link.token])
        self.client.logout()
        self.assertNotContains(self.client.get(url), '微積分')
        self.assertContains(self.client.get(url, {'term': self.previous.pk}), '微積分')

    def test_term_with_personal_courses_cannot_be_deleted(self):
        self.course('微積分', self.previous)
        self.client.force_login(self.scheduler)
        self.client.post(reverse('scheduling:manage_delete', args=['terms', self.previous.pk]))
        self.assertTrue(Term.objects.filter(pk=self.previous.pk).exists())
