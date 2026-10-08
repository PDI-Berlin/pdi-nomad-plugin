from nomad.config.models.plugins import AppEntryPoint
from nomad.config.models.ui import (
    App,
    Column,
    Menu,
    MenuItemTerms,
    SearchQuantities,
)

# Search quantity keys for SubstrateMbe
_SUB_MBE = 'pdi_nomad_plugin.mbe.materials.SubstrateMbe'
_COL_LAB_ID = f'data.lab_id#{_SUB_MBE}'
_COL_MATERIAL = f'data.crystal_id#{_SUB_MBE}'
_COL_ORIENTATION = f'data.surface_orientation_label#{_SUB_MBE}'
_COL_OFFCUT = f'data.offcut_label#{_SUB_MBE}'
_COL_TOWARDS = f'data.offcut_direction#{_SUB_MBE}'
_COL_DELIVERED = f'data.as_delivered#{_SUB_MBE}'
_COL_PROCESSED = f'data.processed#{_SUB_MBE}'
_COL_GROWN = f'data.grown#{_SUB_MBE}'

substrateapp = AppEntryPoint(
    name='Substrates',
    description='Browse and filter the PDI substrate catalogue.',
    app=App(
        label='Substrates',
        path='substrateapp',
        category='PDI',
        columns=[
            Column(
                search_quantity=_COL_LAB_ID,
                label='Substrate',
                selected=True,
            ),
            Column(
                search_quantity=_COL_ORIENTATION,
                label='Orientation',
                selected=True,
            ),
            Column(
                search_quantity=_COL_OFFCUT,
                label='Offcut',
                selected=True,
            ),
            Column(
                search_quantity=_COL_TOWARDS,
                label='Towards',
                selected=True,
            ),
            Column(
                search_quantity=_COL_DELIVERED,
                label='As delivered',
                selected=True,
            ),
            Column(
                search_quantity=_COL_PROCESSED,
                label='Processed',
                selected=True,
            ),
            Column(
                search_quantity=_COL_GROWN,
                label='Grown',
                selected=True,
            ),
        ],
        menu=Menu(
            title='Filters',
            size='sm',
            items=[
                Menu(
                    title='Substrate',
                    items=[
                        MenuItemTerms(
                            search_quantity=_COL_LAB_ID,
                            options=50,
                            show_input=True,
                            show_statistics=False,
                        ),
                    ],
                ),
                Menu(
                    title='Material',
                    items=[
                        MenuItemTerms(
                            search_quantity=_COL_MATERIAL,
                            options=20,
                            show_input=True,
                            show_statistics=False,
                        ),
                    ],
                ),
                Menu(
                    title='Orientation',
                    items=[
                        MenuItemTerms(
                            search_quantity=_COL_ORIENTATION,
                            options=20,
                            show_input=True,
                            show_statistics=False,
                        ),
                    ],
                ),
                Menu(
                    title='Offcut',
                    items=[
                        MenuItemTerms(
                            search_quantity=_COL_OFFCUT,
                            options=20,
                            show_input=True,
                            show_statistics=False,
                        ),
                    ],
                ),
                Menu(
                    title='Towards',
                    items=[
                        MenuItemTerms(
                            search_quantity=_COL_TOWARDS,
                            options=20,
                            show_input=True,
                            show_statistics=False,
                        ),
                    ],
                ),
                Menu(
                    title='Status',
                    items=[
                        MenuItemTerms(
                            title='As delivered',
                            search_quantity=_COL_DELIVERED,
                            options=2,
                            show_input=False,
                            show_statistics=False,
                        ),
                        MenuItemTerms(
                            title='Processed',
                            search_quantity=_COL_PROCESSED,
                            options=2,
                            show_input=False,
                            show_statistics=False,
                        ),
                        MenuItemTerms(
                            title='Grown',
                            search_quantity=_COL_GROWN,
                            options=2,
                            show_input=False,
                            show_statistics=False,
                        ),
                    ],
                ),
            ],
        ),
        search_quantities=SearchQuantities(
            include=['*#pdi_nomad_plugin.mbe.materials.SubstrateMbe'],
        ),
        filters_locked={
            'section_defs.definition_qualified_name': [
                'pdi_nomad_plugin.mbe.materials.SubstrateMbe',
            ],
        },
    ),
)
