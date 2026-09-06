from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_enable_rls_widget"),  # confirm this matches your actual previous migration name
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                DROP POLICY IF EXISTS tenant_isolation_widget ON core_widget;

                CREATE POLICY tenant_isolation_widget ON core_widget
                    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
            """,
            reverse_sql="""
                DROP POLICY IF EXISTS tenant_isolation_widget ON core_widget;
                CREATE POLICY tenant_isolation_widget ON core_widget
                    USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
            """,
        ),
    ]
