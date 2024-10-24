from nomad.config import config
from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.hdf5 import HDF5Dataset
from nomad.datamodel.metainfo.annotations import (
    ELNAnnotation,
    ELNComponentEnum,
    SectionProperties,
    H5WebAnnotation,
)
from nomad.datamodel.metainfo.basesections import (
    EntityReference,
    Instrument,
    PubChemPureSubstanceSection,
)
from nomad.metainfo import (
    Datetime,
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
    VolumetricFlowRate,
    InsertReduction,
    SubstrateHolder,
    SubstrateHolderPosition,
)
from nomad_material_processing.vapor_deposition.pvd.general import (
    ImpingingFlux,
    PVDEvaporationSource,
    PVDSource,
    SourcePower,
)
from nomad_material_processing.vapor_deposition.pvd.thermal import (
    ThermalEvaporationHeater,
    ThermalEvaporationHeaterTemperature,
    ThermalEvaporationSource,
)

from pdi_nomad_plugin.general.schema import (
    PDIMBECategory,
)

configuration = config.get_plugin_entry_point('pdi_nomad_plugin.mbe:instrument_schema')

m_package = SchemaPackage()


class Device(ArchiveSection):
    """
    A device that can be mounted in a Port of the MBE instrument:
    - sources
    - substrate holders
    - windows
    """


class Port(ArchiveSection):
    """
    A port in the MBE machine where
    the source,
    the substrate holder,
    or the window
    are mounted.
    """

    m_def = Section()
    name = Quantity(
        type=str,
        description='The device mounted of the port.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.StringEditQuantity,
        ),
    )
    port_number = Quantity(
        type=int,
        description='The port number of the MBE machine where the source is mounted.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
        ),
    )
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
    # device = Quantity(
    #     type=Device,
    #     description='The device mounted in the port.',
    #     a_eln=ELNAnnotation(
    #         component=ELNComponentEnum.ReferenceEditQuantity,
    #     ),
    # )


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


