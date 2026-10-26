from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse

from .models import Course, CourseTime, Period, ShareLink


class ModelTests(TestCase):
    fixtures = ['periods']

    def setUp(self):
        self.user = get_user_model().objects.create_user('student', password='pw-12345678')

    def test_periods_fixture_loaded(self):
        self.assertEqual(Period.objects.count(), 14)

    def test_display_color_falls_back_to_category(self):
        course = Course(owner=self.user, name='統計學', category=Course.Category.GENERAL)
        self.assertEqual(course.display_color, Course.CATEGORY_COLORS['general'])
        course.color = '#123456'
        self.assertEqual(course.display_color, '#123456')

    def test_credits_counted_once_per_course(self):
        course = Course.objects.create(owner=self.user, name='網頁程式設計', credits=3)
        p = {n: Period.objects.get(number=n) for n in (1, 2, 5)}
        CourseTime.objects.create(course=course, weekday=2, start_period=p[1], end_period=p[2])
        CourseTime.objects.create(course=course, weekday=4, start_period=p[5], end_period=p[5])
        total = self.user.courses.aggregate(total=Sum('credits'))['total']
        self.assertEqual(total, 3)
        self.assertEqual(str(course.times.first()), '星期二 第 1–2 節')

    def test_end_period_before_start_is_invalid(self):
        course = Course.objects.create(owner=self.user, name='英文')
        time = CourseTime(
            course=course,
            weekday=1,
            start_period=Period.objects.get(number=3),
            end_period=Period.objects.get(number=2),
        )
        with self.assertRaises(ValidationError):
            time.full_clean()

    def test_share_link_regenerate_changes_token(self):
        link = ShareLink.objects.create(user=self.user)
        old = link.token
        link.regenerate()
        link.refresh_from_db()
        self.assertNotEqual(link.token, old)


class AuthTests(TestCase):
    password = 'Sch3dule-pass!'

    def signup(self, username='newbie', email='newbie@example.com'):
        return self.client.post(reverse('signup'), {
            'username': username,
            'email': email,
            'password1': self.password,
            'password2': self.password,
        })

    def test_signup_creates_user_and_logs_in(self):
        response = self.signup()
        self.assertRedirects(response, reverse('timetable'))
        user = get_user_model().objects.get(username='newbie')
        self.assertEqual(user.email, 'newbie@example.com')
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_signup_rejects_duplicate_email(self):
        self.signup()
        self.client.logout()
        response = self.signup(username='other', email='NEWBIE@example.com')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '這個 Email 已經註冊過了。')
        self.assertFalse(get_user_model().objects.filter(username='other').exists())

    def test_timetable_requires_login(self):
        response = self.client.get(reverse('timetable'))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('timetable')}")

    def test_login_and_logout(self):
        get_user_model().objects.create_user('student', password=self.password)
        response = self.client.post(
            reverse('login'), {'username': 'student', 'password': self.password}
        )
        self.assertRedirects(response, reverse('timetable'))
        response = self.client.post(reverse('logout'))
        self.assertRedirects(response, reverse('home'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_home_redirects_logged_in_user(self):
        user = get_user_model().objects.create_user('student', password=self.password)
        self.client.force_login(user)
        self.assertRedirects(self.client.get(reverse('home')), reverse('timetable'))


class CourseCrudTests(TestCase):
    fixtures = ['periods']

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('student', password='pw-12345678')
        self.other = User.objects.create_user('other', password='pw-12345678')
        self.client.force_login(self.user)

    def course_data(self, times, **overrides):
        """組出課程表單＋上課時段 formset 的 POST 資料。times 為 (星期, 起, 迄[, id, 刪除])。"""
        data = {
            'name': '網頁程式設計', 'teacher': '王老師', 'classroom': '六教 601',
            'credits': 3, 'category': 'required', 'color': '', 'note': '',
            'times-TOTAL_FORMS': len(times), 'times-INITIAL_FORMS': 0,
            'times-MIN_NUM_FORMS': 1, 'times-MAX_NUM_FORMS': 1000,
        }
        initial = 0
        for i, (weekday, start, end, *rest) in enumerate(times):
            data[f'times-{i}-weekday'] = weekday
            data[f'times-{i}-start_period'] = Period.objects.get(number=start).pk
            data[f'times-{i}-end_period'] = Period.objects.get(number=end).pk
            if rest:
                data[f'times-{i}-id'] = rest[0]
                initial += 1
                if len(rest) > 1 and rest[1]:
                    data[f'times-{i}-DELETE'] = 'on'
        data['times-INITIAL_FORMS'] = initial
        data.update(overrides)
        return data

    def test_create_course_with_two_times(self):
        response = self.client.post(reverse('course_create'), self.course_data([(2, 1, 2), (4, 5, 5)]))
        self.assertRedirects(response, reverse('timetable'))
        course = Course.objects.get(owner=self.user)
        self.assertEqual(course.times.count(), 2)
        self.assertContains(self.client.get(reverse('timetable')), '總學分 3')

    def test_create_requires_at_least_one_time(self):
        response = self.client.post(reverse('course_create'), self.course_data([]))
        self.assertContains(response, '請至少設定 1 個上課時段。')
        self.assertFalse(Course.objects.exists())

    def test_overlapping_times_in_same_course_rejected(self):
        response = self.client.post(reverse('course_create'), self.course_data([(2, 1, 3), (2, 3, 4)]))
        self.assertContains(response, '同一門課的上課時段重疊了')
        self.assertFalse(Course.objects.exists())

    def test_end_before_start_rejected(self):
        response = self.client.post(reverse('course_create'), self.course_data([(1, 4, 2)]))
        self.assertContains(response, '結束節次不可早於開始節次。')
        self.assertFalse(Course.objects.exists())

    def test_update_course_and_delete_one_time(self):
        self.client.post(reverse('course_create'), self.course_data([(2, 1, 2), (4, 5, 5)]))
        course = Course.objects.get()
        keep, drop = course.times.order_by('weekday')
        data = self.course_data(
            [(2, 1, 2, keep.pk), (4, 5, 5, drop.pk, True)], name='網頁程式設計（二）', credits=2
        )
        response = self.client.post(reverse('course_update', args=[course.pk]), data)
        self.assertRedirects(response, reverse('timetable'))
        course.refresh_from_db()
        self.assertEqual(course.name, '網頁程式設計（二）')
        self.assertEqual(list(course.times.values_list('pk', flat=True)), [keep.pk])

    def test_delete_course(self):
        course = Course.objects.create(owner=self.user, name='英文')
        self.assertContains(self.client.get(reverse('course_delete', args=[course.pk])), '英文')
        response = self.client.post(reverse('course_delete', args=[course.pk]))
        self.assertRedirects(response, reverse('timetable'))
        self.assertFalse(Course.objects.exists())

    def test_cannot_touch_other_users_course(self):
        course = Course.objects.create(owner=self.other, name='別人的課')
        self.assertEqual(self.client.get(reverse('course_update', args=[course.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('course_delete', args=[course.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('timetable')), '別人的課')
        self.assertTrue(Course.objects.filter(pk=course.pk).exists())
