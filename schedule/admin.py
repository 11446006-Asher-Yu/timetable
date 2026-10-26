from django.contrib import admin

from .models import Course, CourseTime, Period, ShareLink


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ['number', 'label', 'start_time', 'end_time']


class CourseTimeInline(admin.TabularInline):
    model = CourseTime
    extra = 1


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'category', 'credits', 'teacher', 'classroom']
    list_filter = ['category']
    search_fields = ['name', 'teacher', 'owner__username']
    inlines = [CourseTimeInline]


@admin.register(ShareLink)
class ShareLinkAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_active', 'token']
    readonly_fields = ['token']
