from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cmsplugin_cascade', '0019_verbose_table_names'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cascadeclipboard', name='data',
            field=models.JSONField(blank=True, default=dict, null=True),
        ),
        migrations.AlterField(
            model_name='cascadeelement', name='glossary',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='cascadepage', name='glossary',
            field=models.JSONField(blank=True, default=dict, help_text='Store for arbitrary page data.'),
        ),
        migrations.AlterField(
            model_name='cascadepage', name='settings',
            field=models.JSONField(blank=True, default=dict, help_text='User editable settings for this page.'),
        ),
        migrations.AlterField(
            model_name='iconfont', name='config_data', field=models.JSONField(),
        ),
        migrations.AlterField(
            model_name='inlinecascadeelement', name='glossary',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='pluginextrafields', name='css_classes',
            field=models.JSONField(blank=True, default=dict, null=True),
        ),
        migrations.AlterField(
            model_name='pluginextrafields', name='inline_styles',
            field=models.JSONField(blank=True, default=dict, null=True),
        ),
        migrations.AlterField(
            model_name='sharedglossary', name='glossary',
            field=models.JSONField(blank=True, default=dict, null=True),
        ),
        migrations.AlterField(
            model_name='sortableinlinecascadeelement', name='glossary',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
