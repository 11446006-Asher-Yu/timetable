from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext_lazy as _

from scheduling.models import ClassGroup, StudentProfile, Term

from .models import Course, CourseTime, Period


class SignUpForm(UserCreationForm):
    # Email 必填且不可重複，忘記密碼時要靠它寄信
    email = forms.EmailField(label=_('Email'))

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ['username', 'first_name', 'email']
        labels = {'first_name': _('Name')}

    class_group = forms.ModelChoiceField(
        ClassGroup.objects.all(), label=_('Class group'), empty_label=_('Select'), required=False,
        help_text=_('The catalog shows your class’s courses first. You can change it later.'),
    )

    def __init__(self, *args, require_class_group=True, **kwargs):
        super().__init__(*args, **kwargs)
        # 姓名顯示在班級名單和老師名單上
        self.fields['first_name'].required = True
        if not require_class_group:
            # 老師從邀請連結註冊，不需要班級
            del self.fields['class_group']
        else:
            # 排課人員還沒建立任何班級時先不強制
            self.fields['class_group'].required = ClassGroup.objects.exists()

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_('This email is already registered.'))
        return email

    def save(self, commit=True):
        user = super().save(commit)
        if commit and 'class_group' in self.fields:
            StudentProfile.objects.create(user=user, class_group=self.cleaned_data.get('class_group'))
        return user


class ProfileForm(forms.ModelForm):
    name = forms.CharField(label=_('Name'), max_length=150)

    class Meta:
        model = StudentProfile
        fields = ['class_group']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].initial = self.instance.user.first_name
        # 和註冊時一樣：有班級可選就必填
        self.fields['class_group'].required = ClassGroup.objects.exists()
        self.order_fields(['name', 'class_group'])

    def save(self, commit=True):
        profile = super().save(commit)
        user = profile.user
        user.first_name = self.cleaned_data['name']
        user.save(update_fields=['first_name'])
        return profile


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['term', 'name', 'teacher', 'classroom', 'credits', 'category', 'color', 'note']
        widgets = {
            'color': forms.TextInput(attrs={'placeholder': '#4F86C6'}),
            'note': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if Term.objects.exists():
            self.fields['term'].required = True
            self.fields['term'].empty_label = None
        else:
            # 還沒有任何學期：不顯示學期欄位
            del self.fields['term']


class OfficialCourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['color', 'note']
        widgets = CourseForm.Meta.widgets


class PeriodChoiceField(forms.ModelChoiceField):
    # 下拉選單空間有限，只顯示「第 1 節 08:10」／“Period 1 08:10”
    def label_from_instance(self, obj):
        return f'{obj.display_label} {obj.start_time:%H:%M}'


class CourseTimeForm(forms.ModelForm):
    start_period = PeriodChoiceField(Period.objects.all(), label=_('Start period'), empty_label=_('Select'))
    end_period = PeriodChoiceField(Period.objects.all(), label=_('End period'), empty_label=_('Select'))

    class Meta:
        model = CourseTime
        fields = ['weekday', 'start_period', 'end_period']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['weekday'].choices = [('', _('Select'))] + list(CourseTime.Weekday.choices)


class BaseCourseTimeFormSet(forms.BaseInlineFormSet):
    default_error_messages = {
        'too_few_forms': _('Add at least one class time.'),
    }

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        # 同一門課的時段不可互相重疊
        seen = []
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            weekday = form.cleaned_data['weekday']
            start = form.cleaned_data['start_period'].number
            end = form.cleaned_data['end_period'].number
            for other_weekday, other_start, other_end in seen:
                if weekday == other_weekday and start <= other_end and other_start <= end:
                    raise forms.ValidationError(_('Class times of the same course overlap. Please check them.'))
            seen.append((weekday, start, end))


CourseTimeFormSet = forms.inlineformset_factory(
    Course,
    CourseTime,
    form=CourseTimeForm,
    formset=BaseCourseTimeFormSet,
    extra=0,
    min_num=1,
    validate_min=True,
    can_delete=True,
)
