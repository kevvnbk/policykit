# Introduces BasePolicy as the shared parent of Policy (legacy 5-stage
# code-block policies) and GeneratedPolicy (event-driven script policies),
# which become siblings instead of GeneratedPolicy being an MTI child of
# Policy.
#
#   1. Create policyengine_basepolicy.
#   2. Backfill one basepolicy row per existing policyengine_policy row,
#      REUSING the same id (this is what makes every other step below a
#      constraint/column change rather than a data copy -- all the
#      downstream foreign keys keep their existing integer values).
#   3. Retarget every column that references policyengine_policy's rows
#      and will survive the restructure (Proposal.policy, the 9
#      constitution tables -> basepolicy; PolicyStoreEntry.policy,
#      ScheduledCallback.policy -> generatedpolicy) BEFORE touching
#      policyengine_policy itself. This has to come first: once the
#      "fake Policy" rows for GeneratedPolicy are deleted in step 4, any
#      FK still pointing at policyengine_policy for one of those ids would
#      break.
#   4. Detach GeneratedPolicy from policyengine_policy: drop its old
#      policy_ptr_id FK, delete the now-redundant "fake Policy" rows it was
#      sharing with policyengine_policy under MTI, then rename
#      policy_ptr_id to basepolicy_ptr_id. (The ScheduledCallback/
#      PolicyStoreEntry constraints added in step 3 were pointed at the
#      pre-rename column name; Postgres follows column renames in FK
#      constraints automatically, so they keep working.)
#   5. Re-point policyengine_policy's own PK (id -> basepolicy_ptr_id) at
#      policyengine_basepolicy, and drop the columns that moved there.
#
# Reverse is a no-op: this does not restore the pre-BasePolicy schema or
# data if unapplied. That's an intentional, called-out limitation (see the
# task report), not an oversight.

import django.db.models.deletion
from django.db import migrations, models

# (constraint_name, table, column) for every FK into policyengine_policy
# that survives the restructure pointing somewhere else. Pulled from `\d
# policyengine_policy` on the real dev database rather than guessed, since
# Postgres truncates/hashes these names.
_RETARGET_TO_BASEPOLICY = [
    ('policyengine_proposa_policy_id_832aa374_fk_policyeng', 'policyengine_proposal', 'policy_id'),
    ('constitution_policyk_policy_id_257b788d_fk_policyeng', 'constitution_policykitchangeplatformpolicy', 'policy_id'),
    ('constitution_policyk_policy_id_26ea0ca2_fk_policyeng', 'constitution_policykitchangeconstitutionpolicy', 'policy_id'),
    ('constitution_policyk_policy_id_ba49bed5_fk_policyeng', 'constitution_policykitchangetriggerpolicy', 'policy_id'),
    ('constitution_policyk_policy_id_a121e7df_fk_policyeng', 'constitution_policykitremoveplatformpolicy', 'policy_id'),
    ('constitution_policyk_policy_id_63885618_fk_policyeng', 'constitution_policykitremoveconstitutionpolicy', 'policy_id'),
    ('constitution_policyk_policy_id_d9f83734_fk_policyeng', 'constitution_policykitremovetriggerpolicy', 'policy_id'),
    ('constitution_policyk_policy_id_3994d8c0_fk_policyeng', 'constitution_policykitrecoverplatformpolicy', 'policy_id'),
    ('constitution_policyk_policy_id_809c5c28_fk_policyeng', 'constitution_policykitrecoverconstitutionpolicy', 'policy_id'),
    ('constitution_policyk_policy_id_a0a8c3d6_fk_policyeng', 'constitution_policykitrecovertriggerpolicy', 'policy_id'),
]

_RETARGET_TO_GENERATEDPOLICY = [
    ('policyengine_policys_policy_id_6bef8958_fk_policyeng', 'policyengine_policystoreentry', 'policy_id'),
    ('policyengine_schedul_policy_id_be157b63_fk_policyeng', 'policyengine_scheduledcallback', 'policy_id'),
]


def _content_type_ids(apps):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    policy_ct, _ = ContentType.objects.get_or_create(app_label='policyengine', model='policy')
    generatedpolicy_ct, _ = ContentType.objects.get_or_create(app_label='policyengine', model='generatedpolicy')
    return policy_ct.id, generatedpolicy_ct.id


