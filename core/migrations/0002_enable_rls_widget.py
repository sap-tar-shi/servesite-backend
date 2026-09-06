from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),  # confirm this matches your actual prior migration name
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE core_widget ENABLE ROW LEVEL SECURITY;
                ALTER TABLE core_widget FORCE ROW LEVEL SECURITY;

                CREATE POLICY tenant_isolation_widget ON core_widget
                    USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
            """,
            reverse_sql="""
                DROP POLICY IF EXISTS tenant_isolation_widget ON core_widget;
                ALTER TABLE core_widget DISABLE ROW LEVEL SECURITY;
            """,
        ),
    ]