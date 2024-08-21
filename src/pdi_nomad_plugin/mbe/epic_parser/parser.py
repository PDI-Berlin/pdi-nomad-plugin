#
# Copyright The NOMAD Authors.
#
# This file is part of NOMAD. See https://nomad-lab.eu for further info.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


from epic_scraper.epicfileimport.epic_module import epiclog_read_batch
from nomad.datamodel.data import EntryData
from nomad.datamodel.datamodel import EntryArchive, EntryMetadata
from nomad.datamodel.metainfo.annotations import ELNAnnotation
from nomad.metainfo import Quantity, Section
from nomad.parsing import MatchingParser
from nomad.utils import hash

from nomad.datamodel.metainfo.basesections import (
    SystemComponent,
    CompositeSystemReference,
    PubChemPureSubstanceSection,
    ElementalComposition,
    PureSubstanceComponent,
    PureSubstanceSection,
    ExperimentStep,
)

from nomad_material_processing.general import (
    SubstrateReference,
    ThinFilmReference,
    ThinFilmStackReference,
    Parallelepiped,
    SubstrateCrystalProperties,
    Miscut,
    Dopant,
)
from nomad_material_processing.vapor_deposition.general import (
    Pressure,
    VolumetricFlowRate,
    Temperature,
)

from nomad_material_processing.vapor_deposition.cvd.general import (
    PartialVaporPressure,
    BubblerEvaporator,
    Rotation,
    BubblerSource,
    GasCylinderSource,
    GasCylinderEvaporator,
    PushPurgeGasFlow,
    MistSource,
    MistEvaporator,
    ComponentConcentration,
)

from pdi_nomad_plugin.general.schema import (
    SampleCutPDI,
)

from pdi_nomad_plugin.characterization.schema import (
    AFMmeasurement,
    AFMresults,
)

from pdi_nomad_plugin.mbe.schema import (
    ExperimentMbePDI,
)
from pdi_nomad_plugin.utils import (
    create_archive,
)


class RawFileGrowthRun(EntryData):
    m_def = Section(a_eln=None, label='Raw File Growth Run')
    name = Quantity(
        type=str,
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    growth_run = Quantity(
        type=ExperimentMbePDI,
        # a_eln=ELNAnnotation(
        #     component="ReferenceEditQuantity",
        # ),
        shape=['*'],
    )


class ParserEpicPDI(MatchingParser):
    def parse(self, mainfile: str, archive: EntryArchive, logger) -> None:
        data_file = mainfile.split('/')[-1]
        folder_name = mainfile.split('/')[-2]
        data_path = f"{mainfile.split('raw/')[0]}raw/"
        dataframe_list = epiclog_read_batch(folder_name, data_path)
        filetype = 'yaml'

        print(dataframe_list)
        # creating experiment archive
        experiment_filename = f'a00000.ExperimentMbePDI.archive.{filetype}'
        experiment_data = ExperimentMbePDI(
            name='experiment',
            method='MBE 2 experiment',
        )
        experiment_archive = EntryArchive(
            data=experiment_data if experiment_data else ExperimentMbePDI(),
            # m_context=archive.m_context,
            metadata=EntryMetadata(upload_id=archive.m_context.upload_id),
        )
        create_archive(
            experiment_archive.m_to_dict(),
            archive.m_context,
            experiment_filename,
            filetype,
            logger,
        )

        archive.data = RawFileGrowthRun(
            name=data_file,
            growth_run=[
                f'../uploads/{archive.m_context.upload_id}/archive/{hash(archive.m_context.upload_id, experiment_filename)}#data'
            ],
        )
        archive.metadata.entry_name = data_file + 'raw file'
