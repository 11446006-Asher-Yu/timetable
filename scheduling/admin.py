from django.contrib import admin

from .models import (
    AvailabilitySlot, ChangeRequest, ClassGroup, Classroom, Offering, OfferingTime, TeacherAvailability,
    TeacherInvitation, Term,
)

admin.site.register([Term, Classroom, ClassGroup])


class OfferingTimeInline(admin.TabularInline):
    model = OfferingTime
    extra = 0


@admin.register(Offering)
class OfferingAdmin(admin.ModelAdmin):
    list_display = ['name', 'term', 'class_group', 'teacher', 'classroom', 'status']
    list_filter = ['term', 'status']
    inlines = [OfferingTimeInline]


class AvailabilitySlotInline(admin.TabularInline):
    model = AvailabilitySlot
    extra = 0


@admin.register(TeacherAvailability)
class TeacherAvailabilityAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'term', 'submitted_at']
    inlines = [AvailabilitySlotInline]


@admin.register(ChangeRequest)
class ChangeRequestAdmin(admin.ModelAdmin):
    list_display = ['offering', 'status', 'created_at']


@admin.register(TeacherInvitation)
class TeacherInvitationAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'invited_by', 'expires_at', 'accepted_at']
