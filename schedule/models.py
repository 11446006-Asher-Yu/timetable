import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, RegexValidator
from django.db import models
from django.utils.translation import gettext, gettext_lazy as _, pgettext_lazy


class Period(models.Model):
    """節次，全站共用（資料見 fixtures/periods.json）。"""

    number = models.PositiveSmallIntegerField(_('number'), unique=True)
    label = models.CharField(_('label'), max_length=20)
    start_time = models.TimeField(_('start time'))
    end_time = models.TimeField(_('end time'))

    class Meta:
        ordering = ['number']
        verbose_name = _('period')
        verbose_name_plural = _('periods')

    def __str__(self):
        return f'{self.display_label} ({self.start_time:%H:%M}–{self.end_time:%H:%M})'

    @property
    def display_label(self):
        # 資料庫的 label 是中文，畫面上改用翻譯過的「第 N 節」／“Period N”
        return gettext('Period %(number)s') % {'number': self.number}

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError(_('End time must be later than start time.'))


class Course(models.Model):
    class Category(models.TextChoices):
        REQUIRED = 'required', _('Required')
        ELECTIVE = 'elective', _('Elective')
        GENERAL = 'general', _('General education')
        PE = 'pe', _('Physical education')
        OTHER = 'other', _('Other')

    # 使用者沒有自訂顏色時，依類別套用的預設色
    CATEGORY_COLORS = {
        Category.REQUIRED: '#E57373',
        Category.ELECTIVE: '#64B5F6',
        Category.GENERAL: '#81C784',
        Category.PE: '#FFB74D',
        Category.OTHER: '#BA68C8',
    }

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='courses',
        verbose_name=_('owner'),
    )
    name = models.CharField(_('course name'), max_length=100)
    teacher = models.CharField(_('teacher'), max_length=50, blank=True)
    classroom = models.CharField(_('classroom'), max_length=50, blank=True)
    credits = models.PositiveSmallIntegerField(
        _('credits'), default=0, validators=[MaxValueValidator(6)]
    )
    category = models.CharField(
        _('category'), max_length=10, choices=Category.choices, default=Category.REQUIRED
    )
    color = models.CharField(
        _('custom color'),
        max_length=7,
        blank=True,
        validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$', _('Enter a color code like #RRGGBB.'))],
        help_text=_('Leave blank to use the category color.'),
    )
    note = models.TextField(_('note'), blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = _('course')
        verbose_name_plural = _('courses')

    def __str__(self):
        return self.name

    @property
    def display_color(self):
        return self.color or self.CATEGORY_COLORS[self.category]


class CourseTime(models.Model):
    """課程的一個上課時段；一門課可以有多個時段，學分仍以課程計算。"""

    class Weekday(models.IntegerChoices):
        MON = 1, _('Monday')
        TUE = 2, _('Tuesday')
        WED = 3, _('Wednesday')
        THU = 4, _('Thursday')
        FRI = 5, _('Friday')
        SAT = 6, _('Saturday')
        SUN = 7, _('Sunday')

    # 課表標題、手機分頁用的簡稱（英文 Mon、中文「一」）
    WEEKDAY_SHORT = {
        1: pgettext_lazy('weekday', 'Mon'),
        2: pgettext_lazy('weekday', 'Tue'),
        3: pgettext_lazy('weekday', 'Wed'),
        4: pgettext_lazy('weekday', 'Thu'),
        5: pgettext_lazy('weekday', 'Fri'),
        6: pgettext_lazy('weekday', 'Sat'),
        7: pgettext_lazy('weekday', 'Sun'),
    }

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name='times', verbose_name=_('course')
    )
    weekday = models.PositiveSmallIntegerField(_('day'), choices=Weekday.choices)
    # PROTECT：節次被課程使用中時不可刪除
    start_period = models.ForeignKey(
        Period, on_delete=models.PROTECT, related_name='+', verbose_name=_('start period')
    )
    end_period = models.ForeignKey(
        Period, on_delete=models.PROTECT, related_name='+', verbose_name=_('end period')
    )

    class Meta:
        ordering = ['weekday', 'start_period__number']
        verbose_name = _('class time')
        verbose_name_plural = _('class times')

    def __str__(self):
        return describe_time(self.weekday, self.start_period.number, self.end_period.number)

    def clean(self):
        if (
            self.start_period_id
            and self.end_period_id
            and self.start_period.number > self.end_period.number
        ):
            raise ValidationError(_('End period cannot be earlier than start period.'))


def describe_time(weekday, start, end):
    """例如 “Tuesday, periods 1–2”／「星期二 第 1–2 節」。"""
    day = CourseTime.Weekday(weekday).label
    if start == end:
        return gettext('%(day)s, period %(start)s') % {'day': day, 'start': start}
    return gettext('%(day)s, periods %(start)s–%(end)s') % {'day': day, 'start': start, 'end': end}


class ShareLink(models.Model):
    """唯讀分享連結，網址為 /s/<token>/。"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='share_link',
        verbose_name=_('user'),
    )
    token = models.UUIDField(_('token'), default=uuid.uuid4, unique=True, editable=False)
    is_active = models.BooleanField(_('sharing on'), default=False)

    class Meta:
        verbose_name = _('share link')
        verbose_name_plural = _('share links')

    def __str__(self):
        return gettext('Share link of %(user)s') % {'user': self.user}

    def regenerate(self):
        """換一組新的 token，舊連結隨即失效。"""
        self.token = uuid.uuid4()
        self.save(update_fields=['token'])
