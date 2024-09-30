from nomad.config.models.plugins import AppEntryPoint
from nomad.config.models.ui import (
    App,
    Column,
    Columns,
    FilterMenu,
    FilterMenus,
    Filters,
)

substrateapp = AppEntryPoint(
    name='Substrates',
    description='Explore Substrates catalogue in PDi institute.',
    app=App(
        label='Substrates',
        path='substrateapp',
        category='PDI',
        columns=Columns(
            selected=[
                'data.name#pdi_nomad_plugin.mbe.materials.SubstrateMbe',
                'data.delivery_date#pdi_nomad_plugin.mbe.materials.SubstrateMbe',
                'data.lab_id#pdi_nomad_plugin.mbe.materials.SubstrateMbe',
                'data.as_delivered#pdi_nomad_plugin.mbe.materials.SubstrateMbe',
                'data.fresh#pdi_nomad_plugin.mbe.materials.SubstrateMbe',
                'data.processed#pdi_nomad_plugin.mbe.materials.SubstrateMbe',
                'data.grown#pdi_nomad_plugin.mbe.materials.SubstrateMbe',
                'data.crystal_properties.orientation#pdi_nomad_plugin.mbe.materials.SubstrateMbe',
            ],
            options={
                'data.name#pdi_nomad_plugin.mbe.materials.SubstrateMbe': Column(),
                'data.delivery_date#pdi_nomad_plugin.mbe.materials.SubstrateMbe': Column(),
                'data.lab_id#pdi_nomad_plugin.mbe.materials.SubstrateMbe': Column(),
                'data.as_delivered#pdi_nomad_plugin.mbe.materials.SubstrateMbe': Column(),
                'data.fresh#pdi_nomad_plugin.mbe.materials.SubstrateMbe': Column(),
                'data.processed#pdi_nomad_plugin.mbe.materials.SubstrateMbe': Column(),
                'data.grown#pdi_nomad_plugin.mbe.materials.SubstrateMbe': Column(),
                'data.crystal_properties.orientation#pdi_nomad_plugin.mbe.materials.SubstrateMbe': Column(),
                #     'data.geometry.width#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(
                #         label='Width', unit='mm'
                #     ),
            },
        ),
        filter_menus=FilterMenus(
            options={
                'material': FilterMenu(label='Material'),
                'eln': FilterMenu(label='Electronic Lab Notebook'),
                'custom_quantities': FilterMenu(label='User Defined Quantities'),
                'author': FilterMenu(label='Author / Origin / Dataset'),
                'metadata': FilterMenu(label='Visibility / IDs / Schema'),
            }
        ),
        filters=Filters(
            include=['*#pdi_nomad_plugin.mbe.materials.SubstrateMbe'],
        ),
        filters_locked={
            'section_defs.definition_qualified_name': [
                'pdi_nomad_plugin.mbe.materials.SubstrateMbe',
            ],
        },
    ),
)
