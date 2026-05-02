# Generated migration for Long/Short trading support

from django.db import migrations, models
import django.db.models.deletion


def migrate_existing_trades(apps, schema_editor):
    """
    Migrate existing trades to the new schema using bulk operations.
    No N+1 loops - all updates use bulk update() or RunSQL.
    """
    Trade = apps.get_model('api', 'Trade')
    
    # Step 1: Set all existing trades to spot, closed, with default values
    Trade.objects.all().update(
        position_type='spot',
        leverage=1.0,
        is_open=False,
        funding_fees=0.0
    )
    
    # Step 2: Copy buy_price to entry_price using F() expression
    from django.db.models import F
    Trade.objects.filter(buy_price__isnull=False).update(entry_price=F('buy_price'))
    
    # Step 3: Copy sell_price to exit_price using F() expression
    Trade.objects.filter(sell_price__isnull=False).update(exit_price=F('sell_price'))
    
    # Step 4: Calculate collateral = quantity × entry_price for spot trades
    # Use raw SQL for multiplication since F() expressions with multiplication
    # can be database-specific
    db_alias = schema_editor.connection.alias
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            UPDATE trade 
            SET collateral = quantity * entry_price 
            WHERE entry_price IS NOT NULL AND position_type = 'spot'
        """)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_emotiontag_user_alter_emotiontag_name_and_more'),
    ]

    operations = [
        # Step 1: Add new fields with null/default values
        migrations.AddField(
            model_name='trade',
            name='position_type',
            field=models.CharField(
                choices=[('spot', 'Spot'), ('long', 'Long'), ('short', 'Short')],
                default='spot',
                max_length=10
            ),
        ),
        migrations.AddField(
            model_name='trade',
            name='leverage',
            field=models.FloatField(default=1.0),
        ),
        migrations.AddField(
            model_name='trade',
            name='entry_price',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='trade',
            name='exit_price',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='trade',
            name='collateral',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='trade',
            name='liquidation_price',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='trade',
            name='funding_fees',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='trade',
            name='is_open',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='trade',
            name='close_date',
            field=models.DateTimeField(blank=True, null=True),
        ),
        
        # Step 2: Migrate existing data using bulk operations
        migrations.RunPython(migrate_existing_trades, reverse_code=migrations.RunPython.noop),
        
        # Step 3: Create FundingFeeLog table
        migrations.CreateModel(
            name='FundingFeeLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fee_amount', models.FloatField()),
                ('fee_rate', models.FloatField()),
                ('timestamp', models.DateTimeField()),
                ('trade', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='funding_logs', to='api.trade')),
            ],
            options={
                'db_table': 'funding_fee_log',
                'ordering': ['-timestamp'],
            },
        ),
    ]
