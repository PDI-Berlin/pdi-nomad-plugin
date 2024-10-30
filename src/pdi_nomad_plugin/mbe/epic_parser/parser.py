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
import os
from collections.abc import Iterable
from datetime import datetime
from typing import Union
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from epic_scraper.epicfileimport.epic_module import (
    growth_time,
)
from nomad.datamodel.datamodel import EntryArchive, EntryMetadata
from nomad.datamodel.metainfo.basesections import (
    PureSubstanceSection,
)
from nomad.parsing import MatchingParser
from nomad.units import ureg
from nomad.utils import hash

from pdi_nomad_plugin.characterization.schema import (
    PyrometerTemperature,
    Pyrometry,
)
from pdi_nomad_plugin.mbe.instrument import (
    DoubleFilamentEffusionCell,
    EffusionCellHeater,
    EffusionCellHeaterPower,
    EffusionCellHeaterTemperature,
    GasFlowPDI,
    ImpingingFluxPDI,
    InstrumentMbePDI,
    PlasmaSourcePDI,
    Port,
    RfGeneratorHeater,
    RfGeneratorHeaterPower,
    SingleFilamentEffusionCell,
    ColdLipEffusionCell,
    VolumetricFlowRatePDI,
)
from pdi_nomad_plugin.mbe.processes import (
    ExperimentMbePDI,
    GrowthMbePDI,
    GrowthMbePDIReference,
    GrowthStepMbePDI,
    InSituCharacterizationMbePDI,
    PyrometryReference,
    SampleParametersMbe,
    SubstrateHeaterPower,
    SubstrateHeaterTemperature,
)
from pdi_nomad_plugin.utils import (
    create_archive,
    epiclog_parse_timeseries,
    epiclog_read_handle_empty,
    fill_quantity,
)

timezone = 'Europe/Berlin'


