from nomad.config import config
from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.metainfo.annotations import (
    ELNAnnotation,
    ELNComponentEnum,
    SectionProperties,
)
from nomad.datamodel.metainfo.basesections import (
    PubChemPureSubstanceSection,
    Instrument,
)
from nomad.metainfo import (
    MEnum,
    Quantity,
    SchemaPackage,
    Section,
    SubSection,
)
from nomad_material_processing.vapor_deposition.general import (
    FilledSubstrateHolder,
    FilledSubstrateHolderPosition,
    GasFlow,
    InsertReduction,
    SubstrateHolder,
    SubstrateHolderPosition,
)
from nomad_material_processing.vapor_deposition.pvd.general import (
    PVDSource,
    PVDEvaporationSource,
)
from nomad_material_processing.vapor_deposition.pvd.thermal import (
    ThermalEvaporationSource,
)

from pdi_nomad_plugin.general.schema import (
    PDIMBECategory,
)

configuration = config.get_plugin_entry_point('pdi_nomad_plugin.mbe:instrument_schema')

m_package = SchemaPackage()


class SourceGeometry(ArchiveSection):
    """
    The geometry of the source.
    """

    m_def = Section(
        label='Source Geometry',
    )
    source_length = Quantity(
        type=float,
        description='The length of the source.',
        unit='mm',
    )
    diameter = Quantity(
        type=float,
        description='The diameter of the crucible where material comes out.',
        unit='mm',
    )


class SourcePDI(ArchiveSection):
    """
    Some general information about the source recorded at PDI.
    """

    type = Quantity(
        type=MEnum(
            'RF plasma source',
            'Single filament effusion cell',
            'Double filament effusion cell',
            'other',
            'none',
        ),
        description='The type of the thermal evaporation source.',
    )
    tags = Quantity(
        type=str,
        shape=['*'],
        description='Searchable tags for this entry. Use Explore tab for searching.',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    port_number = Quantity(
        type=int,
        description='The port number of the MBE machine where the source is mounted.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
        ),
    )
    distance_to_substrate = Quantity(
        type=float,
        description='The distance from the tip of the source to the substrate.',
        unit='mm',
    )
    primary_flux_species = SubSection(
        section_def=PubChemPureSubstanceSection,
        description="""
        The primary species that is actually impinching
        on the substrate after evaporation.
        """,
        repeats=True,
    )
    secondary_flux_species = SubSection(
        section_def=PubChemPureSubstanceSection,
        description="""
        The secondary species that is actually impinching
        on the substrate after evaporation.
        """,
        repeats=True,
    )
    geometry = SubSection(
        section_def=SourceGeometry,
    )


class Crucible(ArchiveSection):
    """
    The crucible used in the effusion cell.
    """

    m_def = Section(
        label='Crucible',
    )
    lab_id = Quantity(
        type=str,
        description="""
        A unique human readable ID for the crucible.
        """,
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.StringEditQuantity,
            label='Crucible ID',
        ),
    )
    image = Quantity(
        type=str,
        description='image of teh crucible',
        a_browser={'adaptor': 'RawFileAdaptor'},
        a_eln={'component': 'FileEditQuantity'},
    )


class EffusionCellSourcePDI(ThermalEvaporationSource, SourcePDI):
    """
    A thermal evaporation source is a device that heats a material
    to the point of evaporation.
    """

    m_def = Section(
        label='Effusion Cell',
        links=['http://purl.obolibrary.org/obo/CHMO_0001558'],
        categories=[PDIMBECategory],
        a_eln=ELNAnnotation(
            properties=SectionProperties(
                order=[
                    'name',
                    'tags',
                    'distance_to_substrate',
                    'port_number',
                    'temperature',
                    'power',
                    'material',
                ],
            ),
            lane_width='600px',
        ),
    )
    crucible = SubSection(
        section_def=Crucible,
    )


class RfGenerator(PVDEvaporationSource):
    """
    The RF generator used to create the plasma.
    """

    m_def = Section(
        label='RF Generator',
    )
    forward_power = Quantity(
        type=float,
        description='The power of the RF generator sent in the coil.',
        unit='W',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
        ),
    )
    reflected_power = Quantity(
        type=float,
        description='The power reflected back.',
        unit='W',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
        ),
    )
    dissipated_power = Quantity(
        type=float,
        description="""
        Difference between forward and reflected power.
        The power adsorbed by the vapor.
        """,
        unit='W',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
        ),
    )


