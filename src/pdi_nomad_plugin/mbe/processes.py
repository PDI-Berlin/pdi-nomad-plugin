import json

import numpy as np
import plotly.graph_objects as go
from nomad.config import config
from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.hdf5 import HDF5Dataset
from nomad.datamodel.metainfo.annotations import (
    ELNAnnotation,
    ELNComponentEnum,
    H5WebAnnotation,
    SectionProperties,
)
from nomad.datamodel.metainfo.basesections import (
    Component,
    CompositeSystemReference,
    Experiment,
    Process,
    SectionReference,
    System,
    SystemComponent,
)
from nomad.datamodel.metainfo.plot import PlotlyFigure, PlotSection
from nomad.datamodel.metainfo.workflow import (
    Link,
)
from nomad.metainfo import (
    Datetime,
    Quantity,
    Reference,
    SchemaPackage,
    Section,
    SubSection,
)
from nomad_material_processing.general import (
    TimeSeries,
)
from nomad_material_processing.vapor_deposition.cvd.general import (
    Rotation,
)
from nomad_material_processing.vapor_deposition.general import (
    ChamberEnvironment,
    Pressure,
    SampleParameters,
    SubstrateHeater,
    Temperature,
    VaporDeposition,
    VaporDepositionStep,
    VolumetricFlowRate,
)
from nomad_measurements.general import ActivityReference
from nomad_measurements.xrd.schema import ELNXRayDiffraction

from pdi_nomad_plugin.characterization.schema import (
    AFMmeasurement,
    LaserReflectance,
    LightMicroscope,
    MassSpectrometry,
    Pyrometry,
    RHEEDMeasurement,
)
from pdi_nomad_plugin.general.schema import (
    PDIMBECategory,
    SampleCutPDI,
)
from pdi_nomad_plugin.mbe.instrument import (
    FilledSubstrateHolderPDIReference,
    SourcePDI,
)
from pdi_nomad_plugin.utils import (
    create_archive,
    handle_section,
    set_sample_status,
)

configuration = config.get_plugin_entry_point('pdi_nomad_plugin.mbe:processes_schema')

m_package = SchemaPackage()


class SystemComponentPDI(SystemComponent):
    """
    A section for describing a system component and its role in a composite system.
    """

    molar_concentration = Quantity(
        type=np.float64,
        description='The solvent for the current substance.',
        unit='mol/liter',
        a_eln=dict(component='NumberEditQuantity', defaultDisplayUnit='mol/liter'),
        a_tabular={
            'name': 'Precursors/Molar conc',
            # "unit": "gram"
        },
    )
    system = Quantity(
        type=Reference(System.m_def),
        description='A reference to the component system.',
        a_eln=dict(component='ReferenceEditQuantity'),
    )


