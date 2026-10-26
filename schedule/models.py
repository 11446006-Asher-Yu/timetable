import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, RegexValidator
from django.db import models


class Period(models.Model):
    """節次，全站共用（資料見 fixtures/periods.json）。"""

    number = models.PositiveSmallIntegerField('節次編號', unique=True)
    label = models.CharField('顯示名稱', max_length=20)
    start_time = models.TimeField('上課時間')
    end_time = models.TimeField('下課時間')

    class Meta:
        ordering = ['number']
        verbose_name = '節次'
        verbose_name_plural = '節次'

    def __str__(self):
        return f'{self.label}（{self.start_time:%H:%M}–{self.end_time:%H:%M}）'

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError('下課時間必須晚於上課時間。')


class Course(models.Model):
    class Category(models.TextChoices):
        REQUIRED = 'required', '必修'
        ELECTIVE = 'elective', '選修'
        GENERAL = 'general', '通識'
        PE = 'pe', '體育'
        OTHER = 'other', '其他'

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
        verbose_name='擁有者',
    )
    name = models.CharField('課程名稱', max_length=100)
    teacher = models.CharField('授課老師', max_length=50, blank=True)
    classroom = models.CharField('上課教室', max_length=50, blank=True)
    credits = models.PositiveSmallIntegerField(
        '學分數', default=0, validators=[MaxValueValidator(6)]
    )
    category = models.CharField(
        '類別', max_length=10, choices=Category.choices, default=Category.REQUIRED
    )
    color = models.CharField(
        '自訂顏色',
        max_length=7,
        blank=True,
        validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$', '請輸入 #RRGGBB 格式的色碼。')],
        help_text='留白則使用類別預設色',
    )
    note = models.TextField('備註', blank=True)
    created_at = models.DateTimeField('建立時間', auto_now_add=True)
    updated_at = models.DateTimeField('修改時間', auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = '課程'
        verbose_name_plural = '課程'

    def __str__(self):
        return self.name

    @property
    def display_color(self):
        return self.color or self.CATEGORY_COLORS[self.category]


class CourseTime(models.Model):
    """課程的一個上課時段；一門課可以有多個時段，學分仍以課程計算。"""

    class Weekday(models.IntegerChoices):
        MON = 1, '星期一'
        TUE = 2, '星期二'
        WED = 3, '星期三'
        THU = 4, '星期四'
        FRI = 5, '星期五'
        SAT = 6, '星期六'
        SUN = 7, '星期日'

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name='times', verbose_name='課程'
    )
    weekday = models.PositiveSmallIntegerField('星期', choices=Weekday.choices)
    # PROTECT：節次被課程使用中時不可刪除
    start_period = models.ForeignKey(
        Period, on_delete=models.PROTECT, related_name='+', verbose_name='開始節次'
    )
    end_period = models.ForeignKey(
        Period, on_delete=models.PROTECT, related_name='+', verbose_name='結束節次'
    )

    class Meta:
        ordering = ['weekday', 'start_period__number']
        verbose_name = '上課時段'
        verbose_name_plural = '上課時段'

    def __str__(self):
        if self.start_period_id == self.end_period_id:
            periods = f'第 {self.start_period.number} 節'
        else:
            periods = f'第 {self.start_period.number}–{self.end_period.number} 節'
        return f'{self.get_weekday_display()} {periods}'

    def clean(self):
        if (
            self.start_period_id
            and self.end_period_id
            and self.start_period.number > self.end_period.number
        ):
            raise ValidationError('結束節次不可早於開始節次。')


class ShareLink(models.Model):
    """唯讀分享連結，網址為 /s/<token>/。"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='share_link',
        verbose_name='使用者',
    )
    token = models.UUIDField('識別碼', default=uuid.uuid4, unique=True, editable=False)
    is_active = models.BooleanField('開放分享', default=False)

    class Meta:
        verbose_name = '分享連結'
        verbose_name_plural = '分享連結'

    def __str__(self):
        return f'{self.user} 的分享連結'

    def regenerate(self):
        """換一組新的 token，舊連結隨即失效。"""
        self.token = uuid.uuid4()
        self.save(update_fields=['token'])
