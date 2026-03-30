from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sensa", "0009_fix_userprofile_fk"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailyentry",
            name="buying_value",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Cost price value of goods sold for the day.",
                max_digits=14,
                validators=[MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AddField(
            model_name="dailyentry",
            name="expired_value",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Cost value of expired or wasted goods for the day.",
                max_digits=14,
                validators=[MinValueValidator(Decimal("0.00"))],
            ),
        ),
    ]
