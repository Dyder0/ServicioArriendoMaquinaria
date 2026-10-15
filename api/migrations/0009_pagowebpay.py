from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0008_unidadflota_itemcontrato_unidades_asignadas'),
    ]

    operations = [
        migrations.CreateModel(
            name='PagoWebpay',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('buy_order', models.CharField(max_length=26, unique=True)),
                ('session_id', models.CharField(max_length=61)),
                ('monto', models.DecimalField(decimal_places=0, max_digits=14)),
                ('token', models.CharField(blank=True, max_length=64, null=True, unique=True)),
                ('url_pago', models.URLField(blank=True, max_length=500)),
                ('estado', models.CharField(choices=[('INICIADO', 'Iniciado'), ('AUTORIZADO', 'Autorizado'), ('RECHAZADO', 'Rechazado'), ('ANULADO', 'Anulado por el usuario'), ('REEMBOLSADO', 'Reembolsado'), ('ERROR', 'Error')], db_index=True, default='INICIADO', max_length=20)),
                ('response_code', models.IntegerField(blank=True, null=True)),
                ('authorization_code', models.CharField(blank=True, max_length=20)),
                ('payment_type_code', models.CharField(blank=True, max_length=10)),
                ('card_last4', models.CharField(blank=True, max_length=4)),
                ('respuesta', models.JSONField(blank=True, default=dict)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('contrato', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='pago_webpay', to='api.contrato')),
            ],
            options={
                'verbose_name': 'pago Webpay',
                'verbose_name_plural': 'pagos Webpay',
                'ordering': ('-creado_en',),
            },
        ),
    ]
