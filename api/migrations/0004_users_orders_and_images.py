import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def clear_anonymous_carts(apps, schema_editor):
    # Los carritos antiguos estaban ligados al navegador; desde ahora pertenecen a usuarios.
    apps.get_model('api', 'Cart').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0003_store_product_cart_cartitem_and_more'),
    ]

    operations = [
        migrations.RemoveConstraint(model_name='cart', name='one_cart_per_session_store'),
        migrations.AddField(model_name='store', name='image_url', field=models.URLField(blank=True, verbose_name='imagen')),
        migrations.AddField(model_name='product', name='image_url', field=models.URLField(blank=True, verbose_name='imagen')),
        migrations.AddField(
            model_name='cart', name='user',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='carts', to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(clear_anonymous_carts, migrations.RunPython.noop),
        migrations.RemoveField(model_name='cart', name='session_key'),
        migrations.AlterField(
            model_name='cart', name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='carts', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddConstraint(
            model_name='cart',
            constraint=models.UniqueConstraint(fields=('user', 'store'), name='one_cart_per_user_store'),
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total', models.DecimalField(decimal_places=0, max_digits=12)),
                ('status', models.CharField(choices=[('completed', 'Completada'), ('cancelled', 'Cancelada')], default='completed', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='orders', to='api.store')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='orders', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('-created_at',)},
        ),
        migrations.CreateModel(
            name='OrderItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('product_name', models.CharField(max_length=140)),
                ('unit_price', models.DecimalField(decimal_places=0, max_digits=10)),
                ('quantity', models.PositiveIntegerField()),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='api.order')),
            ],
        ),
    ]
