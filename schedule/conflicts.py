"""跨課程衝堂：新增／修改課程時的檢查，以及課表上衝堂課程的並排位置。"""

from django.utils.translation import gettext

from .models import CourseTime, describe_time


def overlaps(weekday_a, start_a, end_a, weekday_b, start_b, end_b):
    """兩個時段是否同一天且節次有重疊（節次以編號表示，含頭尾）。"""
    return weekday_a == weekday_b and start_a <= end_b and start_b <= end_a


def find_conflicts(owner, new_times, exclude_course=None):
    """找出 new_times 與使用者其他課程的衝堂。

    new_times 為 (星期, 開始節次編號, 結束節次編號) 的清單；回傳給使用者看的說明文字。
    """
    others = CourseTime.objects.filter(course__owner=owner).select_related(
        'course', 'start_period', 'end_period'
    )
    if exclude_course is not None and exclude_course.pk:
        others = others.exclude(course=exclude_course)

    messages = []
    for weekday, start, end in new_times:
        for other in others:
            if overlaps(weekday, start, end, other.weekday, other.start_period.number, other.end_period.number):
                messages.append(gettext('%(time)s overlaps with “%(course)s” (%(other)s)') % {
                    'time': describe_time(weekday, start, end),
                    'course': other.course.name,
                    'other': other,
                })
    return messages


def assign_lanes(blocks):
    """同一天重疊的課程方塊左右並排：替每個方塊加上 lane（第幾欄）、lanes（共幾欄）、conflict。

    先把互相重疊（含間接重疊）的方塊分成一群，群內依開始節次放進第一個空出來的欄位。
    """
    for block in blocks:
        block.update(lane=0, lanes=1, conflict=False)

    def span(block):
        return block['time'].start_period.number, block['time'].end_period.number

    by_day = {}
    for block in blocks:
        by_day.setdefault(block['time'].weekday, []).append(block)

    for day_blocks in by_day.values():
        day_blocks.sort(key=span)
        group, group_end = [], 0
        for block in day_blocks + [None]:  # 結尾放 None，讓最後一群也能結算
            start = span(block)[0] if block else None
            if group and (block is None or start > group_end):
                _place_group(group, span)
                group, group_end = [], 0
            if block is not None:
                group.append(block)
                group_end = max(group_end, span(block)[1])


def _place_group(group, span):
    lane_ends = []  # 每一欄目前最後一堂課的結束節次
    for block in group:
        start, end = span(block)
        for lane, lane_end in enumerate(lane_ends):
            if lane_end < start:
                lane_ends[lane] = end
                block['lane'] = lane
                break
        else:
            block['lane'] = len(lane_ends)
            lane_ends.append(end)
    if len(group) > 1:
        for block in group:
            block['lanes'] = len(lane_ends)
            block['conflict'] = True
