from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext, gettext_lazy as _

from .models import TEACHERS, ChangeRequest, ClassGroup, Classroom, Offering, Term
from .roles import display_name


class TermForm(forms.ModelForm):
    class Meta:
        model = Term
        fields = ['name', 'availability_deadline']
        widgets = {'availability_deadline': forms.DateInput(attrs={'type': 'date'})}


class ClassroomForm(forms.ModelForm):
    class Meta:
        model = Classroom
        fields = ['name', 'capacity', 'kind']

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk:
            return cleaned
        # 已排在這間教室的課，不能因為改容量或類型而變得塞不下、類型不符
        capacity, kind = cleaned.get('capacity'), cleaned.get('kind')
        too_small = [o.name for o in self.instance.offerings.all() if capacity is not None and o.capacity > capacity]
        wrong_kind = [o.name for o in self.instance.offerings.all() if kind and o.room_kind != kind]
        if too_small:
            self.add_error('capacity', gettext('These scheduled courses need more seats: %(courses)s')
                           % {'courses': '、'.join(too_small)})
        if wrong_kind:
            self.add_error('kind', gettext('These scheduled courses need the current classroom type: %(courses)s')
                           % {'courses': '、'.join(wrong_kind)})
        return cleaned


class ClassGroupForm(forms.ModelForm):
    class Meta:
        model = ClassGroup
        fields = ['name']


class TeacherChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return display_name(obj)


class OfferingForm(forms.ModelForm):
    teacher = TeacherChoiceField(
        queryset=get_user_model().objects.filter(groups__name=TEACHERS).order_by('first_name', 'username'),
        label=_('Teacher'),
        empty_label=_('Select'),
    )

    class Meta:
        model = Offering
        fields = ['term', 'name', 'credits', 'category', 'class_group', 'teacher',
                  'periods_per_week', 'room_kind', 'capacity']

    def clean(self):
        cleaned = super().clean()
        capacity, room_kind = cleaned.get('capacity'), cleaned.get('room_kind')
        classroom = self.instance.classroom if self.instance.pk else None
        # 已排了教室：人數上限不能超過教室容量，教室類型要相符
        if classroom and capacity is not None and capacity > classroom.capacity:
            self.add_error('capacity', gettext('%(room)s holds only %(seats)s. Choose another classroom first.')
                           % {'room': classroom.name, 'seats': classroom.capacity})
        if classroom and room_kind and room_kind != classroom.kind:
            self.add_error('room_kind', gettext('This course is scheduled in %(room)s. Choose another classroom first.')
                           % {'room': classroom.name})
        # 不能低於已加入的學生數
        if self.instance.pk and capacity is not None and capacity < self.instance.enrolled_count:
            self.add_error('capacity', gettext('%(count)s students have already added this course.')
                           % {'count': self.instance.enrolled_count})
        return cleaned


class InvitationForm(forms.Form):
    name = forms.CharField(label=_('Teacher’s name'), max_length=50)
    email = forms.EmailField(label=_('Email'))


class ChangeRequestForm(forms.ModelForm):
    class Meta:
        model = ChangeRequest
        fields = ['reason']
        widgets = {'reason': forms.Textarea(attrs={'rows': 3})}


class DeclineForm(forms.Form):
    response = forms.CharField(label=_('Reply to the teacher'), widget=forms.Textarea(attrs={'rows': 2}))
