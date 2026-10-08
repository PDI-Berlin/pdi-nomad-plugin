from nomad.config.models.plugins import DashboardEntryPoint


class SubstrateIntakeDashboardEntryPoint(DashboardEntryPoint):
    def load(self):
        from pdi_nomad_plugin.mbe.substrate_intake.app import app

        return app


substrate_intake = SubstrateIntakeDashboardEntryPoint(
    name='Substrate Intake',
    description='Create substrate batches and child substrate entries.',
    id_url_safe='substrate-intake',
    launch_modes=['embedded', 'tab'],
)
