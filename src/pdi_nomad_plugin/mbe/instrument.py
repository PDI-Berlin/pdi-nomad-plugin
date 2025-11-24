import plotly.graph_objects as go
from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.hdf5 import HDF5Reference
from nomad.datamodel.metainfo.annotations import (
    ELNAnnotation,
    ELNComponentEnum,
    H5WebAnnotation,
    SectionProperties,
)
from nomad.datamodel.metainfo.basesections import (
    EntityReference,
    Instrument,
    PubChemPureSubstanceSection,
    PureSubstanceSection,
)
from nomad.datamodel.metainfo.plot import (
    PlotlyFigure,
    PlotSection,
)
from nomad.metainfo import (
    Datetime,
    MEnum,
    Quantity,
    SchemaPackage,
    Section,
    SubSection,
)
from nomad_material_processing.general import (
    TimeSeries,
)
from nomad_material_processing.vapor_deposition.general import (
    FilledSubstrateHolderPosition,
    GasFlow,
    InsertReduction,
    SubstrateHolder,
    SubstrateHolderPosition,
    VolumetricFlowRate,
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
from pdi_nomad_plugin.utils import (
    _not_equal,
)

m_package = SchemaPackage()


class Device(ArchiveSection):
    """
    A device that can be mounted in a Port of the MBE instrument:
    - sources
    - substrate holders
    - windows
    """

    pass


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


class ShutterStatus(TimeSeries):
    """
    The status of the shutter, can be 0 (closed) or 1 (open).
    """

    m_def = Section()
    value = Quantity(
        type=int,
        description='The observed value as a function of time.',
        shape=['*'],
    )
    time = Quantity(
        type=float,
        unit='s',
        description='The process time when each of the values were recorded.',
        shape=['*'],
    )
    timestamp = Quantity(
        type=Datetime,
        description='The process time when each of the values were recorded.',
        shape=['*'],
    )


class Shutter(PlotSection):
    """
    Shutter closing the inlet of the source or general Shutter in the MBE machine.
    """

    m_def = Section(
        # a_plotly_graph_object=[
        #     {
        #         "label": "Shutter status",
        #         "index": 0,
        #         "dragmode": "pan",
        #         "data": {
        #             "type": "scattergl",
        #             "line": {"width": 2},
        #             "marker": {"size": 6},
        #             "mode": "lines+markers",
        #             "name": "Status",
        #             "x": "#shutter_status/time",
        #             "y": "#shutter_status/value",
        #         },
        #         "layout": {
        #             "title": {"text": "Shutter status"},
        #             "xaxis": {
        #                 "showticklabels": True,
        #                 "fixedrange": True,
        #                 "ticks": "",
        #                 "title": {"text": "Elapsed time [s]"},
        #                 "showline": True,
        #                 "linewidth": 1,
        #                 "linecolor": "black",
        #                 "mirror": True,
        #             },
        #             "yaxis": {
        #                 "showticklabels": True,
        #                 "fixedrange": True,
        #                 "ticks": "",
        #                 "title": {"text": "Status"},
        #                 "showline": True,
        #                 "linewidth": 1,
        #                 "linecolor": "black",
        #                 "mirror": True,
        #             },
        #             "showlegend": False,
        #         },
        #         "config": {
        #             "displayModeBar": False,
        #             "scrollZoom": False,
        #             "responsive": False,
        #             "displaylogo": False,
        #             "dragmode": False,
        #         },
        #     },
        # ],
    )
    name = Quantity(
        type=str,
        description='The name of the shutter.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.StringEditQuantity,
        ),
    )
    shutter_status = SubSection(
        section_def=ShutterStatus,
    )

    def normalize(self, archive, logger):
        # plotly figure
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=self.shutter_status.timestamp,
                y=self.shutter_status.value,
                name=self.name,
                mode='markers',
                # line=dict(color="#2A4CDF", width=4),
                # fill="tonexty",
                yaxis='y',
            ),
        )
        # Add rectangles between each pair of points
        for i in range(len(self.shutter_status.timestamp) - 1):
            if self.shutter_status.value[i] == 0:
                continue
            if self.shutter_status.value[i] == 1:
                fig.add_shape(
                    type='rect',
                    x0=self.shutter_status.timestamp[i],
                    y0=self.shutter_status.value[i],
                    x1=self.shutter_status.timestamp[i + 1],
                    y1=0,
                    fillcolor='rgba(42, 76, 223, 0.2)',
                    line=dict(color='rgba(42, 76, 223, 0.2)'),
                )
                continue
        fig.update_shapes(dict(xref='x', yref='y'))
        fig.update_layout(
            template='plotly_white',
            dragmode='zoom',
            xaxis=dict(
                fixedrange=False,
                autorange=True,
                title='Elapsed time / s',
                mirror='all',
                showline=True,
                gridcolor='#EAEDFC',
            ),
            yaxis=dict(
                fixedrange=False,
                title='Shutter status',
                tickfont=dict(color='#2A4CDF'),
                gridcolor='#EAEDFC',
            ),
            showlegend=True,
        )
        self.figures = [
            PlotlyFigure(label='Shutter status', figure=fig.to_plotly_json())
        ]


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
        unit='m',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            defaultDisplayUnit='millimeter',
        ),
    )
    diameter = Quantity(
        type=float,
        description='The diameter of the crucible where material comes out.',
        unit='m',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            defaultDisplayUnit='millimeter',
        ),
    )
    source_to_substrate_distance = Quantity(
        type=float,
        description='The distance between the tip of the source and the substrate.',
        unit='m',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            defaultDisplayUnit='millimeter',
        ),
    )


