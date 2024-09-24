import yaml
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
                'data.name#pdi_nomad_plugin.mbe.processes.SubstrateMbe',
                'data.delivery_date#pdi_nomad_plugin.mbe.processes.SubstrateMbe',
                'data.crystal_id#pdi_nomad_plugin.mbe.processes.SubstrateMbe',
                'data.charge_id#pdi_nomad_plugin.mbe.processes.SubstrateMbe',
                'data.lab_id#pdi_nomad_plugin.mbe.processes.SubstrateMbe',
                'data.crystal_properties.orientation#pdi_nomad_plugin.mbe.processes.SubstrateMbe',
            ],
            # options={
            #     'data.name#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(),
            #     'data.supplier#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(
            #         label='Supplier ID'
            #     ),
            #     'data.datetime#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(
            #         label='Delivery Date'
            #     ),
            #     'data.lab_id#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(
            #         label='Substrate ID'
            #     ),
            #     'data.tags#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(
            #         label='Substrate Box'
            #     ),
            #     'data.description#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(
            #         label='Comment'
            #     ),
            #     'data.etching#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(),
            #     'data.annealing#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(),
            #     'data.re_etching#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(),
            #     'data.re_annealing#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(),
            #     'data.epi_ready#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(),
            #     'data.geometry.length#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(
            #         label='Length', unit='mm'
            #     ),
            #     'data.geometry.width#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(
            #         label='Width', unit='mm'
            #     ),
            #     'data.dopants.elements#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(),
            #     'data.dopants.doping_level#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(),
            #     'data.crystal_properties.orientation#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(),
            #     'data.crystal_properties.miscut.angle#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(
            #         label='Miscut Angle'
            #     ),
            #     'data.crystal_properties.miscut.orientation#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(
            #         label='Miscut Orientation'
            #     ),
            #     'data.electronic_properties.conductivity_type#nomad_ikz_plugin.movpe.schema.SubstrateMovpe': Column(),
            # },
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
            include=['*#pdi_nomad_plugin.mbe.processes.SubstrateMbe'],
        ),
        filters_locked={
            'section_defs.definition_qualified_name': [
                'pdi_nomad_plugin.mbe.processes.SubstrateMbe',
            ],
        },
    ),
)
