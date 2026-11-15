import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MediaAsset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_id', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('kind', models.CharField(choices=[('product_image', 'Product image'), ('category_image', 'Category image'), ('banner', 'Banner'), ('logo', 'Logo'), ('reference_image', 'Customer reference image'), ('other', 'Other')], db_index=True, default='other', max_length=30)),
                ('visibility', models.CharField(choices=[('public', 'Public'), ('private', 'Private')], db_index=True, default='public', max_length=10)),
                ('status', models.CharField(choices=[('ready', 'Ready'), ('processing', 'Processing'), ('failed', 'Failed')], db_index=True, default='ready', max_length=12)),
                ('object_key', models.CharField(max_length=500)),
                ('thumbnail_key', models.CharField(blank=True, max_length=500)),
                ('original_name', models.CharField(max_length=255)),
                ('mime_type', models.CharField(max_length=100)),
                ('size_bytes', models.PositiveBigIntegerField(default=0)),
                ('width', models.PositiveBigIntegerField(blank=True, null=True)),
                ('height', models.PositiveBigIntegerField(blank=True, null=True)),
                ('alt_text', models.CharField(blank=True, max_length=255)),
                ('related_object_type', models.CharField(blank=True, max_length=80)),
                ('related_object_id', models.CharField(blank=True, max_length=64)),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='media_assets', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'media_asset',
                'ordering': ['-created_at', '-id'],
                'indexes': [models.Index(fields=['related_object_type', 'related_object_id'], name='media_related_idx')],
            },
        ),
    ]
