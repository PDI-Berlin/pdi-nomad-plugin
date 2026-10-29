from nomad.config.models.plugins import DashboardEntryPoint


class PDILabDashboardEntryPoint(DashboardEntryPoint):
    def load(self):
        from pdi_nomad_plugin.mbe.pdi_lab.app import app

        return app


pdi_lab = PDILabDashboardEntryPoint(
    name='PDI Lab',
    description='Unified PDI laboratory workflow workspace.',
    id_url_safe='pdi-lab',
    launch_modes=['embedded', 'tab'],
)
