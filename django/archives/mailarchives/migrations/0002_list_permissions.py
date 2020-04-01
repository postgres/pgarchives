# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mailarchives', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ListSubscriber',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('username', models.CharField(max_length=30)),
            ],
            options={
                'db_table': 'listsubscribers',
            },
        ),
        migrations.AddField(
            model_name='list',
            name='subscriber_access',
            field=models.BooleanField(default=False, help_text='Subscribers can access contents (default is admins only)'),
        ),
        migrations.AddField(
            model_name='listsubscriber',
            name='list',
            field=models.ForeignKey(to='mailarchives.List', on_delete=models.CASCADE),
        ),
        migrations.AlterUniqueTogether(
            name='listsubscriber',
            unique_together=set([('list', 'username')]),
        ),
    ]
