import yaml
from nomad.config.models.plugins import AppEntryPoint
from nomad.config.models.ui import (
    App,
    Column,
    Columns,
    Dashboard,
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
            ],
            options={
                _COL_NAME: Column(),
                _COL_DATE: Column(),
                _COL_LAB_ID: Column(),
                _COL_DELIVERED: Column(),
                _COL_FRESH: Column(),
                _COL_PROCESSED: Column(),
                _COL_GROWN: Column(),
                # 'data.geometry.width#nomad_ikz_plugin.movpe.schema.SubstrateMovpe':
                #     Column(label='Width', unit='mm'),
            },
        ),
        dashboard=Dashboard(
            widgets=yaml.safe_load("""
- type: terms
  show_input: true
  scale: linear
  search_quantity: data.grown#pdi_nomad_plugin.mbe.materials.SubstrateMbe
  title: grown
  layout:
    xxl:
      minH: 3
      minW: 3
      h: 9
      w: 6
      y: 0
      x: 0
    xl:
      minH: 3
      minW: 3
      h: 4
      w: 6
      y: 0
      x: 0
    lg:
      minH: 3
      minW: 3
      h: 4
      w: 5
      y: 0
      x: 0
    md:
      minH: 3
      minW: 3
      h: 9
      w: 6
      y: 0
      x: 12
    sm:
      minH: 3
      minW: 3
      h: 3
      w: 3
      y: 9
      x: 9
- type: periodic_table
  scale: linear
  search_quantity: results.material.elements
  title: elements
  layout:
    xxl:
      minH: 3
      minW: 3
      h: 9
      w: 12
      y: 0
      x: 6
    xl:
      minH: 3
      minW: 3
      h: 8
      w: 14
      y: 0
      x: 12
    lg:
      minH: 3
      minW: 3
      h: 7
      w: 13
      y: 0
      x: 10
    md:
      minH: 3
      minW: 3
      h: 9
      w: 12
      y: 0
      x: 0
    sm:
      minH: 3
      minW: 3
      h: 9
      w: 12
      y: 0
      x: 0
- type: terms
  show_input: true
  scale: linear
  search_quantity: data.processed#pdi_nomad_plugin.mbe.materials.SubstrateMbe
  title: processed
  layout:
    xxl:
      minH: 3
      minW: 3
      h: 9
      w: 6
      y: 0
      x: 18
    xl:
      minH: 3
      minW: 3
      h: 4
      w: 6
      y: 0
      x: 6
    lg:
      minH: 3
      minW: 3
      h: 4
      w: 5
      y: 0
      x: 5
    md:
      minH: 3
      minW: 3
      h: 9
      w: 6
      y: 9
      x: 0
    sm:
      minH: 3
      minW: 3
      h: 3
      w: 3
      y: 9
      x: 6
- type: terms
  show_input: true
  scale: linear
  search_quantity: data.fresh#pdi_nomad_plugin.mbe.materials.SubstrateMbe
  title: fresh
  layout:
    xxl:
      minH: 3
      minW: 3
      h: 9
      w: 6
      y: 0
      x: 24
    xl:
      minH: 3
      minW: 3
      h: 4
      w: 6
      y: 4
      x: 0
    lg:
      minH: 3
      minW: 3
      h: 3
      w: 5
      y: 4
      x: 0
    md:
      minH: 3
      minW: 3
      h: 9
      w: 6
      y: 9
      x: 6
    sm:
      minH: 3
      minW: 3
      h: 3
      w: 3
      y: 9
      x: 3
- type: terms
  show_input: true
  scale: linear
  search_quantity: data.as_delivered#pdi_nomad_plugin.mbe.materials.SubstrateMbe
  title: as-delivered
  layout:
    xxl:
      minH: 3
      minW: 3
      h: 9
      w: 6
      y: 0
      x: 30
    xl:
      minH: 3
      minW: 3
      h: 4
      w: 6
      y: 4
      x: 6
    lg:
      minH: 3
      minW: 3
      h: 3
      w: 5
      y: 4
      x: 5
    md:
      minH: 3
      minW: 3
      h: 9
      w: 6
      y: 9
      x: 12
    sm:
      minH: 3
      minW: 3
      h: 3
      w: 3
      y: 9
      x: 0
            """)
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