def fill_datetime(date: pd.Series, time: pd.Series) -> datetime.date:
    return datetime.combine(
        datetime.strptime(
            date,
            '%d/%m/%Y',
        ),
        datetime.strptime(time, '%H:%M:%S').time(),
    ).replace(tzinfo=ZoneInfo(timezone))


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
                mainfile_keys = ['process', 'pyrometry']
                self.creates_children = True
                return mainfile_keys
            except Exception:
                return is_mainfile
        return is_mainfile

    def parse(
        self,
        mainfile: str,
        archive: EntryArchive,
        child_archives: dict(process=EntryArchive, pyrometry=EntryArchive),
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

        # "MBE gas mixing" sheet
        gasmixing_sheet = pd.read_excel(
            xlsx,
            'MBE gas mixing',
            comment='#',
        )
        gasmixing_sheet.columns = gasmixing_sheet.columns.str.strip()

        # "pyrometry config" sheet
        pyrometry_sheet = pd.read_excel(
            xlsx,
            'pyrometry config',
            comment='#',
        )
        pyrometry_sheet.columns = pyrometry_sheet.columns.str.strip()

        # reading Messages.txt
        growth_starttime = None
        growth_id = None
        if 'messages' in config_sheet and not config_sheet['messages'].empty:
            if pd.notna(config_sheet['messages'].iloc[0]):
                messages_df = epiclog_read_handle_empty(
                    folder_path, config_sheet, 'messages'
                )
                if messages_df is not None:
                    growth_events = growth_time(messages_df)
                    # found_start = False  # TODO remove this flag
                    for line in growth_events.iterrows():
                        if line[1]['to'] == 'GC':
                            growth_id = line[1]['object']
                            growth_starttime = line[0].tz_localize(timezone)
                        if line[1]['from'] == 'GC':
                            growth_endtime = line[0].tz_localize(timezone)
                            growth_duration = growth_endtime - growth_starttime
                            logger.info(
                                f'Detected growth of {growth_id} started at {growth_starttime} and ended at {growth_endtime} with a duration of {growth_duration}'
                            )
        exp_string = growth_id.replace('@', '_') if growth_id else None

        # reading Fitting.txt
        fitting = None
        if (
            'flux_calibration' in config_sheet
            and not config_sheet['flux_calibration'].empty
        ):
            file_path = f"{folder_path}{config_sheet['flux_calibration'][0]}"
            if pd.notna(config_sheet['flux_calibration'].iloc[0]) and os.path.exists(
                file_path
            ):
                with open(
                    file_path,
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

        # reading Shutters.txt
        shutters = None
        if 'shutters' in config_sheet and not config_sheet['shutters'].empty:
            file_path = f"{folder_path}{config_sheet['shutters'][0]}"
            if pd.notna(config_sheet['shutters'].iloc[0]) and os.path.exists(file_path):
                with open(
                    file_path,
                    encoding='utf-8',
                ) as file:
                    shutters = pd.read_csv(file, skiprows=2)

        # filenames
        instrument_filename = f'{data_file}.InstrumentMbePDI.archive.{filetype}'

        # read raw files
        epiclog_value, epiclog_time = epiclog_parse_timeseries(
            timezone,
            growth_starttime,
            folder_path,
            pyrometry_sheet,
            'temperature',
            'temperature_unit',
        )
        # instantiate objects
        child_archives['process'].data = GrowthMbePDI()
        child_archives['process'].data.steps = [GrowthStepMbePDI()]
        child_archives['process'].data.steps[0].sources = []
        child_archives['process'].data.steps[
            0
        ].in_situ_characterization = InSituCharacterizationMbePDI()
        child_archives['process'].data.steps[
            0
        ].in_situ_characterization.pyrometry = PyrometryReference()
        child_archives['pyrometry'].data = Pyrometry()
        child_archives['pyrometry'].data.pyrometer_temperature = PyrometerTemperature()

        # fill in quantities
        child_archives['pyrometry'].data.name = f'{exp_string} pyrometry'
        child_archives['pyrometry'].data.pyrometer_temperature.value = epiclog_value
        child_archives['pyrometry'].data.pyrometer_temperature.time = epiclog_time
        child_archives['process'].data.name = f'{exp_string} process'
        child_archives['process'].data.steps[
            0
        ].in_situ_characterization.pyrometry.reference = child_archives[
            'pyrometry'
        ].data

        # filling in the sources objects list
        port_list = []
        for sources_index, sources_row in sources_sheet.iterrows():
            if sources_row['source_type'] == 'PLASMA':
                # read raw files
                epiclog_value_f, epiclog_time_f = epiclog_parse_timeseries(
                    timezone,
                    growth_starttime,
                    folder_path,
                    sources_row,
                    'f_power',
                    'f_power_unit',
                )
                epiclog_value_r, epiclog_time_r = epiclog_parse_timeseries(
                    timezone,
                    growth_starttime,
                    folder_path,
                    sources_row,
                    'r_power',
                    'r_power_unit',
                )

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
                source_object.gas_flow = []

                # fill in quantities
                source_object.type = 'RF plasma source (PLASMA)'
                source_object.vapor_source.forward_power.value = epiclog_value_f
                source_object.vapor_source.forward_power.time = epiclog_time_f
                source_object.vapor_source.reflected_power.value = epiclog_value_r
                source_object.vapor_source.reflected_power.time = epiclog_time_r

                # TODO fill in dissipated power as the difference between forward and reflected power

                # fill the gas mixing in the plasma source:
                i = 0
                for gas_index in reversed(gasmixing_sheet.index):
                    gas_row = gasmixing_sheet.loc[
                        gas_index
                    ]  # this allows to loop in reverse order. Use .iterrows() instead

                    epiclog_value, epiclog_time = epiclog_parse_timeseries(
                        timezone,
                        growth_starttime,
                        folder_path,
                        gas_row,
                        'mfc_flow',
                        'mfc_flow_unit',
                    )
                    if gas_row['date'] and gas_row['time']:
                        gasmixing_datetime = fill_datetime(
                            gas_row['date'], gas_row['time']
                        )
                        if growth_starttime is None:
                            logger.warning(
                                'Growth start time not found. Possibly, Messages.txt file is missing.'
                            )
                        elif gasmixing_datetime > growth_starttime:
                            continue

                        print(f'this mixing was done at: {gasmixing_datetime}')
                        print(f'growth started at: {growth_starttime}')
                        source_object.gas_flow.append(
                            GasFlowPDI(flow_rate=VolumetricFlowRatePDI())
                        )
                        source_object.gas_flow[i].flow_rate.value = epiclog_value
                        source_object.gas_flow[i].flow_rate.time = epiclog_time
                        i += 1

                        # measurement_type ='Mass Flow Controller',
                        # gas=

            if (
                sources_row['source_type'] == 'SFC'
                or sources_row['source_type'] == 'DFC'
                or sources_row['source_type'] == 'CLC'
            ):
                # read raw files
                epiclog_value, epiclog_time = epiclog_parse_timeseries(
                    timezone,
                    growth_starttime,
                    folder_path,
                    sources_row,
                    'temp_mv',
                    'temp_mv_unit',
                )
                epiclog_value_p, epiclog_time_p = epiclog_parse_timeseries(
                    timezone,
                    growth_starttime,
                    folder_path,
                    sources_row,
                    'temp_wop',
                )

                # instantiate objects
                if sources_row['source_type'] == 'SFC':
                    child_archives['process'].data.steps[0].sources.append(
                        SingleFilamentEffusionCell()
                    )
                elif sources_row['source_type'] == 'DFC':
                    child_archives['process'].data.steps[0].sources.append(
                        DoubleFilamentEffusionCell()
                    )
                elif sources_row['source_type'] == 'CLC':
                    child_archives['process'].data.steps[0].sources.append(
                        ColdLipEffusionCell()
                    )
                source_object = (
                    child_archives['process'].data.steps[0].sources[sources_index]
                )
                source_object.impinging_flux = [ImpingingFluxPDI()]
                source_object.vapor_source = EffusionCellHeater()
                source_object.vapor_source.temperature = EffusionCellHeaterTemperature()
                source_object.vapor_source.power = EffusionCellHeaterPower()

                # fill in quantities
                if sources_row['source_type'] == 'SFC':
                    source_object.type = 'Single filament effusion cell (SFC)'
                if sources_row['source_type'] == 'DFC':
                    source_object.type = 'Double filament effusion cell (DFC)'
                if sources_row['source_type'] == 'CLC':
                    source_object.type = 'Cold lip cell (CLC)'

                source_object.vapor_source.temperature.value = epiclog_value
                source_object.vapor_source.temperature.time = epiclog_time
                source_object.vapor_source.power.value = epiclog_value_p
                source_object.vapor_source.power.time = epiclog_time_p

                if sources_row['EPIC_loop'] and fitting is not None:
                    source_object.epic_loop = sources_row['EPIC_loop']
                    if sources_row['EPIC_loop'] in fitting.keys():
                        a_param, t0_param = fitting[sources_row['EPIC_loop']][
                            'Coeff'
                        ].split(',')
                        bep_to_flux = fitting[sources_row['EPIC_loop']]['BEPtoFlux']
                        # TODO remove print statements after checking the impinging flux magnitude
                        print(a_param)
                        print(t0_param)
                        print(bep_to_flux)
                        with (
                            source_object.vapor_source.temperature.value as temperature
                        ):
                            print(temperature[:])
                            impinging_flux = (
                                float(bep_to_flux)
                                * float(a_param)
                                * np.exp(float(t0_param) / temperature[:])
                            )

                            # test
                            bep_test = float(a_param) * np.exp(
                                float(t0_param) / temperature[:]
                            )
                            print(f'BEP: {bep_test}')

                            # make shutter status a vector
                            shutter_vector = np.zeros(len(epiclog_time))
                            if shutters is not None:
                                for shutter_status in shutters.iterrows():
                                    if shutter_status[1][
                                        f"{sources_row['EPIC_loop']}_Sh"
                                    ]:
                                        for i in epiclog_time:
                                            if (
                                                epiclog_time
                                                < shutter_status["'Date&Time"]
                                            ):
                                                shutter_vector[i] = shutter_status[1][
                                                    f'{sources_row["EPIC_loop"]}_Sh'
                                                ]
                                            else:
                                                break
                                logger.info(
                                    f"The shutters file: {sources_row['EPIC_loop']}_Sh"
                                )
                                logger.info(
                                    f'This is the shutter vector: {shutter_vector}'
                                )

                        source_object.impinging_flux[0].bep_to_flux = ureg.Quantity(
                            float(bep_to_flux),
                            ureg('mol **-1 * meter ** -2 * second * pascal ** -1'),
                        )
                        source_object.impinging_flux[0].t_0_parameter = ureg.Quantity(
                            float(t0_param), ureg('°C')
                        )
                        source_object.impinging_flux[0].a_parameter = float(a_param)
                        source_object.impinging_flux[0].value = impinging_flux
                        source_object.impinging_flux[
                            0
                        ].time = epiclog_time  # TODO insert hdf5 link
                elif fitting is None:
                    logger.warning(
                        'No fitting parameters found. Please provide a Fitting.txt file.'
                    )

            if sources_row['source_type'] == 'DFC':
                # read raw files
                epiclog_value, epiclog_time = epiclog_parse_timeseries(
                    timezone,
                    growth_starttime,
                    folder_path,
                    sources_row,
                    'hl_temp_mv',
                    'hl_temp_mv_unit',
                )
                epiclog_value_p, epiclog_time_p = epiclog_parse_timeseries(
                    timezone,
                    growth_starttime,
                    folder_path,
                    sources_row,
                    'hl_temp_wop',
                )

                # instantiate objects
                source_object.vapor_source_hot_lip = EffusionCellHeater()
                source_object.vapor_source_hot_lip.temperature = (
                    EffusionCellHeaterTemperature()
                )

                # fill in quantities
                source_object.vapor_source_hot_lip.power = EffusionCellHeaterPower()
                source_object.vapor_source_hot_lip.temperature.value = epiclog_value
                source_object.vapor_source_hot_lip.temperature.time = epiclog_time
                source_object.vapor_source_hot_lip.power.value = epiclog_value_p
                source_object.vapor_source_hot_lip.power.time = epiclog_time_p

            # fill in quantities common to all sources
            # and create Source objects and Port objects lists
            if source_object:
                source_name = (
                    str(fill_quantity(sources_row, 'source_type'))
                    + '_'
                    + str(fill_quantity(sources_row, 'source_material'))
                )
                source_object.name = source_name
                # Define a list of tuples containing
                # the columnd header of the xlsx sheet
                # and the corresponding attribute name
                keys_and_attributes = [
                    ('primary_flux_species', 'primary_flux_species'),
                    ('secondary_flux_species', 'secondary_flux_species'),
                    ('source_material', 'material'),
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
                    source_object.datetime = fill_datetime(
                        sources_row['date'], sources_row['time']
                    )
                port_object = Port()
                port_object.name = source_name
                port_object.port_number = fill_quantity(sources_row, 'port_number')
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
            if sources_row['source_type'] == 'SUB':
                # read raw files
                epiclog_value, epiclog_time = epiclog_parse_timeseries(
                    timezone,
                    growth_starttime,
                    folder_path,
                    sources_row,
                    'temp_mv',
                    'temp_mv_unit',
                )
                epiclog_value_p, epiclog_time_p = epiclog_parse_timeseries(
                    timezone,
                    growth_starttime,
                    folder_path,
                    sources_row,
                    'temp_wop',
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
                child_archives['process'].data.steps[0].sample_parameters[
                    0
                ].substrate_temperature.value = epiclog_value
                child_archives['process'].data.steps[0].sample_parameters[
                    0
                ].substrate_temperature.time = epiclog_time
                child_archives['process'].data.steps[0].sample_parameters[
                    0
                ].substrate_power.value = epiclog_value_p
                child_archives['process'].data.steps[0].sample_parameters[
                    0
                ].substrate_power.time = epiclog_time_p

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
            name=f'{exp_string} experiment',
            growth_run=GrowthMbePDIReference(
                reference=child_archives['process'].data,
                # f'/uploads/{archive.m_context.upload_id}/archive/{child_archives["process"].metadata.entry_id}#data',
            ),
            # f'/entries/{child_archives["process"].metadata.entry_id}/archive#data'
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
