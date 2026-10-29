from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from schedule.models import Course, CourseTime, Period

from .models import (
    SCHEDULERS, TEACHERS, AvailabilitySlot, ChangeRequest, ClassGroup, Classroom, Offering, TeacherAvailability,
    TeacherInvitation, Term,
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

    def test_nav_links_follow_roles(self):
        self.client.force_login(self.scheduler)
        response = self.client.get(reverse('timetable'))
        self.assertContains(response, reverse('scheduling:dashboard'))
        self.assertNotContains(response, reverse('scheduling:teacher_home'))
        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(reverse('timetable')), reverse('scheduling:dashboard'))

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
        })
        self.assertRedirects(response, reverse('timetable'))


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
