from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm


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
