from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('label_stations', '0011_station_data_pushed_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='operator',
            name='station',
            field=models.ForeignKey(blank=True, help_text='Пусто = доступен на всех станциях', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='operators', to='label_stations.labelsstations', verbose_name='Станция'),
        ),
        migrations.CreateModel(
            name='MasterDataChange',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=50, unique=True)),
                ('changed_at', models.DateTimeField()),
            ],
        ),
    ]
