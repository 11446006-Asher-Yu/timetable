from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import SignUpForm


def home(request):
    if request.user.is_authenticated:
        return redirect('timetable')
    return render(request, 'home.html')


def signup(request):
    if request.user.is_authenticated:
        return redirect('timetable')
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # 註冊完直接登入
            messages.success(request, f'歡迎，{user.username}！帳號已建立。')
            return redirect('timetable')
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})


@login_required
def timetable(request):
    # 課表格子在 10/30 實作，目前先列出課程數量
    courses = request.user.courses.all()
    return render(request, 'schedule/timetable.html', {'courses': courses})
