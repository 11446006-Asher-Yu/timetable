"""第二階段：排課人員與老師協調排課。"""

import uuid
from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from schedule.models import Course, CourseTime, Period, describe_time

# 角色以 Django Group 表示（由 migration 0002 建立）
SCHEDULERS = 'Schedulers'
TEACHERS = 'Teachers'

INVITATION_DAYS = 7


class Term(models.Model):
    name = models.CharField(_('name'), max_length=20, unique=True, help_text=_('For example 115-1'))
    availability_open = models.BooleanField(_('availability form open'), default=False)
    availability_deadline = models.DateField(_('availability deadline'), null=True, blank=True)
    published_at = models.DateTimeField(_('published at'), null=True, blank=True)

    class Meta:
        ordering = ['-name']
        verbose_name = _('term')
        verbose_name_plural = _('terms')

    def __str__(self):
        return self.name

    @property
    def availability_editable(self):
        """老師還能修改可授課時段：已開放，且還沒過截止日。"""
        if not self.availability_open:
            return False
        return self.availability_deadline is None or timezone.localdate() <= self.availability_deadline


def default_term():
    """學生課表預設顯示的學期：最新一個已公布的學期，都還沒公布就用最新的學期；沒有學期時回傳 None。"""
    return Term.objects.filter(published_at__isnull=False).first() or Term.objects.first()


class Classroom(models.Model):
    class Kind(models.TextChoices):
        GENERAL = 'general', _('General classroom')
        COMPUTER = 'computer', _('Computer lab')
        OTHER = 'other', _('Other')

    name = models.CharField(_('name'), max_length=50, unique=True)
    capacity = models.PositiveSmallIntegerField(_('capacity'), default=60)
    kind = models.CharField(_('type'), max_length=10, choices=Kind.choices, default=Kind.GENERAL)

    class Meta:
        ordering = ['name']
        verbose_name = _('classroom')
        verbose_name_plural = _('classrooms')

    def __str__(self):
        return f'{self.name} ({self.capacity})'


class ClassGroup(models.Model):
    name = models.CharField(_('name'), max_length=50, unique=True, help_text=_('For example IM 3A'))

    class Meta:
        ordering = ['name']
        verbose_name = _('class group')
        verbose_name_plural = _('class groups')

    def __str__(self):
        return self.name


class StudentProfile(models.Model):
    """學生的班級；註冊時選，之後可在個人設定修改。"""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='student_profile')
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='students',
        verbose_name=_('class group'),
    )

    class Meta:
        verbose_name = _('student profile')
        verbose_name_plural = _('student profiles')

    def __str__(self):
        return f'{self.user} · {self.class_group or "—"}'


def class_group_of(user):
    profile = StudentProfile.objects.filter(user=user).select_related('class_group').first()
    return profile.class_group if profile else None


class Offering(models.Model):
    """排課人員建立的一門開課。"""

    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        PENDING = 'pending', _('Waiting for teacher')
        CHANGE_REQUESTED = 'change_requested', _('Change requested')
        ACCEPTED = 'accepted', _('Accepted')
        PUBLISHED = 'published', _('Published')

    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='offerings', verbose_name=_('term'))
    name = models.CharField(_('course name'), max_length=100)
    credits = models.PositiveSmallIntegerField(_('credits'), default=3, validators=[MaxValueValidator(6)])
    category = models.CharField(
        _('category'), max_length=10, choices=Course.Category.choices, default=Course.Category.REQUIRED
    )
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.PROTECT, related_name='offerings', verbose_name=_('class group')
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='teaching',
        verbose_name=_('teacher'),
        limit_choices_to={'groups__name': TEACHERS},
    )
    periods_per_week = models.PositiveSmallIntegerField(
        _('periods per week'), default=3, validators=[MinValueValidator(1), MaxValueValidator(6)]
    )
    room_kind = models.CharField(
        _('classroom type needed'), max_length=10, choices=Classroom.Kind.choices, default=Classroom.Kind.GENERAL
    )
    capacity = models.PositiveSmallIntegerField(_('maximum students'), default=50)
    classroom = models.ForeignKey(
        Classroom, on_delete=models.PROTECT, null=True, blank=True, related_name='offerings',
        verbose_name=_('classroom'),
    )
    status = models.CharField(_('status'), max_length=20, choices=Status.choices, default=Status.DRAFT)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = _('offering')
        verbose_name_plural = _('offerings')

    def __str__(self):
        return f'{self.name} · {self.class_group}'

    @property
    def time_list(self):
        return [str(time) for time in self.times.all()]

    @property
    def enrolled_count(self):
        """已加入（從課程目錄加進個人課表）的學生數。"""
        return self.student_courses.count()

    @property
    def seats_left(self):
        return max(self.capacity - self.enrolled_count, 0)