class PrecursorsPreparationPDI(Process, EntryData):
    """
    Class autogenerated from yaml schema.
    """

    m_def = Section(
        a_eln={
            'hide': [
                'instruments',
                'steps',
                'samples',
            ]
        },
        label_quantity='name',
        categories=[PDIMBECategory],
        label='PrecursorsPreparation',
    )
    data_file = Quantity(
        type=str,
        description='Upload here the spreadsheet file containing the deposition control data',
        a_browser={'adaptor': 'RawFileAdaptor'},
        a_eln={'component': 'FileEditQuantity'},
    )
    lab_id = Quantity(
        type=str,
        description='FILL',
        a_tabular={'name': 'Precursors/Sample ID'},
        a_eln={'component': 'StringEditQuantity', 'label': 'Sample ID'},
    )
    tags = Quantity(
        type=str,
        shape=['*'],
        description='Searchable tags for this entry. Use Explore tab for searching.',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    name = Quantity(
        type=str,
        description='FILL',
        a_tabular={'name': 'Precursors/number'},
        a_eln={
            'component': 'StringEditQuantity',
        },
    )
    description = Quantity(
        type=str,
        a_eln={'component': 'StringEditQuantity'},
    )
    flow_titanium = Quantity(  # TODO make this a single flow
        type=np.float64,
        description='FILL THE DESCRIPTION',
        a_tabular={'name': 'Precursors/Set flow Ti'},
        a_eln={'component': 'NumberEditQuantity', 'defaultDisplayUnit': 'ml / minute'},
        unit='ml / minute',
    )
    flow_calcium = Quantity(
        type=np.float64,
        description='FILL THE DESCRIPTION',
        a_tabular={'name': 'Precursors/Set flow Ca'},
        a_eln={'component': 'NumberEditQuantity', 'defaultDisplayUnit': 'ml / minute'},
        unit='ml / minute',
    )
    # precursors = SubSection(
    #     section_def=SystemComponent,
    #     description="""
    #     A precursor used in MBE. It can be a solution, a gas, or a solid.
    #     """,
    #     repeats=True,
    # )
    components = SubSection(
        description="""
        A list of all the components of the composite system containing a name, reference
        to the system section and mass of that component.
        """,
        section_def=Component,
        repeats=True,
    )


class PrecursorsPreparationPDIReference(ActivityReference):
    """
    A section used for referencing a PrecursorsPreparationPDI.
    """

    m_def = Section(
        label='PrecursorsPreparationReference',
    )
    reference = Quantity(
        type=PrecursorsPreparationPDI,
        description='A reference to a NOMAD `PrecursorsPreparationPDI` entry.',
        a_eln=ELNAnnotation(
            component='ReferenceEditQuantity',
            label='PrecursorsPreparationPDI Reference',
        ),
    )


class PyrometryReference(SectionReference):
    """
    A section used for referencing a pyrometry.
    """

    reference = Quantity(
        type=Pyrometry,
        description='A reference to a NOMAD `Pyrometry` entry.',
        a_eln=ELNAnnotation(
            component='ReferenceEditQuantity',
            label='Pyrometry Reference',
        ),
    )


class LaserReflectanceReference(SectionReference):
    """
    A section used for referencing a LaserReflectance.
    """

    reference = Quantity(
        type=LaserReflectance,
        description='A reference to a NOMAD `LaserReflectance` entry.',
        a_eln=ELNAnnotation(
            component='ReferenceEditQuantity',
            label='Laser Reflectance Reference',
        ),
    )


class HallMeasurementReference(SectionReference):
    """
    A section used for referencing a HallMeasurement.
    The class is taken from the dedicated Lakeshore plugin
    """

    reference = Quantity(
        type=ArchiveSection,
        description='A reference to a NOMAD `HallMeasurement` entry.',
        a_eln=ELNAnnotation(
            component='ReferenceEditQuantity',
            label='Hall Measurement Reference',
        ),
    )


class AFMmeasurementReference(SectionReference):
    """
    A section used for referencing a AFMmeasurement.
    """

    reference = Quantity(
        type=AFMmeasurement,
        description='A reference to a NOMAD `AFMmeasurement` entry.',
        a_eln=ELNAnnotation(
            component='ReferenceEditQuantity',
            label='AFM Measurement Reference',
        ),
    )


class MassSpectrometryReference(SectionReference):
    """
    A section used for referencing a MassSpectrometry.
    """

    reference = Quantity(
        type=MassSpectrometry,
        description='A reference to a NOMAD `MassSpectrometry` entry.',
        a_eln=ELNAnnotation(
            component='ReferenceEditQuantity',
            label='MassSpectrometry Measurement Reference',
        ),
    )


class RHEEDReference(SectionReference):
    """
    RHEED measurement reference
    """

    reference = Quantity(
        type=RHEEDMeasurement,
        description='A reference to a NOMAD `RHEEDMeasurement` entry.',
        a_eln=ELNAnnotation(
            component='ReferenceEditQuantity',
            label='RHEEDMeasurement Measurement Reference',
        ),
    )


class LiMimeasurementReference(SectionReference):
    """
    A section used for referencing a LightMicroscope.
    """

    reference = Quantity(
        type=LightMicroscope,
        description='A reference to a NOMAD `LightMicroscope` entry.',
        a_eln=ELNAnnotation(
            component='ReferenceEditQuantity',
            label='Light Microscope Measurement Reference',
        ),
    )


class XRDmeasurementReference(SectionReference):
    """
    A section used for referencing a LightMicroscope.
    """

    sample_id = Quantity(
        type=str,
        description='The sample to be linked within the XRD measurement',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.StringEditQuantity,
        ),
    )
    reference = Quantity(
        type=ELNXRayDiffraction,
        description='A reference to a NOMAD `ELNXRayDiffraction` entry.',
        a_eln=ELNAnnotation(
            component='ReferenceEditQuantity',
            label='XRD Measurement Reference',
        ),
    )
    phase = Quantity(
        type=str,
        description='Phase type obtained from HRXRD',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.StringEditQuantity,
        ),
    )
    peak_position_2theta = Quantity(
        type=np.float64,
        description='Peak Position - 2theta',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
        ),
        unit='degree',
    )
    peak_fwhm_2theta = Quantity(
        type=np.float64,
        description='Peak Position - 2theta',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
        ),
        unit='degree',
    )
    peak_position_omega = Quantity(
        type=np.float64,
        description='Peak Position - Omega',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
        ),
        unit='degree',
    )
    peak_fwhm_rocking_curve = Quantity(
        type=str,
        description='Peak FWHM Rocking Curve',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.StringEditQuantity,
        ),
    )
    reflection = Quantity(
        type=str,
        description='Peak FWHM Rocking Curve',
        a_eln={'component': 'StringEditQuantity'},
    )
    description = Quantity(
        type=str,
        description='Notes and comments.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.RichTextEditQuantity,
        ),
    )

    def normalize(self, archive, logger):
        super().normalize(archive, logger)
        if (
            hasattr(self, 'reference')
            and self.reference is not None
            and hasattr(self, 'sample_id')
        ):
            # xrd_context = ServerContext(
            #     get_upload_with_read_access(
            #         archive.m_context.upload_id,
            #         User(
            #             is_admin=True,
            #             user_id=archive.metadata.main_author.user_id,
            #         ),
            #         include_others=True,
            #     )
            # )

            with archive.m_context.raw_file(
                self.reference.m_parent.metadata.mainfile, 'r'
            ) as xrd_file:
                updated_xrd_file = json.load(xrd_file)
                updated_xrd_file['data']['samples'] = [
                    CompositeSystemReference(
                        lab_id=self.sample_id,
                    ).m_to_dict()
                ]

            create_archive(
                updated_xrd_file,
                archive.m_context,
                self.reference.m_parent.metadata.mainfile,
                'json',
                logger,
                overwrite=True,
            )


