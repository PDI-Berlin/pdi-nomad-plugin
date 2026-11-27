from nomad.config.models.plugins import DashboardEntryPoint


class NewMbeExperimentDashboardEntryPoint(DashboardEntryPoint):
    def load(self):
        from pdi_nomad_plugin.mbe.new_mbe_experiment.app import app

        return app


new_mbe_experiment = NewMbeExperimentDashboardEntryPoint(
    name='New MBE Experiment',
    description='Create a new MBE growth run and assign holder positions.',
    id_url_safe='new-mbe-experiment',
    launch_modes=['embedded', 'tab'],
)
