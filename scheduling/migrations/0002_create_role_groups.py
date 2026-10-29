from django.db import migrations

ROLE_GROUPS = ['Schedulers', 'Teachers']


def create_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    for name in ROLE_GROUPS:
        Group.objects.get_or_create(name=name)


def remove_groups(apps, schema_editor):
    apps.get_model('auth', 'Group').objects.filter(name__in=ROLE_GROUPS).delete()


class Migration(migrations.Migration):
    """建立排課人員、老師兩個角色群組；管理員在後台把帳號加入 Schedulers 即成為排課人員。"""

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('scheduling', '0001_initial'),
    ]

    operations = [migrations.RunPython(create_groups, remove_groups)]