class InSituCharacterizationMbePDI(ArchiveSection):
    pyrometry = SubSection(
        section_def=Pyrometry,
        repeats=True,
    )
    laser_reflectance = SubSection(
        section_def=LaserReflectanceReference,
    )
    mass_spectrometry = SubSection(
        section_def=MassSpectrometryReference,
    )
    rheed = SubSection(
        section_def=RHEEDReference,
    )


class CharacterizationMbePDI(ArchiveSection):
    """
    A wrapped class to gather all the characterization methods in MBE
    """

    xrd = SubSection(
        section_def=XRDmeasurementReference,
        repeats=True,
    )
    hall = SubSection(
        section_def=HallMeasurementReference,
        repeats=True,
    )
    afm = SubSection(
        section_def=AFMmeasurementReference,
        repeats=True,
    )
    light_microscopy = SubSection(
        section_def=LiMimeasurementReference,
        repeats=True,
    )


class ShaftTemperature(Temperature):
    """
    Central shaft temperature (to hold the susceptor)
    """

    pass


class FilamentTemperature(Temperature):
    """
    heating filament temperature
    """

    pass


class LayTecTemperature(Temperature):
    """
    Central shaft temperature (to hold the susceptor)
    """

    pass


class ChamberEnvironmentMbe(ChamberEnvironment):
    uniform_gas_flow_rate = SubSection(
        section_def=VolumetricFlowRate,
    )
    pressure = SubSection(
        section_def=Pressure,
    )
    throttle_valve = SubSection(
        section_def=Pressure,
    )
    rotation = SubSection(
        section_def=Rotation,
    )
    heater = SubSection(
        section_def=SubstrateHeater,
    )


