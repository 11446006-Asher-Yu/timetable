from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

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
