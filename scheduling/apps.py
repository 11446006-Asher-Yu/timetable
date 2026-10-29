from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SchedulingConfig(AppConfig):
    name = 'scheduling'
    verbose_name = _('Course scheduling')
