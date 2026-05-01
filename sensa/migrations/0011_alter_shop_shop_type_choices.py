from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sensa", "0010_dailyentry_buying_value_dailyentry_expired_value"),
    ]

    operations = [
        migrations.AlterField(
            model_name="shop",
            name="shop_type",
            field=models.CharField(
                choices=[
                    ("restaurant", "Restaurant"),
                    ("retail", "Retail"),
                    ("bar", "Bar"),
                    ("rooms", "Rooms"),
                    ("other", "Other"),
                ],
                default="retail",
                max_length=20,
            ),
        ),
    ]