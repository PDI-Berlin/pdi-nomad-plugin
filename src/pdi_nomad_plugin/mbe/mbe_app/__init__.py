from nomad.config.models.plugins import AppEntryPoint
from nomad.config.models.ui import (
    App,
    Column,
    Columns,
    FilterMenu,
    FilterMenus,
    Filters,
)

# Column keys for SubstrateMbe
_SUB_MBE = 'pdi_nomad_plugin.mbe.materials.SubstrateMbe'
_COL_NAME = f'data.name#{_SUB_MBE}'
_COL_DATE = f'data.delivery_date#{_SUB_MBE}'
_COL_LAB_ID = f'data.lab_id#{_SUB_MBE}'
_COL_DELIVERED = f'data.as_delivered#{_SUB_MBE}'
_COL_FRESH = f'data.fresh#{_SUB_MBE}'
_COL_PROCESSED = f'data.processed#{_SUB_MBE}'
_COL_GROWN = f'data.grown#{_SUB_MBE}'
_COL_ORIENT = f'data.crystal_properties.orientation#{_SUB_MBE}'

substrateapp = AppEntryPoint(
    name='Substrates',
    description='Explore Substrates catalogue in PDi institute.',
    app=App(
        label='Substrates',
        path='substrateapp',
        category='PDI',
        columns=Columns(
            selected=[
                _COL_NAME,
                _COL_DATE,
                _COL_LAB_ID,
                _COL_DELIVERED,
                _COL_FRESH,
                _COL_PROCESSED,
                _COL_GROWN,
                _COL_ORIENT,
            ],
            options={
                _COL_NAME: Column(),
                _COL_DATE: Column(),
                _COL_LAB_ID: Column(),
                _COL_DELIVERED: Column(),
                _COL_FRESH: Column(),
                _COL_PROCESSED: Column(),
                _COL_GROWN: Column(),
                _COL_ORIENT: Column(),
                # 'data.geometry.width#nomad_ikz_plugin.movpe.schema.SubstrateMovpe':
                #     Column(label='Width', unit='mm'),
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
