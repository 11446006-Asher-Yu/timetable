from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import Course, CourseTime, Period


class SignUpForm(UserCreationForm):
    # Email 必填且不可重複，忘記密碼時要靠它寄信
    email = forms.EmailField(label='Email')

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ['username', 'email']

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('這個 Email 已經註冊過了。')
        return email


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['name', 'teacher', 'classroom', 'credits', 'category', 'color', 'note']
        widgets = {
            'color': forms.TextInput(attrs={'placeholder': '#4F86C6'}),
            'note': forms.Textarea(attrs={'rows': 3}),
        }


class PeriodChoiceField(forms.ModelChoiceField):
    # 下拉選單空間有限，只顯示「第 1 節 08:10」
    def label_from_instance(self, obj):
        return f'{obj.label} {obj.start_time:%H:%M}'


class CourseTimeForm(forms.ModelForm):
    start_period = PeriodChoiceField(Period.objects.all(), label='開始節次', empty_label='請選擇')
    end_period = PeriodChoiceField(Period.objects.all(), label='結束節次', empty_label='請選擇')

    class Meta:
        model = CourseTime
        fields = ['weekday', 'start_period', 'end_period']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['weekday'].choices = [('', '請選擇')] + list(CourseTime.Weekday.choices)


class BaseCourseTimeFormSet(forms.BaseInlineFormSet):
    default_error_messages = {
        'too_few_forms': '請至少設定 %(num)d 個上課時段。',
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
                    raise forms.ValidationError('同一門課的上課時段重疊了，請檢查。')
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
