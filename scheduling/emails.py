"""排課相關通知信：英文在前、中文在後的雙語信件，不必知道收件人選了哪種語言。

寄信失敗（例如 Gmail 暫時連不上）不能讓排課流程中斷，所以 fail_silently，只記在 log。
"""

import logging

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import translation
from django.utils.translation import gettext

from .models import SCHEDULERS, TEACHERS
from .roles import display_name

logger = logging.getLogger(__name__)


def _send(recipients, build):
    """build() 在目前語言下回傳 (主旨, 內文)；分別用英文、中文各產生一次。"""
    recipients = sorted({address for address in recipients if address})
    if not recipients:
        return
    with translation.override('en'):
        subject_en, body_en = build()
    with translation.override('zh-hant'):
        subject_zh, body_zh = build()
    subject = f'[Online Timetable] {subject_en} / {subject_zh}'
    body = f'{body_en}\n\n— — —\n\n{body_zh}\n'
    try:
        send_mail(subject, body, None, recipients)
    except Exception:  # noqa: BLE001 寄信失敗不影響主流程
        logger.exception('Failed to send scheduling email to %s', recipients)


def _emails_of(group_name):
    return list(get_user_model().objects.filter(groups__name=group_name).values_list('email', flat=True))


def invitation(invite, link):
    _send([invite.email], lambda: (
        gettext('You’re invited to teach'),
        gettext('Hi %(name)s,\n\n%(inviter)s invited you to join Online Timetable as a teacher. '
                'Open the link below to accept (valid for 7 days):\n\n%(link)s')
        % {'name': invite.name, 'inviter': display_name(invite.invited_by), 'link': link},
    ))


def availability_open(term, link):
    deadline = term.availability_deadline.isoformat() if term.availability_deadline else '—'
    _send(_emails_of(TEACHERS), lambda: (
        gettext('Please submit your availability for %(term)s') % {'term': term.name},
        gettext('The availability form for %(term)s is open. Please mark the periods you can and can’t teach '
                'by %(deadline)s:\n\n%(link)s') % {'term': term.name, 'deadline': deadline, 'link': link},
    ))


def sent_for_confirmation(offerings, link):
    by_teacher = {}
    for offering in offerings:
        by_teacher.setdefault(offering.teacher, []).append(offering)
    for teacher, items in by_teacher.items():
        def build(items=items):
            lines = '\n'.join(f'• {o.name} · {o.class_group.name} · {", ".join(o.time_list)}' for o in items)
            return (
                gettext('Please confirm your class schedule'),
                gettext('These classes have been scheduled for you. Please accept them or request a change:'
                        '\n\n%(lines)s\n\n%(link)s') % {'lines': lines, 'link': link},
            )
        _send([teacher.email], build)


def change_requested(change, link):
    offering = change.offering
    _send(_emails_of(SCHEDULERS), lambda: (
        gettext('Change requested: %(course)s') % {'course': offering.name},
        gettext('%(teacher)s requested a change to “%(course)s”.\n\nReason: %(reason)s\n\n%(link)s') % {
            'teacher': display_name(offering.teacher), 'course': offering.name, 'reason': change.reason, 'link': link,
        },
    ))


def request_resolved(change, link):
    offering = change.offering
    _send([offering.teacher.email], lambda: (
        gettext('Your change request for %(course)s was %(result)s') % {
            'course': offering.name, 'result': change.get_status_display().lower(),
        },
        gettext('Reply from the scheduler: %(reply)s\n\n%(link)s') % {
            'reply': change.response or '—', 'link': link,
        },
    ))


def published(term, link):
    _send(_emails_of(TEACHERS), lambda: (
        gettext('The %(term)s timetable is published') % {'term': term.name},
        gettext('The timetable for %(term)s is now published. Students can add your classes from the catalog.'
                '\n\n%(link)s') % {'term': term.name, 'link': link},
    ))