class PlasmaSourcePDI(PVDSource, SourcePDI):
    """
    An RF plasma source for vapor deposition generates a plasma by applying
    radio frequency energy to a gas, creating ionized particles that facilitate
    the deposition of thin layers on a substrate. It provides precise control
    over deposition parameters like ion energy and density,
    crucial for uniform and high-quality film formation.
    """

    m_def = Section(
        label='Plasma Source',
        categories=[PDIMBECategory],
        a_eln=ELNAnnotation(
            properties=SectionProperties(
                order=[
                    'name',
                    'tags',
                    'distance_to_substrate',
                    'port_number',
                    'temperature',
                    'power',
                    'material',
                ],
            ),
            lane_width='600px',
        ),
    )
    vapor_source = SubSection(
        section_def=RfGenerator,
        description="""
        The RF generator used to create the plasma.
        """,
    )
    gas_flow = SubSection(
        section_def=GasFlow,
        repeats=True,
    )


class InsertReductionPDI(InsertReduction, EntryData):
    m_def = Section(
        label='InsertReduction',
        categories=[PDIMBECategory],
    )
    tags = Quantity(
        type=str,
        shape=['*'],
        description='Searchable tags for this entry. Use Explore tab for searching.',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )


class SubstrateHolderPositionPDI(SubstrateHolderPosition):
    rho = Quantity(
        type=float,
        unit='meter',
        description="""
        Rho angle of the substrate holder in the x-y plane.
        """,
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            defaultDisplayUnit='millimeter',
        ),
    )
    theta = Quantity(
        type=float,
        unit='degree',
        description="""
        Theta angle of the substrate holder in the x-z plane.
        """,
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
        ),
    )


class SubstrateHolderPDI(SubstrateHolder, EntryData):
    m_def = Section(
        label='SubstrateHolder (Empty Template)',
        categories=[PDIMBECategory],
    )
    positions = SubSection(
        section_def=SubstrateHolderPositionPDI,
        repeats=True,
    )
    tags = Quantity(
        type=str,
        shape=['*'],
        description='Searchable tags for this entry. Use Explore tab for searching.',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )


class FilledSubstrateHolderPositionPDI(FilledSubstrateHolderPosition):
    rho = Quantity(
        type=float,
        description="""
        Rho angle of the substrate holder in the x-y plane.
        """,
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
        ),
    )
    theta = Quantity(
        type=float,
        description="""
        Theta angle of the substrate holder in the x-z plane.
        """,
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
        ),
    )


class FilledSubstrateHolderPDI(FilledSubstrateHolder, EntryData):
    m_def = Section(
        label='SubstrateHolder (Filled)',
        categories=[PDIMBECategory],
    )
    positions = SubSection(
        section_def=FilledSubstrateHolderPositionPDI,
        repeats=True,
    )
    tags = Quantity(
        type=str,
        shape=['*'],
        description='Searchable tags for this entry. Use Explore tab for searching.',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )


class Port(ArchiveSection):
    """
    A port in the MBE machine where
    the source,
    the substrate holder,
    or the window
    are mounted.
    """

    m_def = Section()

    lab_id = Quantity(
        type=str,
        description="""
        A unique human readable ID for the Instrument with a specific setup.
        """,
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.StringEditQuantity,
            label='Port ID',
        ),
    )
    number = Quantity(
        type=int,
        description='The port number.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
        ),
    )
    theta = Quantity(
        type=float,
        description='Theta angle of the port in the x-z plane.',
        unit='degree',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
        ),
    )
    phi = Quantity(
        type=float,
        description='Phi angle of the port in the x-y plane.',
        unit='degree',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
        ),
    )
    flange_diameter = Quantity(
        type=float,
        description='The diameter of the flange.',
        unit='meter',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            defaultDisplayUnit='millimeter',
        ),
    )
    flange_to_substrate_distance = Quantity(
        type=float,
        description='The distance from the flange to the substrate.',
        unit='meter',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            defaultDisplayUnit='millimeter',
        ),
    )
    device = Quantity(
        type=MEnum(
            'source',
            'substrate holder',
            'window',
            'other',
            'none',
        ),
        description='The device mounted in the port.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.EnumEditQuantity,
        ),
    )


class InstrumentMbePDI(Instrument, EntryData):
    """
    The instrument used for Molecular Beam Epitaxy (MBE) at PDI.
    """

    m_def = Section(
        label='Instrument MBE',
        categories=[PDIMBECategory],
    )

    lab_id = Quantity(
        type=str,
        description="""
        A unique human readable ID for the Instrument with a specific setup.
        """,
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.StringEditQuantity,
            label='Instrument ID',
        ),
    )
    chamber_geometry = Quantity(
        type=str,
        description='The geometry of the MBE chamber.',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    port_list = SubSection(
        section_def=Port,
        repeats=True,
    )


m_package.__init_metainfo__()
