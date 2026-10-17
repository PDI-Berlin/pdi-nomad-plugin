"""Native NOMAD app for original Material Processing crystalline substrates.

The native search app exposes only indexed, official metainfo quantities.
Treatment/growth status is derived from process archives in the dedicated
Substrate Search / Processing dashboards, not fictional substrate flags.
"""

from nomad.config.models.plugins import AppEntryPoint
from nomad.config.models.ui import App, Column, Menu, MenuItemTerms, SearchQuantities

ORIGINAL_SUBSTRATE = 'nomad_material_processing.general.CrystallineSubstrate'
LAB_ID = f'data.lab_id#{ORIGINAL_SUBSTRATE}'
NAME = f'data.name#{ORIGINAL_SUBSTRATE}'
SUPPLIER = f'data.supplier#{ORIGINAL_SUBSTRATE}'
SUPPLIER_ID = f'data.supplier_id#{ORIGINAL_SUBSTRATE}'

substrateapp = AppEntryPoint(
    name='Substrates',
    description='Browse crystalline substrates using original NOMAD schemas.',
    app=App(
        label='Substrates',
        path='substrateapp',
        category='PDI',
        columns=[
            Column(search_quantity=LAB_ID, label='Substrate ID', selected=True),
            Column(search_quantity=NAME, label='Name', selected=True),
            Column(search_quantity=SUPPLIER, label='Supplier', selected=True),
            Column(search_quantity=SUPPLIER_ID, label='Supplier ID', selected=True),
        ],
        menu=Menu(
            title='Filters',
            size='sm',
            items=[
                MenuItemTerms(
                    search_quantity=LAB_ID,
                    options=100,
                    show_input=True,
                    show_statistics=False,
                ),
                MenuItemTerms(
                    search_quantity=SUPPLIER,
                    options=50,
                    show_input=True,
                    show_statistics=False,
                ),
                MenuItemTerms(
                    search_quantity=SUPPLIER_ID,
                    options=50,
                    show_input=True,
                    show_statistics=False,
                ),
            ],
        ),
        search_quantities=SearchQuantities(include=[f'*#{ORIGINAL_SUBSTRATE}']),
        filters_locked={
            'section_defs.definition_qualified_name': [ORIGINAL_SUBSTRATE],
        },
    ),
)