def backfill_basepolicy_rows(apps, schema_editor):
    policy_ct_id, generatedpolicy_ct_id = _content_type_ids(apps)

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO policyengine_basepolicy
                (id, polymorphic_ctype_id, kind, name, description, is_active, modified_at, community_id)
            SELECT
                p.id,
                CASE WHEN gp.policy_ptr_id IS NOT NULL THEN %s ELSE %s END,
                p.kind, p.name, p.description, p.is_active, p.modified_at, p.community_id
            FROM policyengine_policy p
            LEFT JOIN policyengine_generatedpolicy gp ON gp.policy_ptr_id = p.id
            """,
            [generatedpolicy_ct_id, policy_ct_id],
        )
        cursor.execute(
            """
            INSERT INTO policyengine_basepolicy_action_types (basepolicy_id, actiontype_id)
            SELECT policy_id, actiontype_id FROM policyengine_policy_action_types
            """
        )
        cursor.execute(
            "SELECT setval('policyengine_basepolicy_id_seq', COALESCE((SELECT MAX(id) FROM policyengine_basepolicy), 1))"
        )


def retarget_dependent_fks(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for constraint_name, table, column in _RETARGET_TO_BASEPOLICY:
            cursor.execute(f'ALTER TABLE {table} DROP CONSTRAINT {constraint_name}')
            cursor.execute(
                f'ALTER TABLE {table} ADD CONSTRAINT {constraint_name}_bp '
                f'FOREIGN KEY ({column}) REFERENCES policyengine_basepolicy(id) DEFERRABLE INITIALLY DEFERRED'
            )
        for constraint_name, table, column in _RETARGET_TO_GENERATEDPOLICY:
            cursor.execute(f'ALTER TABLE {table} DROP CONSTRAINT {constraint_name}')
            cursor.execute(
                f'ALTER TABLE {table} ADD CONSTRAINT {constraint_name}_gp '
                f'FOREIGN KEY ({column}) REFERENCES policyengine_generatedpolicy(policy_ptr_id) DEFERRABLE INITIALLY DEFERRED'
            )


def detach_generatedpolicy(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            ALTER TABLE policyengine_generatedpolicy
                DROP CONSTRAINT policyengine_generat_policy_ptr_id_85935bf0_fk_policyeng
        """)
        # These rows only existed because GeneratedPolicy was an MTI child of
        # Policy. They're now fully represented by their basepolicy row
        # (backfilled above) plus their own generatedpolicy row. Everything
        # that referenced them was already retargeted off policyengine_policy
        # in retarget_dependent_fks(), above.
        cursor.execute("""
            DELETE FROM policyengine_policy_action_types
            WHERE policy_id IN (SELECT policy_ptr_id FROM policyengine_generatedpolicy)
        """)
        cursor.execute("""
            DELETE FROM policyengine_policy
            WHERE id IN (SELECT policy_ptr_id FROM policyengine_generatedpolicy)
        """)
        cursor.execute("""
            ALTER TABLE policyengine_generatedpolicy
                RENAME COLUMN policy_ptr_id TO basepolicy_ptr_id
        """)
        cursor.execute("""
            ALTER TABLE policyengine_generatedpolicy
                ADD CONSTRAINT policyengine_generatedpolicy_basepolicy_ptr_id_fk
                FOREIGN KEY (basepolicy_ptr_id) REFERENCES policyengine_basepolicy(id)
                DEFERRABLE INITIALLY DEFERRED
        """)


