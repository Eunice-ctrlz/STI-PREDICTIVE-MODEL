from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("geospatial", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS postgis",
            reverse_sql="",
        ),
    ]
