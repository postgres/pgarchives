# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Attachment',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('filename', models.CharField(max_length=1000)),
                ('contenttype', models.CharField(max_length=1000)),
            ],
            options={
                'ordering': ('id',),
                'db_table': 'attachments',
            },
        ),
        migrations.CreateModel(
            name='List',
            fields=[
                ('listid', models.IntegerField(serialize=False, primary_key=True)),
                ('listname', models.CharField(unique=True, max_length=200)),
                ('shortdesc', models.TextField()),
                ('description', models.TextField()),
                ('active', models.BooleanField()),
            ],
            options={
                'db_table': 'lists',
            },
        ),
        migrations.CreateModel(
            name='ListGroup',
            fields=[
                ('groupid', models.IntegerField(serialize=False, primary_key=True)),
                ('groupname', models.CharField(max_length=200)),
                ('sortkey', models.IntegerField()),
            ],
            options={
                'db_table': 'listgroups',
            },
        ),
        migrations.CreateModel(
            name='Message',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('threadid', models.IntegerField()),
                ('mailfrom', models.TextField(db_column='_from')),
                ('to', models.TextField(db_column='_to')),
                ('cc', models.TextField()),
                ('subject', models.TextField()),
                ('date', models.DateTimeField()),
                ('messageid', models.TextField()),
                ('bodytxt', models.TextField()),
                ('parentid', models.IntegerField()),
                ('has_attachment', models.BooleanField(default=False)),
                ('hiddenstatus', models.IntegerField(null=True)),
            ],
            options={
                'db_table': 'messages',
            },
        ),
        migrations.AddField(
            model_name='list',
            name='group',
            field=models.ForeignKey(to='mailarchives.ListGroup', db_column='groupid', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='attachment',
            name='message',
            field=models.ForeignKey(to='mailarchives.Message', db_column='message', on_delete=models.CASCADE),
        ),
    ]