def retarget_policy_pk(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        # The DELETE in detach_generatedpolicy() leaves deferred FK-check
        # triggers on policyengine_policy (from the constraints that still
        # legitimately point at it -- PolicyVariable, bundled_policies)
        # pending until commit. Postgres refuses structural ALTER TABLE on a
        # table with pending trigger events, so force them to resolve now.
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute("""
            ALTER TABLE policyengine_policy
                DROP CONSTRAINT policyengine_policy_community_id_1e36b482_fk_policyeng
        """)
        cursor.execute("""
            ALTER TABLE policyengine_policy RENAME COLUMN id TO basepolicy_ptr_id
        """)
        cursor.execute("""
            ALTER TABLE policyengine_policy ALTER COLUMN basepolicy_ptr_id DROP DEFAULT
        """)
        cursor.execute("""
            ALTER TABLE policyengine_policy
                ADD CONSTRAINT policyengine_policy_basepolicy_ptr_id_fk
                FOREIGN KEY (basepolicy_ptr_id) REFERENCES policyengine_basepolicy(id)
                DEFERRABLE INITIALLY DEFERRED
        """)
        cursor.execute("ALTER TABLE policyengine_policy DROP COLUMN kind")
        cursor.execute("ALTER TABLE policyengine_policy DROP COLUMN community_id")
        cursor.execute("ALTER TABLE policyengine_policy DROP COLUMN name")
        cursor.execute("ALTER TABLE policyengine_policy DROP COLUMN description")
        cursor.execute("ALTER TABLE policyengine_policy DROP COLUMN is_active")
        cursor.execute("ALTER TABLE policyengine_policy DROP COLUMN modified_at")
        # Fully superseded by policyengine_basepolicy_action_types (all of
        # this table's rows were copied over in backfill_basepolicy_rows).
        cursor.execute("DROP TABLE policyengine_policy_action_types")


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('policyengine', '0027_script_runtime'),
        # Reaches into constitution's tables in retarget_dependent_fks() --
        # see the module docstring. Keeps the whole restructure inside one
        # transaction instead of splitting FK retargets across two apps'
        # migrations in a way that would reorder incorrectly.
        ('constitution', '0006_auto_20221120_1800'),
    ]

    operations = [
        migrations.CreateModel(
            name='BasePolicy',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('platform', 'platform'), ('constitution', 'constitution'), ('trigger', 'trigger')], max_length=30)),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('action_types', models.ManyToManyField(related_name='policy_set', to='policyengine.ActionType')),
                ('community', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='policyengine.community')),
                ('polymorphic_ctype', models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='polymorphic_policyengine.basepolicy_set+', to='contenttypes.contenttype')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
        ),
        migrations.RunPython(backfill_basepolicy_rows, migrations.RunPython.noop),
        migrations.RunPython(retarget_dependent_fks, migrations.RunPython.noop),
        migrations.RunPython(detach_generatedpolicy, migrations.RunPython.noop),
        migrations.RunPython(retarget_policy_pk, migrations.RunPython.noop),
        # State-only: recreate Policy/GeneratedPolicy so migration state
        # reports BasePolicy as their base (matching models.py). The
        # database is already correct after the RunPython steps above --
        # DeleteModel/CreateModel here touch bookkeeping only.
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name='GeneratedPolicy'),
                migrations.CreateModel(
                    name='GeneratedPolicy',
                    fields=[
                        ('basepolicy_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='policyengine.basepolicy')),
                        ('script_code', models.TextField(blank=True, default='')),
                        ('initialized', models.BooleanField(default=False)),
                        ('handler_registry', models.JSONField(blank=True, default=dict)),
                    ],
                    options={
                        'base_manager_name': 'objects',
                    },
                    bases=('policyengine.basepolicy',),
                ),
                migrations.DeleteModel(name='Policy'),
                migrations.CreateModel(
                    name='Policy',
                    fields=[
                        ('basepolicy_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='policyengine.basepolicy')),
                        ('filter', models.TextField(blank=True, default='')),
                        ('initialize', models.TextField(blank=True, default='')),
                        ('check', models.TextField(blank=True, default='')),
                        ('notify', models.TextField(blank=True, default='')),
                        ('success', models.TextField(blank=True, default='')),
                        ('fail', models.TextField(blank=True, default='')),
                        ('policy_template', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='policy', to='policyengine.policytemplate')),
                        ('bundled_policies', models.ManyToManyField(blank=True, related_name='member_of_bundle', to='policyengine.Policy')),
                    ],
                    options={
                        'base_manager_name': 'objects',
                    },
                    bases=('policyengine.basepolicy',),
                ),
            ],
        ),
        # State-only: the database side of all of these was already handled
        # by retarget_dependent_fks() above (policyengine's own two FKs) and
        # by constitution/0007 (the 9 constitution ones, state-only there
        # for the same reason).
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name='proposal',
                    name='policy',
                    field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, to='policyengine.basepolicy'),
                ),
                migrations.AlterField(
                    model_name='policystoreentry',
                    name='policy',
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='store_entries', to='policyengine.generatedpolicy'),
                ),
                migrations.AlterField(
                    model_name='scheduledcallback',
                    name='policy',
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='scheduled_callbacks', to='policyengine.generatedpolicy'),
                ),
            ],
        ),
    ]