class SourcePDI(Device, EntryData):
    """
    Some general information about the source recorded at PDI.
    """

    m_def = Section(
        label_quantity='name',
    )
    datetime = Quantity(
        type=Datetime,
        description='The date and time of creation of this entry.',
        a_eln=dict(component='DateTimeEditQuantity'),
    )
    type = Quantity(
        type=MEnum(
            'RF plasma source (PLASMA)',
            'Single filament effusion cell (SFC)',
            'Cold lip cell (CLC)',
            'Double filament effusion cell (DFC)',
            'other',
            'none',
        ),
        description='The type of the thermal evaporation source.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.EnumEditQuantity,
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
        type=HDF5Reference,
        unit='dimensionless',
        shape=[],
    )
    time = Quantity(
        type=HDF5Reference,
        description='The process time when each of the values were recorded.',
        shape=[],
    )


class EffusionCellHeaterTemperature(ThermalEvaporationHeaterTemperature):
    """
    The temperature of the heater during the deposition process.
    """

    m_def = Section(a_h5web=H5WebAnnotation(axes='time', signal='value'))
    value = Quantity(
        type=HDF5Reference,
        shape=[],
    )
    time = Quantity(
        type=HDF5Reference,
        description='The process time when each of the values were recorded.',
        shape=[],
    )


