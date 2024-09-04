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
import pandas as pd
from epic_scraper.epicfileimport.epic_module import (
    epiclog_read_batch,
)
from nomad.datamodel.data import EntryData
from nomad.datamodel.datamodel import EntryArchive, EntryMetadata
from nomad.datamodel.metainfo.annotations import ELNAnnotation
from nomad.metainfo import Quantity, Section
from nomad.parsing import MatchingParser
from nomad.utils import hash

from pdi_nomad_plugin.mbe.instrument import (
    InstrumentMbePDI,
    PlasmaSourcePDI,
)
from pdi_nomad_plugin.mbe.schema import (
    ExperimentMbePDI,
    GrowthMbePDI,
    GrowthMbePDIReference,
)
from pdi_nomad_plugin.utils import (
    create_archive,
)


class RawFileConfigurationExcel(EntryData):
    m_def = Section(a_eln=None, label='Raw File Config Excel')
    name = Quantity(
        type=str,
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    excel_file = Quantity(
        type=str,
        a_eln=ELNAnnotation(
            component='FileEditQuantity',
        ),
        a_browser={'adaptor': 'RawFileAdaptor'},
        description='Configuration Excel file',
    )


class RawFileEPIC(EntryData):
    m_def = Section(a_eln=None, label='Raw File EPIC')
    name = Quantity(
        type=str,
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    epic_file = Quantity(
        type=str,
        a_eln=ELNAnnotation(
            component='FileEditQuantity',
        ),
        a_browser={'adaptor': 'RawFileAdaptor'},
        description='EPIC log file list',
    )


class ParserConfigurationMbePDI(MatchingParser):
    def parse(self, mainfile: str, archive: EntryArchive, logger) -> None:
        filetype = 'yaml'
        data_file = mainfile.split('/')[-1]
        data_file_with_path = mainfile.split('raw/')[-1]
        xlsx = pd.ExcelFile(mainfile)

        # "MBE sources" sheet
        sources_file = pd.read_excel(
            xlsx,
            'MBE sources',
            comment='#',
        )
        sources_file.columns = sources_file.columns.str.strip()

        sources = []
        for sources_index, sources_row in sources_file.iterrows():
            if sources_row['source type'] == 'PLASMA':
                sources.append(
                    PlasmaSourcePDI(
                        epic_loop=sources_row['EPIC_loop'],
                    )
                )

        # creating instrument archive
        instrument_filename = f'{data_file}.InstrumentMbePDI.archive.{filetype}'
        if archive.m_context.raw_path_exists(instrument_filename):
            print(f'Instrument archive already exists: {instrument_filename}')
        else:
            instrument_data = InstrumentMbePDI(
                name=f'{data_file} instrument',
                sources=sources,
            )
            instrument_archive = EntryArchive(
                data=instrument_data if instrument_data else InstrumentMbePDI(),
                # m_context=archive.m_context,
                metadata=EntryMetadata(upload_id=archive.m_context.upload_id),
            )
            create_archive(
                instrument_archive.m_to_dict(),
                archive.m_context,
                instrument_filename,
                filetype,
                logger,
            )

        # creating process archive
        process_data = GrowthMbePDI(
            name=f'{data_file} process',
        )
        process_filename = f'{data_file}.GrowthMbePDI.archive.{filetype}'
        if archive.m_context.raw_path_exists(process_filename):
            print(f'Process archive already exists: {process_filename}')
        else:
            process_archive = EntryArchive(
                data=process_data if process_data else GrowthMbePDI(),
                # m_context=archive.m_context,
                metadata=EntryMetadata(upload_id=archive.m_context.upload_id),
            )
            create_archive(
                process_archive.m_to_dict(),
                archive.m_context,
                process_filename,
                filetype,
                logger,
            )

        # creating experiment archive
        experiment_filename = f'{data_file}.ExperimentMbePDI.archive.{filetype}'
        if archive.m_context.raw_path_exists(experiment_filename):
            print(f'Experiment archive already exists: {experiment_filename}')
        else:
            experiment_data = ExperimentMbePDI(
                name=f'{data_file} experiment',
                growth_run=GrowthMbePDIReference(
                    reference=f'../uploads/{archive.m_context.upload_id}/archive/{hash(archive.m_context.upload_id, process_filename)}#data',
                ),
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
        archive.data = RawFileEPIC(
            name=data_file,
            epic_file=mainfile,
        )
        archive.metadata.entry_name = data_file.replace('.txt', '')


class ParserEpicPDI(MatchingParser):
    def parse(self, mainfile: str, archive: EntryArchive, logger) -> None:
        data_file = mainfile.split('/')[-1]
        folder_name = mainfile.split('/')[-2]
        data_path = f"{mainfile.split('raw/')[0]}raw/"
        dataframe_list = epiclog_read_batch(folder_name, data_path)
        filetype = 'yaml'

        print(dataframe_list)

        archive.data = RawFileEPIC(name=data_file, epic_file=mainfile)
        archive.metadata.entry_name = data_file.replace('.txt', '')
