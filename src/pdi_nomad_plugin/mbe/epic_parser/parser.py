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
from time import perf_counter
import glob
from datetime import datetime
from zoneinfo import ZoneInfo
import pytz
import os
import pandas as pd
from epic_scraper.epicfileimport.epic_module import (
    epiclog_read,
    epiclog_read_batch,
    growth_time,
)
from nomad.datamodel.data import EntryData
from nomad.datamodel.datamodel import EntryArchive, EntryMetadata
from nomad.datamodel.metainfo.annotations import ELNAnnotation
from nomad.metainfo import Quantity, Section
from nomad.parsing import MatchingParser
from nomad.utils import hash

from nomad.datamodel.metainfo.basesections import (
    PubChemPureSubstanceSection,
)
from pdi_nomad_plugin.mbe.instrument import (
    InstrumentMbePDI,
    PlasmaSourcePDI,
    RfGeneratorHeater,
    RfGeneratorHeaterPower,
    SingleFilamentEffusionCell,
    DoubleFilamentEffusionCell,
    EffusionCellHeater,
    EffusionCellHeaterTemperature,
    EffusionCellHeaterPower,
    Port,
    SourcePDI,
)
from pdi_nomad_plugin.mbe.processes import (
    ExperimentMbePDI,
    GrowthMbePDI,
    GrowthStepMbePDI,
    GrowthMbePDIReference,
    SampleParametersMbe,
    SubstrateHeaterTemperature,
    SubstrateHeaterPower,
)
from pdi_nomad_plugin.utils import (
    create_archive,
    fill_quantity,
    get_hash_ref,
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
        upload_path = f"{mainfile.split('raw/')[0]}raw/"
        folder_name = mainfile.split('/')[-2]
        folder_path = f'{upload_path}{folder_name}/'
        xlsx = pd.ExcelFile(mainfile)

        # "MBE config files" sheet
        config_sheet = pd.read_excel(
            xlsx,
            'MBE config files',
            comment='#',
        )
        config_sheet.columns = config_sheet.columns.str.strip()

        # "MBE sources" sheet
        sources_sheet = pd.read_excel(
            xlsx,
            'MBE sources',
            comment='#',
        )
        sources_sheet.columns = sources_sheet.columns.str.strip()

        # reading Messages.txt
        # TODO so far, nothing is done with this metadata
        if config_sheet['messages'][0]:
            messages_df = epiclog_read(f"{folder_path}{config_sheet['messages'][0]}")
            growth_events = growth_time(messages_df)
            for line in growth_events.iterrows():
                if line[1]['to'] == 'GC':
                    growth_object = line[1][
                        'object'
                    ]  # check TODO with Oliver which ID to write
                    growth_starttime = line[0]
                if line[1]['from'] == 'GC':
                    growth_endtime = line[0]
                    growth_duration = growth_endtime - growth_starttime
                    print(
                        f'Detected growth of {growth_object} started at {growth_starttime} and ended at {growth_endtime} with a duration of {growth_duration}'
                    )

        # filenames
        instrument_filename = f'{data_file}.InstrumentMbePDI.archive.{filetype}'
        process_filename = f'{data_file}.GrowthMbePDI.archive.{filetype}'
        experiment_filename = f'{data_file}.ExperimentMbePDI.archive.{filetype}'

        # filling in the sources objects list
        sources_list = []
        port_list = []
        for sources_index, sources_row in sources_sheet.iterrows():
            source_object = None
            if sources_row['source type'] == 'PLASMA':
                # TODO check if file exists, everywhere
                forward_power = epiclog_read(
                    f"{folder_path}{sources_row['f power']}.txt"
                )
                reflected_power = epiclog_read(
                    f"{folder_path}{sources_row['r power']}.txt"
                )
                source_object = PlasmaSourcePDI()
                source_object.vapor_source = RfGeneratorHeater()
                source_object.vapor_source.forward_power = RfGeneratorHeaterPower()
                source_object.vapor_source.reflected_power = RfGeneratorHeaterPower()
                source_object.type = 'RF plasma source (PLASMA)'
                source_object.vapor_source.forward_power.value = forward_power.values
                source_object.vapor_source.forward_power.time = list(
                    forward_power.index
                )
                source_object.vapor_source.reflected_power.value = (
                    reflected_power.values
                )
                source_object.vapor_source.reflected_power.time = list(
                    reflected_power.index
                )
                # TODO fill in dissipated power as the difference between forward and reflected power
            if sources_row['source type'] == 'SFC':
                sfc_temperature = epiclog_read(
                    f"{folder_path}{sources_row['temp mv']}.txt"
                )
                sfc_power = epiclog_read(f"{folder_path}{sources_row['temp wop']}.txt")
                source_object = SingleFilamentEffusionCell()
                source_object.vapor_source = EffusionCellHeater()
                source_object.vapor_source.temperature = EffusionCellHeaterTemperature()
                source_object.vapor_source.power = EffusionCellHeaterPower()
                source_object.type = 'Single filament effusion cell (SFC)'
                source_object.vapor_source.temperature.value = sfc_temperature.values
                source_object.vapor_source.temperature.time = list(
                    sfc_temperature.index
                )
                source_object.vapor_source.power.value = sfc_power.values
                source_object.vapor_source.power.time = list(sfc_power.index)
            if sources_row['source type'] == 'DFC':
                dfc_temperature = epiclog_read(
                    f"{folder_path}{sources_row['temp mv']}.txt"
                )
                dfc_power = epiclog_read(f"{folder_path}{sources_row['temp wop']}.txt")
                dfc_hl_temperature = epiclog_read(
                    f"{folder_path}{sources_row['hl temp mv']}.txt"
                )
                dfc_hl_power = epiclog_read(
                    f"{folder_path}{sources_row['hl temp wop']}.txt"
                )
                source_object = DoubleFilamentEffusionCell()
                source_object.vapor_source = EffusionCellHeater()
                source_object.vapor_source.temperature = EffusionCellHeaterTemperature()
                source_object.vapor_source.power = EffusionCellHeaterPower()
                source_object.vapor_source_hot_lip = EffusionCellHeater()
                source_object.vapor_source_hot_lip.temperature = (
                    EffusionCellHeaterTemperature()
                )
                source_object.vapor_source_hot_lip.power = EffusionCellHeaterPower()
                source_object.type = 'Double filament effusion cell (DFC)'
                source_object.vapor_source.temperature.value = dfc_temperature.values
                source_object.vapor_source.temperature.time = list(
                    dfc_temperature.index
                )
                source_object.vapor_source.power.value = dfc_power.values
                source_object.vapor_source.power.time = list(dfc_power.index)
                source_object.vapor_source_hot_lip.temperature.value = (
                    dfc_hl_temperature.values
                )
                source_object.vapor_source_hot_lip.temperature.time = list(
                    dfc_hl_temperature.index
                )
                source_object.vapor_source_hot_lip.power.value = dfc_hl_power.values
                source_object.vapor_source_hot_lip.power.time = list(dfc_hl_power.index)

            # fill in quantities common to all sources
            # and create Source objects and Port objects lists
            if source_object:
                source_name = (
                    str(fill_quantity(sources_row, 'source type'))
                    + '_'
                    + str(fill_quantity(sources_row, 'source material'))
                )
                source_object.name = source_name
                # Define a list of tuples containing
                # the columnd header of the xlsx sheet
                # and the corresponding attribute name
                keys_and_attributes = [
                    ('primary flux species', 'primary_flux_species'),
                    ('secondary flux species', 'secondary_flux_species'),
                    ('source material', 'material'),
                ]
                for key, attribute in keys_and_attributes:
                    if sources_row[key]:
                        substances = sources_row[key].split('+')
                        substance_objs = [
                            PubChemPureSubstanceSection(name=substance)
                            for substance in substances
                        ]
                        setattr(source_object, attribute, substance_objs)
                if sources_row['date'] and sources_row['time']:
                    source_object.datetime = datetime.combine(
                        datetime.strptime(
                            sources_row['date'],
                            '%d.%m.%y',
                        ),
                        datetime.strptime(sources_row['time'], '%H:%M:%S').time(),
                    ).replace(tzinfo=ZoneInfo('Europe/Berlin'))

                port_object = Port()
                port_object.name = source_name
                port_object.port_number = fill_quantity(sources_row, 'port number')
                port_object.flange_diameter = fill_quantity(sources_row, 'diameter')
                port_object.flange_to_substrate_distance = fill_quantity(
                    sources_row, 'distance'
                )
                port_object.theta = fill_quantity(sources_row, 'theta')
                port_object.phi = fill_quantity(sources_row, 'phi')
                port_list.append(port_object)

                source_object.port = f'../uploads/{archive.m_context.upload_id}/archive/{hash(archive.m_context.upload_id, instrument_filename)}#data/port_list/{sources_index}'

                sources_list.append(source_object)

            # filling in growth process archive
            if sources_row['source type'] == 'SUB':
                substrate_temperature = epiclog_read(
                    f"{folder_path}{sources_row['temp mv']}.txt"
                )
                substrate_power = epiclog_read(
                    f"{folder_path}{sources_row['temp wop']}.txt"
                )
                process_data = GrowthMbePDI()
                process_data.name = f'{data_file} growth'
                process_data.steps = [GrowthStepMbePDI()]
                process_data.steps[0].sample_parameters = [SampleParametersMbe()]
                process_data.steps[0].sample_parameters[
                    0
                ].substrate_temperature = SubstrateHeaterTemperature()
                process_data.steps[0].sample_parameters[
                    0
                ].substrate_power = SubstrateHeaterPower()

                process_data.steps[0].sources = sources_list
                process_data.steps[0].sample_parameters[
                    0
                ].substrate_temperature.value = substrate_temperature.values
                process_data.steps[0].sample_parameters[
                    0
                ].substrate_temperature.time = list(substrate_temperature.index)
                process_data.steps[0].sample_parameters[
                    0
                ].substrate_power.value = substrate_power.values
                process_data.steps[0].sample_parameters[0].substrate_power.time = list(
                    substrate_power.index
                )

        # creating instrument archive
        if archive.m_context.raw_path_exists(instrument_filename):
            print(f'Instrument archive already exists: {instrument_filename}')
        else:
            instrument_data = InstrumentMbePDI()
            instrument_data.name = f'{data_file} instrument'
            instrument_data.port_list = port_list

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

        # list files in folder:
        # found_files = glob.glob(os.path.join(folder_path, '*.txt'))


class ParserEpicPDI(MatchingParser):
    def parse(self, mainfile: str, archive: EntryArchive, logger) -> None:
        data_file = mainfile.split('/')[-1]
        folder_name = mainfile.split('/')[-2]
        upload_path = f"{mainfile.split('raw/')[0]}raw/"
        dataframe_list = epiclog_read_batch(folder_name, upload_path)
        filetype = 'yaml'

        print(dataframe_list)

        archive.data = RawFileEPIC(name=data_file, epic_file=mainfile)
        archive.metadata.entry_name = data_file.replace('.txt', '')