class SourcePDI(Device, EntryData):
    """
    Some general information about the source recorded at PDI.
    """

    datetime = Quantity(
        type=Datetime,
        description='The date and time of creation of this entry.',
        a_eln=dict(component='DateTimeEditQuantity'),
    )
    type = Quantity(
        type=MEnum(
            'RF plasma source (PLASMA)',
            'Single filament effusion cell (SFC)',
            'Double filament effusion cell (DFC)',
            'other',
            'none',
        ),
        description='The type of the thermal evaporation source.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.EnumEditQuantity,
        ),
    )
    lab_id = Quantity(
        type=str,
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.StringEditQuantity,
            label='Source ID',
        ),
    )
    tags = Quantity(
        type=str,
        shape=['*'],
        description='Searchable tags for this entry. Use Explore tab for searching.',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    port = Quantity(
        type=Port,
        description='The port of the reaction chamber.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.ReferenceEditQuantity,
        ),
    )
    epic_loop = Quantity(
        type=str,
        description='The EPIC loop string.',
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


# class SourcePDIReference(EntityReference):
#     """
#     Class autogenerated from yaml schema.
#     """

#     name = Quantity(
#         type=str,
#         a_eln=ELNAnnotation(
#             component=ELNComponentEnum.StringEditQuantity,
#         ),
#     )
#     reference = Quantity(
#         type=SourcePDI,
#         a_eln=ELNAnnotation(
#             component=ELNComponentEnum.ReferenceEditQuantity,
#             label='Thin Film',
#         ),
#     )


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


class EffusionCellHeaterPower(SourcePower):
    """
    The working output power measured from the effusion cell termocouple (dimensionless).
    """

    m_def = Section(a_h5web=H5WebAnnotation(axes='time', signal='value'))
    value = Quantity(
        type=HDF5Dataset,
        unit='dimensionless',
        shape=[],
    )
    time = Quantity(
        type=HDF5Dataset,
        description='The process time when each of the values were recorded.',
        shape=[],
    )


class EffusionCellHeaterTemperature(ThermalEvaporationHeaterTemperature):
    """
    The temperature of the heater during the deposition process.
    """

    m_def = Section(a_h5web=H5WebAnnotation(axes='time', signal='value'))
    value = Quantity(
        type=HDF5Dataset,
        unit='kelvin',
        shape=[],
    )
    time = Quantity(
        type=HDF5Dataset,
        description='The process time when each of the values were recorded.',
        shape=[],
    )


class ImpingingFluxPDI(ImpingingFlux):
    """
    The flux that impinges the surface of the substrate.
    """

    m_def = Section(a_h5web=H5WebAnnotation(axes='time', signal='value'))
    bep_to_flux = Quantity(
        type=float,
        description='The conversion factor from Beam Equivalent Pressure (BEP) to the flux.',
        unit='mol **-1 * meter ** -2 * second * pascal ** -1',
    )
    t_0_parameter = Quantity(
        type=float,
        unit='kelvin',
    )
    a_parameter = Quantity(
        type=float,
    )
    value = Quantity(
        type=HDF5Dataset,
        unit='mol/meter ** 2/second',
        shape=[],
    )
    time = Quantity(
        type=HDF5Dataset,
        description='The process time when each of the values were recorded.',
        shape=[],
    )


class EffusionCellHeater(ThermalEvaporationHeater):
    m_def = Section()
    temperature = SubSection(
        section_def=EffusionCellHeaterTemperature,
    )
    power = SubSection(
        section_def=EffusionCellHeaterPower,
        description='The power to the termocouple.',
    )


class EffusionCellSourcePDI(SourcePDI, ThermalEvaporationSource):
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
                    'datetime',
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
    # material has been taken from VaporDepositionSource
    material = SubSection(
        section_def=PubChemPureSubstanceSection,
        description="""
        The source of the material that is being evaporated.
        Example: A sputtering target, a powder in a crucible, etc.
        """,
        repeats=True,
    )
    vapor_source = SubSection(
        section_def=EffusionCellHeater,
    )


class SingleFilamentEffusionCell(EffusionCellSourcePDI):
    """
    A single filament effusion cell is a thermal evaporation source
    with a single filament that heats the material to the point of evaporation.
    """

    m_def = Section(
        label='Single Filament Effusion Cell',
    )


class DoubleFilamentEffusionCell(EffusionCellSourcePDI):
    """
    A double filament effusion cell is a thermal evaporation source
    with two filaments that heat the material to the point of evaporation.
    """

    m_def = Section(
        label='Double Filament Effusion Cell',
        a_eln=ELNAnnotation(
            properties=SectionProperties(
                order=[
                    'vapor_source',
                    'vapor_source_hot_lip',
                ],
            ),
        ),
    )
    vapor_source_hot_lip = SubSection(
        section_def=EffusionCellHeater,
    )


class RfGeneratorHeaterPower(SourcePower):
    """
    The power of the heater during the deposition process.
    """

    m_def = Section(a_h5web=H5WebAnnotation(axes='time', signal='value'))
    value = Quantity(
        type=HDF5Dataset,
        unit='watt',
        shape=[],
    )
    time = Quantity(
        type=HDF5Dataset,
        description='The process time when each of the values were recorded.',
        shape=[],
    )


class RfGeneratorHeater(PVDEvaporationSource):
    """
    The reflected and dissipated power (watt) used in the radio frequency (RF)
    generator to create the plasma.
    """

    m_def = Section(
        label='RF Generator',
    )
    forward_power = SubSection(
        section_def=RfGeneratorHeaterPower,
        description='The power of the RF generator sent in the coil.',
    )
    reflected_power = SubSection(
        section_def=RfGeneratorHeaterPower,
        description='The power reflected back.',
    )
    dissipated_power = SubSection(
        section_def=RfGeneratorHeaterPower,
        description="""
        Difference between forward and reflected power.
        The power adsorbed by the vapor.
        """,
    )


class VolumetricFlowRatePDI(VolumetricFlowRate):
    """
    The volumetric flow rate of a gas at standard conditions, i.e. the equivalent rate
    at a temperature of 0 °C (273.15 K) and a pressure of 1 atm (101325 Pa).
    """

    m_def = Section()
    measurement_type = Quantity(
        type=MEnum(
            'Mass Flow Controller',
            'Flow Meter',
            'Other',
        ),
    )
    value = Quantity(
        type=HDF5Dataset,
        unit='meter ** 3 / second',
        shape=[],
    )
    time = Quantity(
        type=HDF5Dataset,
        description='The process time when each of the values were recorded.',
        shape=[],
    )


class GasFlowPDI(GasFlow):
    """
    Section describing the flow of a gas.
    """

    m_def = Section()
    gas = SubSection(
        section_def=PubChemPureSubstanceSection,
    )
    flow_rate = SubSection(
        section_def=VolumetricFlowRatePDI,
    )


class PlasmaSourcePDI(SourcePDI, PVDSource):
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
                    'datetime',
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
        section_def=RfGeneratorHeater,
        description="""
        The RF generator used to create the plasma.
        """,
    )
    gas_flow = SubSection(
        section_def=GasFlowPDI,
        repeats=True,
    )
    # material has been taken from VaporDepositionSource
    material = SubSection(
        section_def=PubChemPureSubstanceSection,
        description="""
        The source of the material that is being evaporated.
        Example: A sputtering target, a powder in a crucible, etc.
        """,
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
        Module of the substrate holder in the x-y plane.
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
        Theta angle of the substrate holder in the x-y plane.
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


class FilledSubstrateHolderPDIReference(EntityReference):
    """
    A section used for referencing a FilledSubstrateHolderPDI.
    """

    reference = Quantity(
        type=FilledSubstrateHolderPDI,
        description='A reference to a NOMAD `FilledSubstrateHolderPDI` entry.',
        a_eln=ELNAnnotation(
            component='ReferenceEditQuantity',
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