class SubstrateHeaterPower(TimeSeries):
    """
    The working output power measured from the substrate termocouple (dimensionless).
    """

    m_def = Section(a_h5web=H5WebAnnotation(axes='time', signal='value'))
    value = Quantity(
        type=HDF5Dataset,
        unit='dimensionless',
        shape=[],
        a_h5web=H5WebAnnotation(
            long_name='power',
        ),
    )
    time = Quantity(
        type=HDF5Dataset,
        description='The process time when each of the values were recorded.',
        shape=[],
    )


class SubstrateHeaterTemperature(TimeSeries, PlotSection):
    """
    The temperature of the heater during the deposition process.
    """

    m_def = Section(a_h5web=H5WebAnnotation(axes='time', signal='value'))
    value = Quantity(
        type=HDF5Dataset,
        unit='kelvin',
        shape=[],
        a_h5web=H5WebAnnotation(
            long_name='temperature (K)',
        ),
    )
    time = Quantity(
        type=HDF5Dataset,
        description='The process time when each of the values were recorded.',
        shape=[],
        unit='second',
    )

    def normalize(self, archive, logger):
        super().normalize(archive, logger)
        with self.time as deserialized:
            time_array = deserialized[:]
        with self.value as deserialized:
            value_array = deserialized[:]
        with (
            archive.data.steps[0]
            .in_situ_characterization.pyrometry[0]
            .pyrometer_temperature.value as deserialized
        ):
            pyrometer_temperature = deserialized[:]
        with (
            archive.data.steps[0]
            .in_situ_characterization.pyrometry[0]
            .pyrometer_temperature.time as deserialized
        ):
            pyrometer_time = deserialized[:]
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=time_array,
                y=value_array,
                name='Sub Temp',
                line=dict(color='#2A4CDF', width=4),
                yaxis='y',
            ),
        )
        fig.add_trace(
            go.Scatter(
                x=pyrometer_time,
                y=pyrometer_temperature,
                name='Pyro Temp',
                line=dict(color='#90002C', width=2),
                yaxis='y',
            ),
        )
        fig.update_layout(
            template='plotly_white',
            dragmode='zoom',
            xaxis=dict(
                fixedrange=False,
                autorange=True,
                title='Process time / s',
                mirror='all',
                showline=True,
                gridcolor='#EAEDFC',
            ),
            yaxis=dict(
                fixedrange=False,
                title='Temperature / °C',
                tickfont=dict(color='#2A4CDF'),
                gridcolor='#EAEDFC',
            ),
            showlegend=True,
        )
        self.figures = [PlotlyFigure(label='figure 1', figure=fig.to_plotly_json())]


class SubstrateHeaterCurrent(TimeSeries):
    """
    The current of the heater during the deposition process.
    """

    m_def = Section(
        a_plot=[
            {
                'label': 'measured current',
                'x': 'time',
                'y': ['value'],
            },
        ],
        a_eln={
            'hide': [
                'set_value',
                'set_time',
            ]
        },
    )
    value = Quantity(
        type=float,
        unit='ampere',
        shape=['*'],
    )
    time = Quantity(
        type=Datetime,
        description='The process time when each of the values were recorded.',
        shape=['*'],
    )


class SubstrateHeaterVoltage(TimeSeries):
    """
    The voltage of the heater during the deposition process.
    """

    m_def = Section(
        a_plot=[
            {
                'label': 'measured voltage',
                'x': 'time',
                'y': ['value'],
            },
        ],
        a_eln={
            'hide': [
                'set_value',
                'set_time',
            ]
        },
    )
    value = Quantity(
        type=float,
        unit='volt',
        shape=['*'],
    )
    time = Quantity(
        type=Datetime,
        description='The process time when each of the values were recorded.',
        shape=['*'],
    )