class OfferingTime(models.Model):
    offering = models.ForeignKey(Offering, on_delete=models.CASCADE, related_name='times')
    weekday = models.PositiveSmallIntegerField(_('day'), choices=CourseTime.Weekday.choices)
    start_period = models.ForeignKey(Period, on_delete=models.PROTECT, related_name='+')
    end_period = models.ForeignKey(Period, on_delete=models.PROTECT, related_name='+')

    class Meta:
        ordering = ['weekday', 'start_period__number']

    def __str__(self):
        return describe_time(self.weekday, self.start_period.number, self.end_period.number)


class TeacherAvailability(models.Model):
    """一位老師在一個學期的可授課時段；沒有紀錄的格子視為「可以」。"""

    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='availabilities')
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='availabilities')
    note = models.TextField(_('note'), blank=True)
    submitted_at = models.DateTimeField(_('submitted at'), null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['teacher', 'term'], name='one_availability_per_term')]
        verbose_name = _('teacher availability')
        verbose_name_plural = _('teacher availability')

    def status_map(self):
        """{(星期, 節次): 狀態}，只含不是「可以」的格子。"""
        return {(slot.weekday, slot.period): slot.status for slot in self.slots.all()}


class AvailabilitySlot(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = 'available', _('Available')
        AVOID = 'avoid', _('Prefer not')
        UNAVAILABLE = 'unavailable', _('Unavailable')

    availability = models.ForeignKey(TeacherAvailability, on_delete=models.CASCADE, related_name='slots')
    weekday = models.PositiveSmallIntegerField(choices=CourseTime.Weekday.choices)
    period = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['availability', 'weekday', 'period'], name='one_status_per_cell')
        ]


class ChangeRequest(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', _('Waiting')
        APPROVED = 'approved', _('Approved')
        DECLINED = 'declined', _('Declined')

    offering = models.ForeignKey(Offering, on_delete=models.CASCADE, related_name='change_requests')
    reason = models.TextField(_('reason'))
    status = models.CharField(_('status'), max_length=10, choices=Status.choices, default=Status.OPEN)
    response = models.TextField(_('reply'), blank=True)
    created_at = models.DateTimeField(_('requested at'), auto_now_add=True)
    resolved_at = models.DateTimeField(_('resolved at'), null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('change request')
        verbose_name_plural = _('change requests')

    def preferred_cells(self):
        return [(slot.weekday, slot.period) for slot in self.slots.all()]


class ChangeRequestSlot(models.Model):
    request = models.ForeignKey(ChangeRequest, on_delete=models.CASCADE, related_name='slots')
    weekday = models.PositiveSmallIntegerField(choices=CourseTime.Weekday.choices)
    period = models.PositiveSmallIntegerField()


class WaitlistEntry(models.Model):
    """額滿課程的候補名單，依加入時間排序；有名額時由第一位自動遞補。"""

    offering = models.ForeignKey(Offering, on_delete=models.CASCADE, related_name='waitlist')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='waitlist_entries')
    created_at = models.DateTimeField(_('joined at'), auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [models.UniqueConstraint(fields=['offering', 'student'], name='one_waitlist_entry')]
        verbose_name = _('waitlist entry')
        verbose_name_plural = _('waitlist')

    @property
    def position(self):
        return self.offering.waitlist.filter(
            models.Q(created_at__lt=self.created_at) | models.Q(created_at=self.created_at, pk__lt=self.pk)
        ).count() + 1


def default_expiry():
    return timezone.now() + timedelta(days=INVITATION_DAYS)


class TeacherInvitation(models.Model):
    name = models.CharField(_('name'), max_length=50)
    email = models.EmailField(_('email'))
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_invitations'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_expiry)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('teacher invitation')
        verbose_name_plural = _('teacher invitations')

    @property
    def is_usable(self):
        return self.accepted_at is None and timezone.now() < self.expires_at
