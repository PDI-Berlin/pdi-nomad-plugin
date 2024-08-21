from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


import numpy as np
from nomad.config import config
from nomad.datamodel.data import EntryData, EntryDataCategory
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.datamodel.metainfo.basesections import (
    CompositeSystemReference,
    Process,
)
from nomad.metainfo import (
    Category,
    Quantity,
    Reference,
    SchemaPackage,
    Section,
    SectionProxy,
    SubSection,
)
from nomad.utils import hash
from nomad_material_processing import (
    Geometry,
)

from nomad_material_processing.general import (
    SubstrateReference,
    Geometry,
    Recipe,
    Etching,
    Annealing,
    AnnealingRecipe,
    Cleaning,
    CleaningRecipe,
    Etching,
    EtchingRecipe,
    Recipe,
)

from pdi_nomad_plugin.utils import create_archive

configuration = config.get_plugin_entry_point('pdi_nomad_plugin.general:schema')

m_package = SchemaPackage()


class PDICategory(EntryDataCategory):
    m_def = Category(label='PDI', categories=[EntryDataCategory])


class PDIMBECategory(EntryDataCategory):
    m_def = Category(label='PDI MBE', categories=[EntryDataCategory, PDICategory])


class EtchingPDI(Etching):
    """
    Selectively remove material from a surface using chemical or physical processes
    to create specific patterns or structures.
    """

    m_def = Section(
        label='Etching',
        links=['http://purl.obolibrary.org/obo/CHMO_0001558'],
        categories=[PDICategory],
    )


class EtchingRecipePDI(EtchingRecipe):
    """
    A recipe for selectively remove material from a surface using chemical or physical processes
    to create specific patterns or structures.
    """

    m_def = Section(
        label='EtchingRecipe',
        links=['http://purl.obolibrary.org/obo/CHMO_0001558'],
        categories=[PDICategory],
    )


class AnnealingRecipePDI(AnnealingRecipe):
    """
    A recipe for the process of heating a material to a specific temperature for a specific time.
    """

    m_def = Section(
        label='AnnealingRecipe',
        links=['http://purl.obolibrary.org/obo/CHMO_0001465'],
        categories=[PDICategory],
    )


class CleaningRecipePDI(CleaningRecipe):
    """
    A recipe for the process of removing contaminants from a surface.
    """

    m_def = Section(
        label='CleaningRecipe',
        categories=[PDICategory],
    )


class AnnealingPDI(Annealing):
    """
    Class autogenerated from yaml schema.
    """

    m_def = Section(
        label='Annealing',
        links=['http://purl.obolibrary.org/obo/CHMO_0001465'],
        categories=[PDICategory],
    )


class CleaningPDI(Cleaning):
    """
    Class autogenerated from yaml schema.
    """

    m_def = Section(
        label='Cleaning',
        categories=[PDICategory],
    )


class BackSideCoatingPDI(Process, EntryData):
    """
    Coating of the back side of a substrate.
    """

    m_def = Section(
        label='BackSideCoating',
        a_eln={'hide': ['steps']},
        categories=[PDICategory],
    )
    recipe = Quantity(
        type=Reference(SectionProxy('BackSideCoatingRecipePDI')),
        description=""" The recipe used for the process. If a recipe is found,
           all the data is copied from the Recipe within the Process.
           """,
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.ReferenceEditQuantity,
        ),
    )
    temperature = Quantity(
        type=np.float64,
        description='The temperature of the annealing process.',
        a_eln={'component': 'NumberEditQuantity', 'defaultDisplayUnit': 'celsius'},
        unit='celsius',
    )
    duration = Quantity(
        type=np.float64,
        description='The elapsed time since the annealing process started.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='minute'
        ),
        unit='second',
    )
    coating_reagents = SubSection(
        section_def=CompositeSystemReference,
    )


class BackSideCoatingRecipePDI(BackSideCoatingPDI, Recipe, EntryData):
    """
    A Recipe for a back side coating process.
    """

    m_def = Section(
        label='BackSideCoatingRecipe',
        a_eln={'hide': ['datetime', 'samples']},
    )


class SampleCutPDI(Process, EntryData):
    """
    An Activity that can be used for cutting a sample in multiple ones.
    """

    m_def = Section(
        a_eln={'hide': ['steps', 'samples', 'instruments']},
        label='Sample Cut',
        categories=[PDICategory],
    )
    number_of_samples = Quantity(
        type=int,
        description='The number of samples generated from this "Sample Cut" Task.',
        a_eln=dict(component='NumberEditQuantity'),
    )
    image = Quantity(
        type=str,
        description='A photograph or image of the substrate.',
        a_browser={'adaptor': 'RawFileAdaptor'},
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.FileEditQuantity,
        ),
    )
    children_geometry = SubSection(
        section_def=Geometry,
        description='Section containing the geometry of the substrate.',
    )
    parent_sample = SubSection(
        description="""
        The parent sample that is going to be cut.
        """,
        section_def=CompositeSystemReference,
    )
    children_samples = SubSection(
        description="""
        The children samples that are going to be created.
        """,
        section_def=CompositeSystemReference,
        repeats=True,
    )

    def normalize(self, archive, logger):
        from nomad.datamodel import EntryArchive, EntryMetadata

        super(SampleCutPDI, self).normalize(archive, logger)
        filetype = 'yaml'
        if not self.number_of_samples:
            logger.error(
                "Error in SampleCut: 'number_of_samples' expected, but None found."
            )
        if not self.parent_sample:
            logger.error(
                "Error in SampleCut: 'parent_sample' expected, but None found."
            )
        if self.children_samples:
            logger.error(
                f'Error in SampleCut: No children samples expected,'
                f' but {len(self.children_samples)} children samples given.'
                f' Remove the children samples and save again to generate children.'
            )
        generated_samples = []
        if self.parent_sample and self.number_of_samples:
            children_object = self.parent_sample.reference.m_copy(deep=True)
            if self.children_geometry:
                children_object.geometry = self.children_geometry
            else:
                children_object.geometry = None
            for sample_index in range(self.number_of_samples):
                child_name = (
                    self.parent_sample.reference.lab_id
                    if self.parent_sample.reference.lab_id
                    else self.parent_sample.reference.name
                )
                children_filename = (
                    f'{child_name}_{sample_index}.CompositeSystem.archive.{filetype}'
                )
                children_object.name = f'{child_name}_{sample_index}'
                children_object.lab_id = f'{child_name}_{sample_index}'
                children_archive = EntryArchive(
                    data=children_object,
                    m_context=archive.m_context,
                    metadata=EntryMetadata(upload_id=archive.m_context.upload_id),
                )
                create_archive(
                    children_archive.m_to_dict(),
                    archive.m_context,
                    children_filename,
                    filetype,
                    logger,
                )
                generated_samples.append(
                    CompositeSystemReference(
                        name=children_object.name,
                        reference=f'../uploads/{archive.m_context.upload_id}/archive/{hash(archive.m_context.upload_id, children_filename)}#data',
                    ),
                )
            self.children_samples = generated_samples


m_package.__init_metainfo__()