class SampleParametersMbe(SampleParameters):
    m_def = Section(
        a_h5web=H5WebAnnotation(paths=['substrate_temperature', 'substrate_power']),
    )
    name = Quantity(
        type=str,
        description="""
        Sample name.
        """,
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    distance_to_source = Quantity(
        type=float,
        unit='meter',
        a_eln={'component': 'NumberEditQuantity', 'defaultDisplayUnit': 'millimeter'},
        description="""
        The distance between the substrate and the source.
        It is an array because multiple sources can be used.
        """,
        shape=[1],
    )
    substrate_temperature = SubSection(
        section_def=SubstrateHeaterTemperature,
    )
    substrate_power = SubSection(
        section_def=SubstrateHeaterPower,
    )
    substrate_voltage = SubSection(
        section_def=SubstrateHeaterVoltage,
    )
    substrate_current = SubSection(
        section_def=SubstrateHeaterCurrent,
    )


class GrowthStepMbePDI(VaporDepositionStep, PlotSection):
    """
    Growth step for MBE PDI
    """

    m_def = Section(
        # label='Growth Step Mbe 2',
        a_eln=None,
    )

    name = Quantity(
        type=str,
        description="""
        A short and descriptive name for this step.
        """,
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
            label='Step name',
        ),
    )
    step_index = Quantity(
        type=str,
        description='the ID from RTG',
        a_eln={
            'component': 'StringEditQuantity',
        },
    )
    # duration = VaporDepositionStep.duration.m_copy()

    duration = Quantity(
        type=float,
        unit='second',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
        ),
    )

    comment = Quantity(
        type=str,
        description='description',
        a_eln={'component': 'StringEditQuantity'},
        label='Notes',
    )
    sample_parameters = SubSection(
        section_def=SampleParametersMbe,
        repeats=True,
    )
    sources = SubSection(
        section_def=SourcePDI,
        repeats=True,
    )
    environment = SubSection(
        section_def=ChamberEnvironmentMbe,
    )

    in_situ_characterization = SubSection(section_def=InSituCharacterizationMbePDI)


