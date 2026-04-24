# Generated manually - creates all models not covered in migrations 0001-0005
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0005_alter_admin_profile_picture_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Location',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('code', models.CharField(blank=True, max_length=10, null=True, unique=True)),
                ('address', models.TextField(blank=True, null=True)),
                ('city', models.CharField(blank=True, max_length=50, null=True)),
                ('state', models.CharField(blank=True, max_length=50, null=True)),
                ('country', models.CharField(default='India', max_length=50)),
                ('zip_code', models.CharField(blank=True, max_length=20, null=True)),
                ('phone', models.CharField(blank=True, max_length=20, null=True)),
                ('email', models.EmailField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'hr_locations', 'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='Department',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('code', models.CharField(blank=True, max_length=10, null=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('head', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='headed_departments', to='hr.employee')),
            ],
            options={'db_table': 'hr_departments', 'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='Designation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=100)),
                ('code', models.CharField(blank=True, max_length=10, null=True, unique=True)),
                ('level', models.IntegerField(default=1, help_text='Hierarchy level (1 = entry level)')),
                ('description', models.TextField(blank=True, null=True)),
                ('min_salary', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('max_salary', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('department', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='designations', to='hr.department')),
            ],
            options={'db_table': 'hr_designations', 'ordering': ['department', 'level'], 'unique_together': {('title', 'department')}},
        ),
        migrations.CreateModel(
            name='Role',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'hr_roles', 'verbose_name': 'Role', 'verbose_name_plural': 'Roles', 'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='ProbationConfiguration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('probation_period_days', models.IntegerField(default=90, help_text='Default probation period in days')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'hr_probation_configuration', 'verbose_name_plural': 'Probation Configuration'},
        ),
        migrations.CreateModel(
            name='MessageCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'db_table': 'message_category'},
        ),
        migrations.CreateModel(
            name='MessageSubType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('is_active', models.BooleanField(default=True)),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subtypes', to='hr.messagecategory')),
            ],
            options={'db_table': 'message_subtype'},
        ),
        migrations.CreateModel(
            name='EmployeeWarning',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('employee_code', models.CharField(max_length=100)),
                ('message_category', models.CharField(max_length=255)),
                ('sub_type', models.CharField(max_length=255)),
                ('warning_date', models.DateField()),
                ('subject', models.CharField(max_length=255)),
                ('description', models.TextField()),
                ('issued_by', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'db_table': 'employee_warning'},
        ),
        migrations.CreateModel(
            name='YsMenuMaster',
            fields=[
                ('menu_id', models.AutoField(primary_key=True, serialize=False)),
                ('menu_name', models.CharField(max_length=45)),
                ('menu_icon', models.CharField(blank=True, max_length=200, null=True)),
                ('menu_id_name', models.CharField(blank=True, max_length=45, null=True)),
                ('menu_url', models.CharField(blank=True, max_length=100, null=True)),
                ('display_area_type', models.CharField(blank=True, max_length=1, null=True)),
                ('icon_bytes', models.BinaryField(blank=True, null=True)),
                ('seq', models.IntegerField(blank=True, null=True)),
                ('status', models.BooleanField(default=False)),
            ],
            options={'db_table': 'ys_menu_master', 'ordering': ['seq']},
        ),
        migrations.CreateModel(
            name='YsMenuLinkMaster',
            fields=[
                ('menu_link_id', models.AutoField(primary_key=True, serialize=False)),
                ('menu_link_name', models.CharField(max_length=45)),
                ('menu_link_icon', models.CharField(blank=True, max_length=200, null=True)),
                ('menu_link_url', models.CharField(blank=True, max_length=100, null=True)),
                ('menu_link_id_name', models.CharField(blank=True, max_length=45, null=True)),
                ('seq', models.IntegerField(blank=True, null=True)),
                ('status', models.IntegerField(default=1)),
                ('menu', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='hr.ysmenumaster')),
            ],
            options={'db_table': 'ys_menu_link_master', 'ordering': ['seq']},
        ),
        migrations.CreateModel(
            name='YsUserRoleMaster',
            fields=[
                ('userRoleId', models.AutoField(primary_key=True, serialize=False)),
                ('userRole', models.CharField(max_length=45)),
                ('isActive', models.BooleanField(default=True)),
            ],
            options={'db_table': 'ys_user_role_master', 'verbose_name': 'User Role', 'verbose_name_plural': 'User Roles'},
        ),
        migrations.CreateModel(
            name='AllowedDomain',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('domain', models.CharField(help_text="Enter domain like 'company.com' or '*.company.com' for subdomains", max_length=255, unique=True)),
                ('domain_type', models.CharField(choices=[('ALLOW', 'Allow'), ('BLOCK', 'Block')], default='ALLOW', max_length=10)),
                ('is_active', models.BooleanField(default=True)),
                ('description', models.TextField(blank=True, null=True, help_text='Optional description')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'hr_allowed_domains', 'verbose_name': 'Allowed Domain', 'verbose_name_plural': 'Allowed Domains', 'ordering': ['domain']},
        ),
        migrations.CreateModel(
            name='CelebrationWish',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.TextField()),
                ('wish_type', models.CharField(choices=[('birthday', 'Birthday'), ('work_anniversary', 'Work Anniversary'), ('marriage_anniversary', 'Marriage Anniversary')], max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('celebrant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='received_wishes', to='hr.employee')),
                ('wisher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sent_wishes', to='hr.employee')),
            ],
            options={'db_table': 'celebration_wishes', 'ordering': ['-created_at']},
        ),
    ]
