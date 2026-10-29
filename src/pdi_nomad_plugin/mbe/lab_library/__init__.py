from nomad.config.models.plugins import DashboardEntryPoint


class LabLibraryDashboardEntryPoint(DashboardEntryPoint):
    def load(self):
        from pdi_nomad_plugin.mbe.lab_library.app import app

        return app


lab_library = LabLibraryDashboardEntryPoint(
    name='Lab Library',
    description='Manage reusable laboratory recipes, holders, and inserts.',
    id_url_safe='lab-library',
    launch_modes=['embedded', 'tab'],
)
