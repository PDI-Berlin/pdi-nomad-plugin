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
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Union, Dict, Iterable

import pandas as pd
from epic_scraper.epicfileimport.epic_module import (
    epiclog_read,
    growth_time,
)
from nomad.units import ureg
from nomad.datamodel.data import EntryData
from nomad.datamodel.datamodel import EntryArchive, EntryMetadata
from nomad.datamodel.metainfo.annotations import ELNAnnotation
from nomad.datamodel.metainfo.basesections import (
    PubChemPureSubstanceSection,
    PureSubstanceSection,
)
from nomad.metainfo import Quantity, Section
from nomad.parsing import MatchingParser
from nomad.utils import hash

from pdi_nomad_plugin.general.schema import EtchingPDI
from pdi_nomad_plugin.mbe.instrument import (
    DoubleFilamentEffusionCell,
    EffusionCellHeater,
    EffusionCellHeaterPower,
    EffusionCellHeaterTemperature,
    InstrumentMbePDI,
    PlasmaSourcePDI,
    Port,
    RfGeneratorHeater,
    RfGeneratorHeaterPower,
    SingleFilamentEffusionCell,
    ImpingingFluxPDI,
)
from pdi_nomad_plugin.mbe.processes import (
    ExperimentMbePDI,
    GrowthMbePDI,
    GrowthMbePDIReference,
    GrowthStepMbePDI,
    SampleParametersMbe,
    SubstrateHeaterPower,
    SubstrateHeaterTemperature,
)
from pdi_nomad_plugin.utils import (
    create_archive,
    fill_quantity,
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


class ParserEpicPDI(MatchingParser):
    def is_mainfile(
        self,
        filename: str,
        mime: str,
        buffer: bytes,
        decoded_buffer: str,
        compression: str = None,
    ) -> Union[bool, Iterable[str]]:
        is_mainfile = super().is_mainfile(
            filename=filename,
            mime=mime,
            buffer=buffer,
            decoded_buffer=decoded_buffer,
            compression=compression,
        )
        if is_mainfile:
            try:
                # try to resolve mainfile keys from parser
                mainfile_keys = ['process']
                self.creates_children = True
                return mainfile_keys
            except Exception:
                return is_mainfile
        return is_mainfile

    def parse(
        self,
        mainfile: str,
        archive: EntryArchive,
        child_archives: dict(process=EntryArchive),
        logger,
    ) -> None:
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
                    growth_id = line[1]['object']
                    growth_starttime = line[0]
                if line[1]['from'] == 'GC':
                    growth_endtime = line[0]
                    growth_duration = growth_endtime - growth_starttime
                    logger.info(
                        f'Detected growth of {growth_id} started at {growth_starttime} and ended at {growth_endtime} with a duration of {growth_duration}'
                    )

        # reading Fitting.txt
        if config_sheet['flux calibration'][0]:
            with open(
                f"{folder_path}{config_sheet['flux calibration'][0]}",
                'r',
                encoding='utf-8',
            ) as file:
                fitting = {}
                for line in file:
                    if '#' in line:
                        epic_loop = line.split('#')[1].strip()
                        fitting[epic_loop] = {}
                        for _ in range(4):
                            key, value = file.readline().split('=')
                            fitting[epic_loop][key] = value

        # filenames
        instrument_filename = f'{data_file}.InstrumentMbePDI.archive.{filetype}'
        process_filename = f'{data_file}.GrowthMbePDI.archive.{filetype}'
        experiment_filename = f'{data_file}.ExperimentMbePDI.archive.{filetype}'

        # etching_filename = f'TEST.InstrumentMbePDI.archive.{filetype}'
        # etching_data = EtchingPDI()

        # etching_archive = EntryArchive(
        #     data=etching_data if etching_data else EtchingPDI(),
        #     # m_context=archive.m_context,
        #     metadata=EntryMetadata(upload_id=archive.m_context.upload_id),
        # )
        # create_archive(
        #     etching_archive.m_to_dict(),
        #     archive.m_context,
        #     etching_filename,
        #     filetype,
        #     logger,
        # )

        # filling in the sources objects list
        sources_list = []
        port_list = []
        child_archives['process'].data = GrowthMbePDI()
        child_archives['process'].data.steps = [GrowthStepMbePDI()]
        child_archives['process'].data.steps[0].sources = []
        for sources_index, sources_row in sources_sheet.iterrows():
            if sources_row['source type'] == 'PLASMA':
                # TODO check if file exists, everywhere
                # read raw files
                forward_power = epiclog_read(
                    f"{folder_path}{sources_row['f power']}.txt"
                )
                reflected_power = epiclog_read(
                    f"{folder_path}{sources_row['r power']}.txt"
                )
                f_power_unit = sources_row['f power unit']
                r_power_unit = sources_row['r power unit']

                # instantiate objects
                child_archives['process'].data.steps[0].sources.append(
                    PlasmaSourcePDI()
                )
                source_object = (
                    child_archives['process'].data.steps[0].sources[sources_index]
                )
                source_object.vapor_source = RfGeneratorHeater()
                source_object.vapor_source.forward_power = RfGeneratorHeaterPower()
                source_object.vapor_source.reflected_power = RfGeneratorHeaterPower()

                # fill in quantities
                source_object.type = 'RF plasma source (PLASMA)'
                source_object.vapor_source.forward_power.value = ureg.Quantity(
                    forward_power.values.ravel(), ureg(f_power_unit)
                )
                source_object.vapor_source.forward_power.time = np.array(
                    (forward_power.index - growth_starttime).total_seconds()
                )
                source_object.vapor_source.reflected_power.value = ureg.Quantity(
                    reflected_power.values.ravel(), ureg(r_power_unit)
                )
                source_object.vapor_source.reflected_power.time = np.array(
                    (reflected_power.index - growth_starttime).total_seconds()
                )

                # TODO fill in dissipated power as the difference between forward and reflected power
            if (
                sources_row['source type'] == 'SFC'
                or sources_row['source type'] == 'DFC'
            ):
                # read raw files
                sfc_temperature = epiclog_read(
                    f"{folder_path}{sources_row['temp mv']}.txt"
                )
                sfc_power = epiclog_read(f"{folder_path}{sources_row['temp wop']}.txt")

                temp_mv_unit = (
                    '°C'
                    if sources_row['temp mv unit'] == 'C'
                    else sources_row['temp mv unit']
                )

                # instantiate objects
                child_archives['process'].data.steps[0].sources.append(
                    SingleFilamentEffusionCell()
                    if sources_row['source type'] == 'SFC'
                    else DoubleFilamentEffusionCell()
                )
                source_object = (
                    child_archives['process'].data.steps[0].sources[sources_index]
                )
                source_object.impinging_flux = [ImpingingFluxPDI()]
                source_object.vapor_source = EffusionCellHeater()
                source_object.vapor_source.temperature = EffusionCellHeaterTemperature()
                source_object.vapor_source.power = EffusionCellHeaterPower()

                # fill in quantities
                source_object.type = (
                    'Single filament effusion cell (SFC)'
                    if sources_row['source type'] == 'SFC'
                    else 'Double filament effusion cell (DFC)'
                )
                source_object.vapor_source.temperature.value = ureg.Quantity(
                    sfc_temperature.values.ravel(), ureg(temp_mv_unit)
                )
                mv_time = np.array(
                    (sfc_temperature.index - growth_starttime).total_seconds()
                )
                source_object.vapor_source.temperature.time = mv_time
                source_object.vapor_source.power.value = (
                    sfc_power.values.ravel()
                )  # TODO insert units
                source_object.vapor_source.power.time = np.array(
                    (sfc_power.index - growth_starttime).total_seconds()
                )

                if sources_row['EPIC loop']:
                    source_object.epic_loop = sources_row['EPIC loop']
                    if sources_row['EPIC loop'] in fitting.keys():
                        a_param, t0_param = fitting[sources_row['EPIC loop']][
                            'Coeff'
                        ].split(',')
                        bep_to_flux = fitting[sources_row['EPIC loop']]['BEPtoFlux']
                        temperature = source_object.vapor_source.temperature
                        # impinging_flux = (
                        #     float(bep_to_flux)
                        #     * float(a_param)
                        #     * np.exp(float(t0_param) / temperature)
                        # )
                        source_object.impinging_flux[0].bep_to_flux = ureg.Quantity(
                            float(bep_to_flux),
                            ureg('mol **-1 * meter ** -2 * second * pascal ** -1'),
                        )
                        source_object.impinging_flux[0].t_0_parameter = ureg.Quantity(
                            float(t0_param), ureg('°C')
                        )
                        source_object.impinging_flux[0].a_parameter = float(a_param)
                        # source_object.impinging_flux[0].value = impinging_flux
                        # TODO include impinging flux in the source object
                        source_object.impinging_flux[
                            0
                        ].time = mv_time  # TODO insert hdf5 link

            if sources_row['source type'] == 'DFC':
                # read raw files
                dfc_hl_temperature = epiclog_read(
                    f"{folder_path}{sources_row['hl temp mv']}.txt"
                )
                dfc_hl_power = epiclog_read(
                    f"{folder_path}{sources_row['hl temp wop']}.txt"
                )
                hl_temp_mv_unit = (
                    '°C'
                    if sources_row['hl temp mv unit'] == 'C'
                    else sources_row['hl temp mv unit']
                )

                # instantiate objects
                source_object.vapor_source_hot_lip = EffusionCellHeater()
                source_object.vapor_source_hot_lip.temperature = (
                    EffusionCellHeaterTemperature()
                )

                # fill in quantities
                source_object.vapor_source_hot_lip.power = EffusionCellHeaterPower()
                source_object.vapor_source_hot_lip.temperature.value = ureg.Quantity(
                    dfc_hl_temperature.values, ureg(hl_temp_mv_unit)
                )
                source_object.vapor_source_hot_lip.temperature.time = np.array(
                    (dfc_hl_temperature.index - growth_starttime).total_seconds()
                )
                source_object.vapor_source_hot_lip.power.value = (
                    dfc_hl_power.values.ravel()
                )
                source_object.vapor_source_hot_lip.power.time = np.array(
                    (dfc_hl_power.index - growth_starttime).total_seconds()
                )
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
                        substances = str(sources_row[key]).split('+')
                        substance_objs = []
                        for substance in substances:
                            substance_objs = [
                                PureSubstanceSection(
                                    name=substance
                                )  # TODO insert here again PUBCHEM PubChemPureSubstanceSection(name=substance)
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

                # reference the instrument.port_list into the process.sources
                source_object.port = f'../uploads/{archive.m_context.upload_id}/archive/{hash(archive.m_context.upload_id, instrument_filename)}#data/port_list/{sources_index}'

            # filling in growth process archive
            if sources_row['source type'] == 'SUB':
                # read raw files
                substrate_temperature = epiclog_read(
                    f"{folder_path}{sources_row['temp mv']}.txt"
                )
                substrate_power = epiclog_read(
                    f"{folder_path}{sources_row['temp wop']}.txt"
                )

                # instantiate objects
                child_archives['process'].data.steps[0].sample_parameters = [
                    SampleParametersMbe()
                ]
                child_archives['process'].data.steps[0].sample_parameters[
                    0
                ].substrate_temperature = SubstrateHeaterTemperature()
                child_archives['process'].data.steps[0].sample_parameters[
                    0
                ].substrate_power = SubstrateHeaterPower()

                # fill in quantities
                child_archives[
                    'process'
                ].data.name = f'growth_{growth_id.replace("@", "_")}'
                child_archives['process'].data.steps[0].sample_parameters[
                    0
                ].substrate_temperature.value = ureg.Quantity(
                    substrate_temperature.values.ravel(), ureg(temp_mv_unit)
                )
                child_archives['process'].data.steps[0].sample_parameters[
                    0
                ].substrate_temperature.time = np.array(
                    (substrate_temperature.index - growth_starttime).total_seconds()
                )
                child_archives['process'].data.steps[0].sample_parameters[
                    0
                ].substrate_power.value = ureg.Quantity(
                    substrate_power.values.ravel(), ureg(temp_mv_unit)
                )
                child_archives['process'].data.steps[0].sample_parameters[
                    0
                ].substrate_power.time = np.array(
                    (substrate_power.index - growth_starttime).total_seconds()
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

        # creating experiment archive
        archive.data = ExperimentMbePDI(
            name=f'{data_file} experiment',
            # growth_run=GrowthMbePDIReference(
            #     reference=f'../uploads/{archive.m_context.upload_id}/archive/{hash(archive.m_context.upload_id, child_archives["process"].metadata.entry_name)}#data',
            # ),
        )
        # archive.metadata.entry_name = data_file.replace('.txt', '')

        # # old way of creating archives as raw files
        # # creating process archive
        # if archive.m_context.raw_path_exists(process_filename):
        #     print(f'Process archive already exists: {process_filename}')
        # else:
        #     process = EntryArchive(
        #         data=process_data if process_data else GrowthMbePDI(),
        #         # m_context=archive.m_context,
        #         metadata=EntryMetadata(upload_id=archive.m_context.upload_id),
        #     )
        #     create_archive(
        #         process.m_to_dict(),
        #         archive.m_context,
        #         process_filename,
        #         filetype,
        #         logger,
        #     )
