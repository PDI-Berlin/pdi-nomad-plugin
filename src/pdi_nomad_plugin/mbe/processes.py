import json

import numpy as np
from nomad.config import config
from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.metainfo.annotations import (
    ELNAnnotation,
    ELNComponentEnum,
    SectionProperties,
)
from nomad.datamodel.metainfo.basesections import (
    CompositeSystemReference,
    Experiment,
    SectionReference,
)
from nomad.datamodel.metainfo.plot import PlotSection
from nomad.datamodel.metainfo.workflow import (
    Link,
)
from nomad.metainfo import (
    Quantity,
    SchemaPackage,
    Section,
    SubSection,
)
from nomad_material_processing.vapor_deposition.cvd.general import (
    CVDSource,
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

from pdi_nomad_plugin.characterization.schema import AFMmeasurement, LightMicroscope
from pdi_nomad_plugin.general.schema import (
    PDIMBECategory,
    SampleCutPDI,
)
from pdi_nomad_plugin.utils import (
    create_archive,
    handle_section,
)

configuration = config.get_plugin_entry_point('pdi_nomad_plugin.mbe:processes_schema')

m_package = SchemaPackage()


class InSituMonitoringReference(SectionReference):
    """
    A section used for referencing a InSituMonitoring.
    """

    reference = Quantity(
        type=ArchiveSection,
        description='A reference to a NOMAD `InSituMonitoring` entry.',
        a_eln=ELNAnnotation(
            component='ReferenceEditQuantity',
            label='In situ Monitoring Reference',
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
        super(XRDmeasurementReference, self).normalize(archive, logger)
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


class SampleParametersMbe(SampleParameters):
    m_def = Section(
        a_eln=ELNAnnotation(
            properties=SectionProperties(
                order=[
                    'shaft_temperature',
                    'filament_temperature',
                    'laytec_temperature',
                    'substrate_temperature',
                    'in_situ_reflectance',
                    'growth_rate',
                    'layer',
                    'substrate',
                ],
            ),
        ),
        a_plotly_graph_object=[
            {
                'label': 'filament temperature',
                'index': 1,
                'dragmode': 'pan',
                'data': {
                    'type': 'scattergl',
                    'line': {'width': 2},
                    'marker': {'size': 6},
                    'mode': 'lines+markers',
                    'name': 'Filament Temperature',
                    'x': '#filament_temperature/time',
                    'y': '#filament_temperature/value',
                },
                'layout': {
                    'title': {'text': 'Filament Temperature'},
                    'xaxis': {
                        'showticklabels': True,
                        'fixedrange': True,
                        'ticks': '',
                        'title': {'text': 'Process time [min]'},
                        # "showline": True,
                        'linewidth': 1,
                        'linecolor': 'black',
                        'mirror': True,
                    },
                    'yaxis': {
                        'showticklabels': True,
                        'fixedrange': True,
                        'ticks': '',
                        'title': {'text': 'Temperature [°C]'},
                        # "showline": True,
                        'linewidth': 1,
                        'linecolor': 'black',
                        'mirror': True,
                    },
                    'showlegend': False,
                },
                'config': {
                    'displayModeBar': False,
                    'scrollZoom': False,
                    'responsive': False,
                    'displaylogo': False,
                    'dragmode': False,
                },
            },
        ],
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
    filament_temperature = SubSection(
        section_def=FilamentTemperature,
    )
    in_situ_reflectance = SubSection(
        section_def=InSituMonitoringReference,
    )


class GrowthStepMbePDI(VaporDepositionStep, PlotSection):
    """
    Growth step for MBE PDI
    """

    m_def = Section(
        # label='Growth Step Mbe 2',
        a_eln=None,
    )
    # name
    # step_index
    # creates_new_thin_film
    # duration
    # sources
    # sample_parameters
    # environment
    # description

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
        section_def=CVDSource,
        repeats=True,
    )
    environment = SubSection(
        section_def=ChamberEnvironmentMbe,
    )
    in_situ_reflectance = SubSection(
        section_def=InSituMonitoringReference,
    )


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

    def normalize(self, archive, logger):
        # for sample in self.samples:
        #     sample.normalize(archive, logger)
        # for parent_sample in self.parent_sample:
        #     parent_sample.normalize(archive, logger)
        # for substrate in self.substrate:
        #     substrate.normalize(archive, logger)

        archive.workflow2 = None
        super(GrowthMbePDI, self).normalize(archive, logger)
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
        a_eln=ELNAnnotation(
            component='ReferenceEditQuantity',
        ),
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
        description='Upload here the spreadsheet file containing the growth data',
        a_browser={'adaptor': 'RawFileAdaptor'},
        a_eln={'component': 'FileEditQuantity'},
    )
    description = Quantity(
        type=str,
        description='description',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
            label='Notes',
        ),
    )
    substrate_temperature = Quantity(
        type=np.float64,
        description='FILL THE DESCRIPTION',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='celsius',
        ),
        unit='kelvin',
    )
    oxygen_argon_ratio = Quantity(
        type=str,
        description='FILL THE DESCRIPTION',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    composition = Quantity(
        type=str,
        description='FILL THE DESCRIPTION',
        a_eln={
            'component': 'StringEditQuantity',
        },
    )
    pregrowth = SubSection(
        section_def=GrowthMbePDIReference,
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
        super(ExperimentMbePDI, self).normalize(archive, logger)

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
