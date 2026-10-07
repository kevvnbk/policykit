# State-only: the database side of this retarget (dropping/adding the FK
# constraints on these 9 tables, pointing them at policyengine_basepolicy
# instead of policyengine_policy) is done by
# policyengine/migrations/0028_basepolicy.py's retarget_dependent_fks(),
# which has to run before policyengine_policy's stale GeneratedPolicy rows
# are deleted -- see that migration's module docstring. This migration
# just brings constitution's own migration state in line with models.py.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('policyengine', '0028_basepolicy'),
        ('constitution', '0006_auto_20221120_1800'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name='policykitchangeconstitutionpolicy',
                    name='policy',
                    field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='policyengine.basepolicy'),
                ),
                migrations.AlterField(
                    model_name='policykitchangeplatformpolicy',
                    name='policy',
                    field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='policyengine.basepolicy'),
                ),
                migrations.AlterField(
                    model_name='policykitchangetriggerpolicy',
                    name='policy',
                    field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='policyengine.basepolicy'),
                ),
                migrations.AlterField(
                    model_name='policykitrecoverconstitutionpolicy',
                    name='policy',
                    field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='policyengine.basepolicy'),
                ),
                migrations.AlterField(
                    model_name='policykitrecoverplatformpolicy',
                    name='policy',
                    field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='policyengine.basepolicy'),
                ),
                migrations.AlterField(
                    model_name='policykitrecovertriggerpolicy',
                    name='policy',
                    field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='policyengine.basepolicy'),
                ),
                migrations.AlterField(
                    model_name='policykitremoveconstitutionpolicy',
                    name='policy',
                    field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='policyengine.basepolicy'),
                ),
                migrations.AlterField(
                    model_name='policykitremoveplatformpolicy',
                    name='policy',
                    field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='policyengine.basepolicy'),
                ),
                migrations.AlterField(
                    model_name='policykitremovetriggerpolicy',
                    name='policy',
                    field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='policyengine.basepolicy'),
                ),
            ],
        ),
    ]
