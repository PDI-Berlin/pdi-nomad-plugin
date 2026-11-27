from nomad.config.models.plugins import DashboardEntryPoint


class ProcessingDashboardEntryPoint(DashboardEntryPoint):
    def load(self):
        from pdi_nomad_plugin.mbe.processing.app import app

        return app


processing = ProcessingDashboardEntryPoint(
    name='Processing',
    description='Apply processes to substrates and samples.',
    id_url_safe='processing',
    launch_modes=['embedded', 'tab'],
)