class GrowthMbePDI(VaporDeposition, EntryData):
    """
    Class autogenerated from yaml schema.
    """

    m_def = Section(
        a_eln=ELNAnnotation(
            properties=SectionProperties(
                order=[
                    'name',
                    'method',
                    'data_file',
                    'datetime',
                    'end_time',
                    'duration',
                ],
            ),
            # hide=[
            #     "instruments",
            #     "steps",
            #     "samples",
            #     "description",
            #     "location",
            #     "lab_id",
            # ],
        ),
        label_quantity='lab_id',
        categories=[PDIMBECategory],
        label='Growth Process',
        a_h5web=H5WebAnnotation(
            paths=[
                'steps/0/sample_parameters/0/substrate_temperature',
                'steps/0/sample_parameters/0/substrate_power',
            ]
        ),
    )

    # datetime
    # name
    # description
    # lab_id
    # method
    method = Quantity(
        type=str,
        default='MBE PDI',
    )
    tags = Quantity(
        type=str,
        shape=['*'],
        description='Searchable tags for this entry. Use Explore tab for searching.',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    data_file = Quantity(
        type=str,
        description='Upload here the spreadsheet file containing the deposition control data',
        # a_tabular_parser={
        #     "parsing_options": {"comment": "#"},
        #     "mapping_options": [
        #         {
        #             "mapping_mode": "row",
        #             "file_mode": "multiple_new_entries",
        #             "sections": ["#root"],
        #         }
        #     ],
        # },
        a_browser={'adaptor': 'RawFileAdaptor'},
        a_eln={'component': 'FileEditQuantity'},
    )
    description = Quantity(
        type=str,
        description='description',
        a_eln={'component': 'StringEditQuantity'},
        label='Notes',
    )
    recipe_id = Quantity(
        type=str,
        description='the ID from RTG',
        a_tabular={'name': 'GrowthRun/Recipe Name'},
        a_eln={'component': 'StringEditQuantity', 'label': 'Recipe ID'},
    )
    susceptor = Quantity(
        type=str,
        description="""
        material of the susceptor adaptor
        """,
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    mask = Quantity(
        type=str,
        description="""
        type and size of growth map
        """,
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    pocket = Quantity(
        type=str,
        description="""
        position in the growth mask
        """,
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    steps = SubSection(
        section_def=GrowthStepMbePDI,
        repeats=True,
    )
    samples = SubSection(
        section_def=FilledSubstrateHolderPDIReference,
        repeats=True,
    )

    def normalize(self, archive, logger):
        # for sample in self.samples:
        #     sample.normalize(archive, logger)
        # for parent_sample in self.parent_sample:
        #     parent_sample.normalize(archive, logger)
        # for substrate in self.substrate:
        #     substrate.normalize(archive, logger)

        for sample_holder in self.samples:
            if sample_holder.reference:
                for sample_holder_position in sample_holder.reference.positions:
                    if sample_holder_position.substrate:
                        set_sample_status(
                            sample_holder_position.substrate.reference,
                            logger,
                            as_delivered=False,
                            fresh=False,
                            processed=sample_holder_position.substrate.reference.grown
                            if sample_holder_position.substrate.reference.grown
                            else False,
                            grown=True,
                        )

        archive.workflow2 = None
        super().normalize(archive, logger)
        if self.steps is not None:
            inputs = []
            outputs = []
            for step in self.steps:
                if step.sample_parameters is not None:
                    for sample in step.sample_parameters:
                        if sample.layer is not None:
                            outputs.append(
                                Link(
                                    name=f'{sample.layer.name}',
                                    section=sample.layer.reference,
                                )
                            )
                        if sample.substrate is not None:
                            outputs.append(
                                Link(
                                    name=f'{sample.substrate.name}',
                                    section=sample.substrate.reference,
                                )
                            )
                        if (
                            sample.substrate is not None
                            and sample.substrate.reference is not None
                        ):
                            if hasattr(
                                getattr(sample.substrate.reference, 'substrate'),
                                'name',
                            ):
                                # sample.substrate.reference.substrate.reference is not None:
                                inputs.append(
                                    Link(
                                        name=f'{sample.substrate.reference.substrate.name}',
                                        section=getattr(
                                            sample.substrate.reference.substrate,
                                            'reference',
                                            None,
                                        ),
                                    )
                                )
            archive.workflow2.outputs.extend(set(outputs))
            archive.workflow2.inputs.extend(set(inputs))


class SampleCutPDIReference(ActivityReference):
    """
    A section used for referencing a SampleCutPDI.
    """

    m_def = Section(
        label='SampleCutReference',
    )
    reference = Quantity(
        type=SampleCutPDI,
        description='A reference to a NOMAD `SampleCutPDI` entry.',
        a_eln=ELNAnnotation(
            component='ReferenceEditQuantity',
        ),
    )


class GrowthMbePDIReference(ActivityReference):
    """
    A section used for referencing a GrowthMbePDI.
    """

    m_def = Section(
        label='GrowthProcessReference',
    )
    reference = Quantity(
        type=GrowthMbePDI,
        description='A reference to a NOMAD `GrowthMbePDI` entry.',
        # a_eln=ELNAnnotation(
        #     component='ReferenceEditQuantity',
        # ),
    )


class ExperimentMbePDI(Experiment, EntryData):
    """
    Class autogenerated from yaml schema.
    """

    m_def = Section(
        # a_eln={"hide": ["steps"]},
        categories=[PDIMBECategory],
        label='Experiment MBE',
    )
    # lab_id
    method = Quantity(
        type=str,
    )
    tags = Quantity(
        type=str,
        shape=['*'],
        description='Searchable tags for this entry. Use Explore tab for searching.',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    data_file = Quantity(
        type=str,
        shape=['*'],
        description='Searchable tags for this entry. Use Explore tab for searching.',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    description = Quantity(
        type=str,
        description='description',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
            label='Notes',
        ),
    )
    growth_run = SubSection(
        section_def=GrowthMbePDIReference,
    )
    sample_cut = SubSection(
        section_def=GrowthMbePDIReference,
    )
    characterization = SubSection(section_def=CharacterizationMbePDI)

    steps = SubSection(
        section_def=ActivityReference,
        repeats=True,
    )
    # growth_run_constant_parameters = SubSection(
    #     section_def=GrowthMbe1PDIConstantParametersReference
    # )

    def normalize(self, archive, logger):
        archive_sections = (
            attr for attr in vars(self).values() if isinstance(attr, ArchiveSection)
        )
        step_list = []
        for section in archive_sections:
            try:
                if section is not None:
                    step_list.extend(handle_section(section))
            except (AttributeError, TypeError, NameError) as e:
                print(f'An error occurred in section XXX {section}: {e}')
        self.steps = [step for step in step_list if step is not None]

        activity_lists = (
            attr for attr in vars(self).values() if isinstance(attr, list)
        )
        for activity_list in activity_lists:
            for activity in activity_list:
                if isinstance(activity, ArchiveSection):
                    try:
                        step_list.extend(handle_section(activity))
                    except (AttributeError, TypeError, NameError) as e:
                        print(f'An error occurred in section YYY {section}: {e}')
        self.steps = [step for step in step_list if step is not None]

        archive.workflow2 = None
        super().normalize(archive, logger)

        # search_result = search(
        #     owner="user",
        #     query={
        #         "results.eln.sections:any": ["GrowthMbe1PDIConstantParameters"],
        #         "upload_id:any": [archive.m_context.upload_id],
        #     },
        #     pagination=MetadataPagination(page_size=10000),
        #     user_id=archive.metadata.main_author.user_id,
        # )
        # # checking if all entries are properly indexed
        # if getattr(
        #     getattr(self, "growth_run_constant_parameters", None), "lab_id", None
        # ) and not getattr(
        #     getattr(self, "growth_run_constant_parameters", None), "reference", None
        # ):
        #     found_id = False
        #     for growth_entry in search_result.data:
        #         if (
        #             self.growth_run_constant_parameters.lab_id
        #             == growth_entry["results"]["eln"]["lab_ids"][0]
        #         ):
        #             found_id = True
        #             self.growth_run_constant_parameters = GrowthMbe1PDIConstantParametersReference(
        #                 reference=f"../uploads/{archive.m_context.upload_id}/archive/{growth_entry['entry_id']}#data"
        #             )
        #         for search_quantities in growth_entry["search_quantities"]:
        #             if (
        #                 search_quantities["path_archive"]
        #                 == "data.substrate_temperature"
        #             ):
        #                 self.substrate_temperature = search_quantities["float_value"]
        #             if search_quantities["path_archive"] == "data.oxygen_argon_ratio":
        #                 self.oxygen_argon_ratio = search_quantities["float_value"]
        #             if search_quantities["path_archive"] == "data.composition":
        #                 self.composition = search_quantities["str_value"][0]
        #     if not found_id:
        #         logger.warning(
        #             f"The lab_id '{self.growth_run_constant_parameters.lab_id}' was not found in any 'GrowthMbe1PDIConstantParameters' entry in Nomad. Check if it exist and try to reference it manually."
        #         )
        # else:
        #     logger.warning(
        #         "No lab_id for 'GrowthMbe1PDIConstantParameters' found. The archive couldn't be referenced."
        #     )

    # def normalize(self, archive, logger: BoundLogger) -> None:
    #     '''
    #     The normalizer for the `MbeBinaryOxidesPDIExperiment` class.
    #     '''
    #     super(MbeBinaryOxidesPDIExperiment, self).normalize(archive, logger)
    ## Potential weak code in next lines:
    ## I want to get back to GrowthRun entry (already created by tabular parser)
    ## and set the "reference" quantity in grwon_samples.
    ## Here two example codes by Theodore Chang, first touches the raw file, second touches the processed file.
    #### ONE
    ## 1. get the file name of archive/entry containing grown_sample_ref
    ## 2. overwrite yaml for this entry
    ## 3. reprocess
    # grown_sample_ref.reference = f'../uploads/{archive.m_context.upload_id}/archive/{hash(archive.m_context.upload_id, filename)}#data'
    # grown_sample_archive = grown_sample_ref
    # while not isinstance(grown_sample_archive, EntryArchive):
    #     grown_sample_archive=grown_sample_archive.m_parent
    # grown_sample_file_name:str = grown_sample_archive.metadata.mainfile
    # create_archive(
    #     grown_sample_archive.m_to_dict(), archive.m_context, grown_sample_file_name, filetype, logger,bypass_check=True)
    #### TWO
    ## alternatively directly overwite the processed msg file
    # grown_sample_upload_id:str = grown_sample_archive.metadata.upload_id
    # grown_sample_entry_id:str = grown_sample_archive.metadata.entry_id
    # StagingUploadFiles(grown_sample_upload_id).write_archive(grown_sample_entry_id, grown_sample_archive.m_to_dict())


m_package.__init_metainfo__()
