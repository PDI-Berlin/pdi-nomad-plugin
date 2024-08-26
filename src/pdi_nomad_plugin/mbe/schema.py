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
    Component,
    CompositeSystemReference,
    Experiment,
    Process,
    PureSubstance,
    SectionReference,
    System,
    SystemComponent,
)
from nomad.datamodel.metainfo.plot import PlotSection
from nomad.datamodel.metainfo.workflow import (
    Link,
)
from nomad.metainfo import (
    Datetime,
    MEnum,
    Quantity,
    Reference,
    SchemaPackage,
    Section,
    SubSection,
)
from nomad.utils import hash
from nomad_material_processing.general import (
    CrystallineSubstrate,
    Geometry,
    Parallelepiped,
    ThinFilm,
    ThinFilmStack,
    ThinFilmStackReference,
)
from nomad_material_processing.vapor_deposition.cvd.general import (
    CVDSource,
    Rotation,
)
from nomad_material_processing.vapor_deposition.general import (
    ChamberEnvironment,
    FilledSubstrateHolder,
    FilledSubstrateHolderPosition,
    InsertReduction,
    Pressure,
    SampleParameters,
    SubstrateHeater,
    SubstrateHolder,
    SubstrateHolderPosition,
    Temperature,
    VaporDeposition,
    VaporDepositionStep,
    VolumetricFlowRate,
)
from nomad_measurements.general import ActivityReference
from nomad_measurements.xrd.schema import ELNXRayDiffraction
from structlog.stdlib import (
    BoundLogger,
)

from pdi_nomad_plugin.characterization.schema import AFMmeasurement, LightMicroscope
from pdi_nomad_plugin.general.schema import (
    PDIMBECategory,
    SampleCutPDI,
)
from pdi_nomad_plugin.utils import (
    create_archive,
    handle_section,
)

configuration = config.get_plugin_entry_point('pdi_nomad_plugin.mbe:schema')

m_package = SchemaPackage()


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


class Shape(Parallelepiped):
    diameter = Quantity(
        type=float,
        description='The diamater',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            defaultDisplayUnit='millimeter',
        ),
        unit='meter',
    )


class BubblerPrecursor(PureSubstance, EntryData):
    """
    A precursor already loaded in a bubbler.
    To calculate the vapor pressure the Antoine equation is used.
    log10(p) = A - [B / (T + C)]
    It is a mathematical expression (derived from the Clausius-Clapeyron equation)
    of the relation between the vapor pressure (p) and the temperature (T) of pure substances.
    """

    m_def = Section(categories=[PDIMBECategory])
    name = Quantity(
        type=str,
        description='FILL',
        a_eln=ELNAnnotation(component='StringEditQuantity', label='Substance Name'),
    )
    cas_number = Quantity(
        type=str,
        description='FILL',
        a_eln=ELNAnnotation(component='StringEditQuantity', label='CAS number'),
    )
    weight = Quantity(
        type=np.float64,
        description="""
        Weight of precursor and bubbler.
        Attention: Before weighing bubblers,
        all gaskets and corresponding caps must be attached!
        """,
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='gram',
        ),
        unit='kg',
    )
    weight_difference = Quantity(
        type=np.float64,
        description='Weight when the bubbler is exhausted.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='gram',
        ),
        unit='kg',
    )
    total_comsumption = Quantity(
        type=np.float64,
        description='FILL DESCRIPTION.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='gram',
        ),
        unit='kg',
    )
    a_parameter = Quantity(
        type=np.float64,
        description='The A parameter of Antoine equation. Dimensionless.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='millimeter',
        ),
        unit='millimeter',
    )
    b_parameter = Quantity(
        type=np.float64,
        description='The B parameter of Antoine equation. Temperature units.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='celsius',
        ),
        unit='kelvin',
    )
    c_parameter = Quantity(
        type=np.float64,
        description='The C parameter of Antoine equation. Temperature units.',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='celsius',
        ),
        unit='kelvin',
    )
    information_sheet = Quantity(
        type=str,
        description='pdf files containing certificate and other documentation',
        a_browser={'adaptor': 'RawFileAdaptor'},
        a_eln=ELNAnnotation(
            component='FileEditQuantity',
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


class Cylinder(Geometry):
    """
    Class autogenerated from yaml schema.
    """

    m_def = Section()
    height = Quantity(
        type=np.float64,
        description='docs',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='nanometer',
        ),
        unit='nanometer',
    )
    radius = Quantity(
        type=np.float64,
        description='docs',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='millimeter',
        ),
        unit='millimeter',
    )
    lower_cap_radius = Quantity(
        type=np.float64,
        description='docs',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='millimeter',
        ),
        unit='millimeter',
    )
    upper_cap_radius = Quantity(
        type=np.float64,
        description='docs',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='millimeter',
        ),
        unit='millimeter',
    )
    cap_surface_area = Quantity(
        type=np.float64,
        description='docs',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='millimeter ** 2',
        ),
        unit='millimeter ** 2',
    )
    lateral_surface_area = Quantity(
        type=np.float64,
        description='docs',
        a_eln=ELNAnnotation(
            component='NumberEditQuantity',
            defaultDisplayUnit='millimeter ** 2',
        ),
        unit='millimeter ** 2',
    )