class ImpingingFluxPDI(ImpingingFlux):
    """
    The flux that impinges the surface of the substrate.
    It is calculated from the effusion cell heater temperature as the following:

    bep_to_flux * np.exp(a_parameter) * np.exp(t_0_parameter / temperature[:])

    """

    m_def = Section(a_h5web=H5WebAnnotation(axes='time', signal='value'))
    bep_to_flux = Quantity(
        type=float,
        description='The conversion factor from Beam Equivalent Pressure (BEP) to the flux.',
        unit='meter ** -2 * second ** -1 * pascal ** -1',
    )
    t_0_parameter = Quantity(
        type=float,
        unit='kelvin',
    )
    a_parameter = Quantity(
        type=float,
    )
    value = Quantity(
        type=HDF5Reference,
        shape=[],
    )
    time = Quantity(
        type=HDF5Reference,
        description='The process time when each of the values were recorded.',
        shape=[],
    )
    timestamp = Quantity(
        type=HDF5Reference,
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
        a_h5web=H5WebAnnotation(paths=['impinging_flux/0']),
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
    impinging_flux = SubSection(
        section_def=ImpingingFluxPDI,
        description="""
        The deposition rate of the material onto the substrate (mol/area/time).
        """,
        repeats=True,
    )


class SingleFilamentEffusionCell(EffusionCellSourcePDI):
    """
    A single filament effusion cell is a thermal evaporation source
    with a single filament that heats the material to the point of evaporation.
    """

    m_def = Section(
        label='Single Filament Effusion Cell',
    )


class ColdLipEffusionCell(EffusionCellSourcePDI):
    """
    A single filament effusion cell is a thermal evaporation source
    with a single filament that heats the material to the point of evaporation.

    This is a Cold Lip version of a single filament effusion cell.
    """

    m_def = Section(
        label='Cold Lip Effusion Cell',
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
        type=HDF5Reference,
        unit='watt',
        shape=[],
    )
    time = Quantity(
        type=HDF5Reference,
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

    m_def = Section(a_h5web=H5WebAnnotation(axes='time', signal='value'))
    measurement_type = Quantity(
        type=MEnum(
            'Mass Flow Controller',
            'Flow Meter',
            'Other',
        ),
    )
    value = Quantity(
        type=HDF5Reference,
        unit='meter ** 3 / second',
        shape=[],
    )
    time = Quantity(
        type=HDF5Reference,
        description='The process time when each of the values were recorded.',
        shape=[],
    )


class GasFlowPDI(GasFlow):
    """
    Section describing the flow of a gas.
    """

    m_def = Section()
    name = Quantity(
        type=str,
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.StringEditQuantity,
        ),
    )
    gas = SubSection(
        section_def=PureSubstanceSection,  # TODO change to PubChemPureSubstanceSection
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
        a_h5web=H5WebAnnotation(paths=['impinging_flux/0']),
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
    impinging_flux = SubSection(
        section_def=ImpingingFluxPDI,
        description="""
        The deposition rate of the material onto the substrate (mol/area/time).
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
    name = Quantity(
        type=str,
        description="""
        A short name for this position. This name is used as label of the position.
        """,
    )
    x_position = Quantity(
        type=float,
        unit='meter',
        description="""
        The x coordinate of the substrate holder position
        relative to the center of the holder.
        """,
    )
    y_position = Quantity(
        type=float,
        unit='meter',
        description="""
        The y coordinate of the substrate holder position
        relative to the center of the holder.
        """,
    )
    rho = Quantity(
        type=float,
        description="""
        Rho angle of the substrate holder in the x-y plane.
        """,
    )
    theta = Quantity(
        type=float,
        description="""
        Theta angle of the substrate holder in the x-z plane.
        """,
    )


class FilledSubstrateHolderPDI(SubstrateHolderPDI, EntryData):
    m_def = Section(
        label='SubstrateHolder (Filled)',
        categories=[PDIMBECategory],
    )
    substrate_holder = Quantity(
        type=SubstrateHolderPDI,
        description='A reference to an empty substrate holder.',
        a_eln=ELNAnnotation(
            component='ReferenceEditQuantity',
            label='Empty Substrate Holder Reference',
        ),
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

    def normalize(self, archive, logger):
        super().normalize(archive, logger)
        if len(self.positions) > 0 and self.substrate_holder is None:
            logger.error(
                'FilledSubstrateHolderPDI: positions list is not None and Empty Substrate Holder template is not linked. Delete all positions to import metadata from Empty Substrate Holder.'
            )
        if len(self.positions) > 0 and self.substrate_holder is not None:
            logger.warn(
                'FilledSubstrateHolderPDI: positions list is not None and Empty Substrate Holder template is linked. No metadata will be imported from Empty Substrate Holder. Delete all positions to import metadata from Empty Holder.'
            )
        if not len(self.positions) > 0 and self.substrate_holder is not None:
            materials_list = []
            for holder_material in self.substrate_holder.holder_material:
                materials_list.append(holder_material)
            self.holder_material = materials_list
            positions_list = []
            for position in self.substrate_holder.positions:
                positions_list.append(FilledSubstrateHolderPositionPDI())

                for value_from_empty, value_from_filled in zip(
                    position.m_def.all_quantities.keys(),
                    positions_list[-1].m_def.all_quantities.keys(),
                ):
                    if not position.m_is_set(value_from_empty):
                        continue
                    if not positions_list[-1].m_is_set(value_from_filled):
                        unit = None
                        default_unit = (
                            position.m_def.all_quantities[value_from_empty]
                            .m_annotations['eln']
                            .defaultDisplayUnit
                        )
                        unit = (
                            default_unit
                            if default_unit
                            else position.m_def.all_quantities[value_from_empty].unit
                        )
                        if unit:
                            positions_list[-1].m_set(
                                value_from_filled,
                                position.m_get(value_from_empty).to(unit),
                            )
                        else:
                            positions_list[-1].m_set(
                                value_from_filled, position.m_get(value_from_empty)
                            )
                if position.m_is_set('slot_geometry'):
                    positions_list[-1].slot_geometry = position.m_get_sub_sections(
                        'slot_geometry'
                    )[0]
            self.positions = positions_list
            for name, quantity in self.substrate_holder.m_def.all_quantities.items():
                if not self.substrate_holder.m_is_set(quantity):
                    continue
                if not self.m_is_set(quantity):
                    self.m_set(quantity, self.substrate_holder.m_get(quantity))
                elif _not_equal(
                    self.m_get(quantity), self.substrate_holder.m_get(quantity)
                ):
                    warning = (
                        f'Merging sections with different values for quantity "{name}".'
                    )
                    if logger:
                        logger.warning(warning)
                    else:
                        print(warning)

            # merge_sections(
            #     self, self.substrate_holder, FilledSubstrateHolderPositionPDI, logger
            # )


class FilledSubstrateHolderPDIReference(EntityReference):
    """
    A section used for referencing a FilledSubstrateHolderPDI.
    """

    m_def = Section(
        a_eln=ELNAnnotation(
            overview=True,
        )
    )
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
