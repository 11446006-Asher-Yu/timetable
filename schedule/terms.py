"""個人課表的學期：每門課屬於一個學期，課表一次顯示一個學期。"""

from django.db.models import Q

from scheduling.models import Term, default_term


def selected_term(request):
    """課表要顯示的學期：網址 ?term= 優先，否則用預設學期（沒有任何學期時為 None）。"""
    term_id = request.GET.get('term', '')
    term = Term.objects.filter(pk=term_id).first() if term_id.isdigit() else None
    return term or default_term()


def courses_in_term(owner, term):
    courses = owner.courses.all()
    if term is None:
        return courses
    # 還沒分到學期的課（先新增課程、後來才建立學期）顯示在預設學期
    if term == default_term():
        return courses.filter(Q(term=term) | Q(term__isnull=True))
    return courses.filter(term=term)