class SubstrateMbe(CrystallineSubstrate, EntryData):
    """
    Class autogenerated from yaml schema.
    """

    m_def = Section(
        label_quantity='lab_id',
        categories=[PDIMBECategory],
        label='Substrate',
        a_eln=ELNAnnotation(
            properties=SectionProperties(
                order=[
                    'name',
                    'tags',
                    'delivery_date',
                    'datetime',
                    'supplier',
                    'supplier_id',
                    'crystal_id',
                    'charge_id',
                    'polishing',
                    'lab_id',
                    'epi_ready',
                    'substrate_image',
                    'information_sheet',
                    'description',
                ],
            ),
            lane_width='600px',
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

    delivery_date = Quantity(
        type=Datetime,
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.DateEditQuantity,
        ),
    )
    crystal_id = Quantity(
        type=str,
        description='The ID of the crystal from which the current batch was cut, given by the manufacturer.',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
        label='Crystal ID',
    )
    charge_id = Quantity(
        type=str,
        description='The ID of the charge, or polishing batch, given by the manufacturer.',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
            label='Charge ID',
        ),
    )
    polishing = Quantity(
        type=MEnum(
            'Single-side',
            'Double-side',
            'Other',
        ),
        description='The polishing applied to the material.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.EnumEditQuantity,
        ),
    )
    epi_ready = Quantity(
        type=bool,
        description='Sample ready for epitaxy',
        a_eln=ELNAnnotation(
            component='BoolEditQuantity',
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

    def normalize(self, archive, logger):
        super(SubstrateMbe, self).normalize(archive, logger)

        if (
            self.supplier_id is not None
            and self.crystal_id is not None
            and self.charge_id is not None
            and self.lab_id is None
        ):
            self.lab_id = f'{self.supplier_id}_{self.crystal_id}_{self.charge_id}'
        elif (
            self.supplier_id is not None
            and self.crystal_id is not None
            and self.charge_id is not None
            and self.lab_id is not None
        ):
            logger.warning(
                "Error in SubstrateBatch: 'Substrate ID' is already given:\n"
                'supplier_id, charge_id, crystal_id are not used to compose it.'
            )
        elif (
            self.supplier_id is None
            and self.crystal_id is None
            and self.charge_id is None
            and self.lab_id is None
        ):
            logger.error(
                "Error in SubstrateBatch: 'Substrate ID' expected, but None found.\n"
                "Please provide 'supplier_id', 'crystal_id', and 'charge_id',"
                " or 'Substrate ID'."
            )


class SubstrateBatchMbe(SubstrateMbe, EntryData):
    """
    Class autogenerated from yaml schema.
    """

    m_def = Section(
        label_quantity='lab_id',
        categories=[PDIMBECategory],
        label='Substrate Batch',
        a_eln=ELNAnnotation(
            properties=SectionProperties(
                order=[
                    'name',
                    'delivery_date',
                    'datetime',
                    'supplier',
                    'supplier_id',
                    'crystal_id',
                    'charge_id',
                    'polishing',
                    'lab_id',
                    'number_of_substrates',
                    'epi_ready',
                    'substrate_image',
                    'information_sheet',
                    'description',
                ],
            ),
            lane_width='600px',
        ),
    )
    number_of_substrates = Quantity(
        type=int,
        description='The number of substrates in the batch.',
        a_eln=dict(component='NumberEditQuantity'),
    )
    substrates = SubSection(
        description="""
        The substrates in the batch.
        """,
        section_def=CompositeSystemReference,
        repeats=True,
    )

    def normalize(self, archive, logger):
        from nomad.datamodel import EntryArchive, EntryMetadata

        super(SubstrateBatchMbe, self).normalize(archive, logger)
        filetype = 'yaml'

        # if (
        #     self.supplier_id is not None
        #     and self.crystal_id is not None
        #     and self.charge_id is not None
        #     and self.lab_id is None
        # ):
        #     self.lab_id = f'{self.supplier_id}_{self.crystal_id}_{self.charge_id}'
        # elif (
        #     self.supplier_id is not None
        #     and self.crystal_id is not None
        #     and self.charge_id is not None
        #     and self.lab_id is not None
        # ):
        #     logger.warning(f"Error in SubstrateBatch: 'Substrate ID' is already given.")
        # elif (
        #     self.supplier_id is None
        #     and self.crystal_id is None
        #     and self.charge_id is None
        #     and self.lab_id is None
        # ):
        #     logger.error(
        #         f"Error in SubstrateBatch: 'Substrate ID' expected, but None found.\n"
        #         f"Please provide 'supplier_id', 'crystal_id', 'charge_id' and 'lab_id'."
        #     )

        if not self.number_of_substrates:
            logger.error(
                "Error in SubstrateBatch: 'number_of_substrates' expected, but None found."
            )
        if self.substrates:
            logger.error(
                f'Error in SubstrateBatch: No substrates expected,'
                f' but {len(self.substrates)} substrates given.'
                f' Remove the substrates and save again to generate substrates.'
            )
        generated_substrates = []
        if self.number_of_substrates:
            substrate_object = self.m_copy(deep=True)
            substrate_object.m_def = SubstrateMbe.m_def
            substrate_object.number_of_substrates = None
            for substrate_index in range(1, self.number_of_substrates + 1):
                child_name = self.lab_id if self.lab_id else self.name
                substrate_filename = (
                    f'{child_name}_{substrate_index}.Substrate.archive.{filetype}'
                )
                substrate_object.name = f'{child_name}_{substrate_index}'
                substrate_object.lab_id = f'{child_name}_{substrate_index}'
                substrate_archive = EntryArchive(
                    data=substrate_object,
                    m_context=archive.m_context,
                    metadata=EntryMetadata(upload_id=archive.m_context.upload_id),
                )
                create_archive(
                    substrate_archive.m_to_dict(),
                    archive.m_context,
                    substrate_filename,
                    filetype,
                    logger,
                )
                generated_substrates.append(
                    CompositeSystemReference(
                        name=substrate_object.name,
                        reference=f'../uploads/{archive.m_context.upload_id}/archive/{hash(archive.m_context.upload_id, substrate_filename)}#data',
                    ),
                )
            self.substrates = generated_substrates


class ThinFilmMbe(ThinFilm, EntryData):
    """
    Class autogenerated from yaml schema.
    """

    m_def = Section(
        label_quantity='lab_id',
        categories=[PDIMBECategory],
        label='ThinFilmMbe',
    )
    lab_id = Quantity(
        type=str,
        description='the Sample created in the current growth',
        a_tabular={'name': 'GrowthRun/Sample Name'},
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
            label='Grown Sample ID',
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
    test_quantities = Quantity(
        type=str,
        description='Test quantity',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )


class ThinFilmStackMbePDI(ThinFilmStack, EntryData):
    """
    Class autogenerated from yaml schema.
    """

    m_def = Section(
        label_quantity='lab_id',
        categories=[PDIMBECategory],
        label='ThinFilmStackMbe',
    )
    lab_id = Quantity(
        type=str,
        description='the Sample created in the current growth',
        a_tabular={'name': 'GrowthRun/Sample Name'},
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
            label='Grown Sample ID',
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
    parent_sample = SubSection(
        description="""
        the parent sample of the current sample.
        """,
        section_def=ThinFilmStackReference,
    )


class ThinFilmStackMbeReference(ThinFilmStackReference):
    """
    A section used for referencing a Grown Sample.
    """

    lab_id = Quantity(
        type=str,
        description='the Sample created in the current growth',
        a_tabular={'name': 'GrowthRun/Sample Name'},
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
            label='Grown Sample ID',
        ),
    )
    reference = Quantity(
        type=ThinFilmStackMbePDI,
        description='A reference to a NOMAD `ThinFilmStackMbe` entry.',
        a_eln=ELNAnnotation(
            component='ReferenceEditQuantity',
            label='ThinFilmStackMbe Reference',
        ),
    )

    def normalize(self, archive, logger: BoundLogger) -> None:
        """
        The normalizer for the `ThinFilmStackMbeReference` class.
        """
        super(ThinFilmStackMbeReference, self).normalize(archive, logger)


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
        label='MBE Experiment',
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
    precursors_preparation = SubSection(
        section_def=PrecursorsPreparationPDIReference,
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
