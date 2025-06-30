from nomad.config.models.plugins import SchemaPackageEntryPoint
from pydantic import Field


class GeneralPackageEntryPoint(SchemaPackageEntryPoint):
    parameter: int = Field(0, description='Custom configuration parameter')

    def load(self):
        from pdi_nomad_plugin.general.schema import m_package

        return m_package


schema_entry_point = GeneralPackageEntryPoint(
    name='GeneralSchema',
    description='Schema package defined using the new plugin mechanism.',
)
