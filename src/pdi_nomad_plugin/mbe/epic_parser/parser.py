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
from collections.abc import Iterable
from datetime import datetime
from typing import Union
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from epic_scraper.epicfileimport.epic_module import (
    epiclog_read,
    growth_time,
)
from nomad.datamodel.data import EntryData
from nomad.datamodel.datamodel import EntryArchive, EntryMetadata
from nomad.datamodel.metainfo.annotations import ELNAnnotation
from nomad.datamodel.metainfo.basesections import (
    PureSubstanceSection,
)
from nomad.metainfo import Quantity, Section
from nomad.parsing import MatchingParser
from nomad.units import ureg
from nomad.utils import hash

from pdi_nomad_plugin.mbe.instrument import (
    DoubleFilamentEffusionCell,
    EffusionCellHeater,
    EffusionCellHeaterPower,
    EffusionCellHeaterTemperature,
    ImpingingFluxPDI,
    InstrumentMbePDI,
    PlasmaSourcePDI,
    Port,
    RfGeneratorHeater,
    RfGeneratorHeaterPower,
    GasFlowPDI,
    VolumetricFlowRatePDI,
    SingleFilamentEffusionCell,
)
from pdi_nomad_plugin.mbe.processes import (
    ExperimentMbePDI,
    GrowthMbePDI,
    GrowthStepMbePDI,
    GrowthMbePDIReference,
    SampleParametersMbe,
    SubstrateHeaterPower,
    SubstrateHeaterTemperature,
    InSituCharacterizationMbePDI,
    PyrometryReference,
)
from pdi_nomad_plugin.characterization.schema import (
    Pyrometry,
    PyrometerTemperature,
)
from pdi_nomad_plugin.utils import (
    create_archive,
    fill_quantity,
)

timezone = "Europe/Berlin"


def fill_datetime(date: pd.Series, time: pd.Series) -> datetime.date:
    return datetime.combine(
        datetime.strptime(
            date,
            "%d/%m/%Y",
        ),
        datetime.strptime(time, "%H:%M:%S").time(),
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
                mainfile_keys = ["process", "pyrometry"]
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
        filetype = "yaml"
        data_file = mainfile.split("/")[-1]
        upload_path = f"{mainfile.split('raw/')[0]}raw/"
        folder_name = mainfile.split("/")[-2]
        folder_path = f"{upload_path}{folder_name}/"
        xlsx = pd.ExcelFile(mainfile)

        # "MBE config files" sheet
        config_sheet = pd.read_excel(
            xlsx,
            "MBE config files",
            comment="#",
        )
        config_sheet.columns = config_sheet.columns.str.strip()

        # "MBE sources" sheet
        sources_sheet = pd.read_excel(
            xlsx,
            "MBE sources",
            comment="#",
        )
        sources_sheet.columns = sources_sheet.columns.str.strip()

        # "MBE gas mixing" sheet
        gasmixing_sheet = pd.read_excel(
            xlsx,
            "MBE gas mixing",
            comment="#",
        )
        gasmixing_sheet.columns = gasmixing_sheet.columns.str.strip()

        # "pyrometry config" sheet
        pyrometry_sheet = pd.read_excel(
            xlsx,
            "pyrometry config",
            comment="#",
        )
        pyrometry_sheet.columns = pyrometry_sheet.columns.str.strip()

        # reading Messages.txt
        # TODO so far, nothing is done with this metadata
        if config_sheet["messages"][0]:
            messages_df = epiclog_read(f"{folder_path}{config_sheet['messages'][0]}")
            growth_events = growth_time(messages_df)
            found_start = False
            for line in growth_events.iterrows():
                if line[1]["to"] == "GC":
                    growth_id = line[1]["object"]
                    growth_starttime = line[0].tz_localize(timezone)
                if line[1]["from"] == "GC":
                    growth_endtime = line[0].tz_localize(timezone)
                    growth_duration = growth_endtime - growth_starttime
                    logger.info(
                        f"Detected growth of {growth_id} started at {growth_starttime} and ended at {growth_endtime} with a duration of {growth_duration}"
                    )

        # reading Fitting.txt
        if config_sheet["flux_calibration"][0]:
            with open(
                f"{folder_path}{config_sheet['flux_calibration'][0]}",
                encoding="utf-8",
            ) as file:
                fitting = {}
                for line in file:
                    if "#" in line:
                        epic_loop = line.split("#")[1].strip()
                        fitting[epic_loop] = {}
                        for _ in range(4):
                            key, value = file.readline().split("=")
                            fitting[epic_loop][key] = value

        # reading Shutters.txt
        shutters = None
        if config_sheet["shutters"][0]:
            with open(
                f"{folder_path}{config_sheet['shutters'][0]}",
                encoding="utf-8",
            ) as file:
                shutters = pd.read_csv(file, skiprows=2)

        # filenames
        instrument_filename = f"{data_file}.InstrumentMbePDI.archive.{filetype}"

        # filling in the pyrometry archive
        # read raw files
        pyrometer_temp = epiclog_read(
            f"{folder_path}{pyrometry_sheet['temperature'][0]}.txt"
        )
        pyrometer_temp_unit = (
            "°C"
            if pyrometry_sheet["temperature_unit"][0] == "C"
            else pyrometry_sheet["temperature_unit"][0]
        )

        # instantiate objects
        child_archives["process"].data = GrowthMbePDI()
        child_archives["process"].data.steps = [GrowthStepMbePDI()]
        child_archives["process"].data.steps[0].sources = []
        child_archives["process"].data.steps[
            0
        ].in_situ_characterization = InSituCharacterizationMbePDI()
        child_archives["process"].data.steps[
            0
        ].in_situ_characterization.pyrometry = PyrometryReference()
        child_archives["pyrometry"].data = Pyrometry()
        child_archives["pyrometry"].data.pyrometer_temperature = PyrometerTemperature()

        # fill in quantities
        child_archives["pyrometry"].data.pyrometer_temperature.value = ureg.Quantity(
            pyrometer_temp.values.ravel(), ureg(pyrometer_temp_unit)
        )
        child_archives["pyrometry"].data.pyrometer_temperature.time = np.array(
            (
                pyrometer_temp.index.tz_localize(timezone) - growth_starttime
            ).total_seconds()
        )
        child_archives["process"].data.steps[
            0
        ].in_situ_characterization.pyrometry.reference = child_archives[
            "pyrometry"
        ].data

        # filling in the sources objects list
        port_list = []
        for sources_index, sources_row in sources_sheet.iterrows():
            if sources_row["source_type"] == "PLASMA":
                # TODO check if file exists, everywhere
                # read raw files
                forward_power = epiclog_read(
                    f"{folder_path}{sources_row['f_power']}.txt"
                )
                reflected_power = epiclog_read(
                    f"{folder_path}{sources_row['r_power']}.txt"
                )
                f_power_unit = sources_row["f_power_unit"]
                r_power_unit = sources_row["r_power_unit"]

                # instantiate objects
                child_archives["process"].data.steps[0].sources.append(
                    PlasmaSourcePDI()
                )
                source_object = (
                    child_archives["process"].data.steps[0].sources[sources_index]
                )
                source_object.vapor_source = RfGeneratorHeater()
                source_object.vapor_source.forward_power = RfGeneratorHeaterPower()
                source_object.vapor_source.reflected_power = RfGeneratorHeaterPower()
                source_object.gas_flow = []

                # fill in quantities
                source_object.type = "RF plasma source (PLASMA)"
                source_object.vapor_source.forward_power.value = ureg.Quantity(
                    forward_power.values.ravel(), ureg(f_power_unit)
                )
                source_object.vapor_source.forward_power.time = np.array(
                    (
                        forward_power.index.tz_localize(timezone) - growth_starttime
                    ).total_seconds()
                )
                source_object.vapor_source.reflected_power.value = ureg.Quantity(
                    reflected_power.values.ravel(), ureg(r_power_unit)
                )
                source_object.vapor_source.reflected_power.time = np.array(
                    (
                        reflected_power.index.tz_localize(timezone) - growth_starttime
                    ).total_seconds()
                )

                # TODO fill in dissipated power as the difference between forward and reflected power

                # fill the gas mixing in the plasma source:
                i = 0
                for gas_index in reversed(gasmixing_sheet.index):
                    gas_row = gasmixing_sheet.loc[
                        gas_index
                    ]  # this allows to loop in reverse order. Use .iterrows() instead
                    mfc_mv = epiclog_read(f"{folder_path}{gas_row['mfc_flow']}.txt")
                    if gas_row["date"] and gas_row["time"]:
                        gasmixing_datetime = fill_datetime(
                            gas_row["date"], gas_row["time"]
                        )
                        if gasmixing_datetime > growth_starttime:
                            continue
                        else:
                            print(f"this mixing was done at: {gasmixing_datetime}")
                            print(f"growth started at: {growth_starttime}")
                            source_object.gas_flow.append(
                                GasFlowPDI(flow_rate=VolumetricFlowRatePDI())
                            )
                            source_object.gas_flow[
                                i
                            ].flow_rate.value = mfc_mv.values.ravel()
                            source_object.gas_flow[i].flow_rate.time = np.array(
                                (
                                    mfc_mv.index.tz_localize(timezone)
                                    - growth_starttime
                                ).total_seconds()
                            )
                            i += 1

                            # measurement_type ='Mass Flow Controller',
                            # gas=

            if (
                sources_row["source_type"] == "SFC"
                or sources_row["source_type"] == "DFC"
            ):
                # read raw files
                sfc_temperature = epiclog_read(
                    f"{folder_path}{sources_row['temp_mv']}.txt"
                )
                sfc_power = epiclog_read(f"{folder_path}{sources_row['temp_wop']}.txt")

                temp_mv_unit = (
                    "°C"
                    if sources_row["temp_mv_unit"] == "C"
                    else sources_row["temp_mv_unit"]
                )

                # instantiate objects
                child_archives["process"].data.steps[0].sources.append(
                    SingleFilamentEffusionCell()
                    if sources_row["source_type"] == "SFC"
                    else DoubleFilamentEffusionCell()
                )
                source_object = (
                    child_archives["process"].data.steps[0].sources[sources_index]
                )
                source_object.impinging_flux = [ImpingingFluxPDI()]
                source_object.vapor_source = EffusionCellHeater()
                source_object.vapor_source.temperature = EffusionCellHeaterTemperature()
                source_object.vapor_source.power = EffusionCellHeaterPower()

                # fill in quantities
                source_object.type = (
                    "Single filament effusion cell (SFC)"
                    if sources_row["source_type"] == "SFC"
                    else "Double filament effusion cell (DFC)"
                )
                source_object.vapor_source.temperature.value = ureg.Quantity(
                    sfc_temperature.values.ravel(), ureg(temp_mv_unit)
                )
                mv_time = np.array(
                    (
                        sfc_temperature.index.tz_localize(timezone) - growth_starttime
                    ).total_seconds()
                )
                source_object.vapor_source.temperature.time = mv_time
                source_object.vapor_source.power.value = (
                    sfc_power.values.ravel()
                )  # dimensionless
                source_object.vapor_source.power.time = np.array(
                    (
                        sfc_power.index.tz_localize(timezone) - growth_starttime
                    ).total_seconds()
                )

                if sources_row["EPIC_loop"]:
                    source_object.epic_loop = sources_row["EPIC_loop"]
                    if sources_row["EPIC_loop"] in fitting.keys():
                        a_param, t0_param = fitting[sources_row["EPIC_loop"]][
                            "Coeff"
                        ].split(",")
                        bep_to_flux = fitting[sources_row["EPIC_loop"]]["BEPtoFlux"]
                        # TODO remove print statements after checking the impinging flux magnitude
                        print(a_param)
                        print(t0_param)
                        print(bep_to_flux)
                        with source_object.vapor_source.temperature.value as temperature:
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
                            print(f"BEP: {bep_test}")
                            #

                            # make shutter status a vector
                            shutter_vector = np.zeros(len(mv_time))
                            if shutters is not None:
                                for shutter_status in shutters.iterrows():
                                    if shutter_status[1][
                                        f"{sources_row['EPIC_loop']}_Sh"
                                    ]:
                                        for i in mv_time:
                                            if mv_time < shutter_status["'Date&Time"]:
                                                shutter_vector[i] = shutter_status[1][
                                                    f'{sources_row["EPIC_loop"]}_Sh'
                                                ]
                                            else:
                                                break
                                logger.info(
                                    f"The shutters file: {sources_row['EPIC_loop']}_Sh"
                                )
                                logger.info(
                                    f"This is the shutter vector: {shutter_vector}"
                                )

                        source_object.impinging_flux[0].bep_to_flux = ureg.Quantity(
                            float(bep_to_flux),
                            ureg("mol **-1 * meter ** -2 * second * pascal ** -1"),
                        )
                        source_object.impinging_flux[0].t_0_parameter = ureg.Quantity(
                            float(t0_param), ureg("°C")
                        )
                        source_object.impinging_flux[0].a_parameter = float(a_param)
                        source_object.impinging_flux[0].value = impinging_flux
                        source_object.impinging_flux[
                            0
                        ].time = mv_time  # TODO insert hdf5 link

            if sources_row["source_type"] == "DFC":
                # read raw files
                dfc_hl_temperature = epiclog_read(
                    f"{folder_path}{sources_row['hl_temp_mv']}.txt"
                )
                dfc_hl_power = epiclog_read(
                    f"{folder_path}{sources_row['hl_temp_wop']}.txt"
                )
                hl_temp_mv_unit = (
                    "°C"
                    if sources_row["hl_temp_mv_unit"] == "C"
                    else sources_row["hl_temp_mv_unit"]
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
                    (
                        dfc_hl_temperature.index.tz_localize(timezone)
                        - growth_starttime
                    ).total_seconds()
                )
                source_object.vapor_source_hot_lip.power.value = (
                    dfc_hl_power.values.ravel()
                )  # dimensionless
                source_object.vapor_source_hot_lip.power.time = np.array(
                    (
                        dfc_hl_power.index.tz_localize(timezone) - growth_starttime
                    ).total_seconds()
                )
            # fill in quantities common to all sources
            # and create Source objects and Port objects lists
            if source_object:
                source_name = (
                    str(fill_quantity(sources_row, "source_type"))
                    + "_"
                    + str(fill_quantity(sources_row, "source_material"))
                )
                source_object.name = source_name
                # Define a list of tuples containing
                # the columnd header of the xlsx sheet
                # and the corresponding attribute name
                keys_and_attributes = [
                    ("primary_flux_species", "primary_flux_species"),
                    ("secondary_flux_species", "secondary_flux_species"),
                    ("source_material", "material"),
                ]
                for key, attribute in keys_and_attributes:
                    if sources_row[key]:
                        substances = str(sources_row[key]).split("+")
                        substance_objs = []
                        for substance in substances:
                            substance_objs = [
                                PureSubstanceSection(
                                    name=substance
                                )  # TODO insert here again PUBCHEM PubChemPureSubstanceSection(name=substance)
                            ]
                        setattr(source_object, attribute, substance_objs)
                if sources_row["date"] and sources_row["time"]:
                    source_object.datetime = fill_datetime(
                        sources_row["date"], sources_row["time"]
                    )
                port_object = Port()
                port_object.name = source_name
                port_object.port_number = fill_quantity(sources_row, "port_number")
                port_object.flange_diameter = fill_quantity(sources_row, "diameter")
                port_object.flange_to_substrate_distance = fill_quantity(
                    sources_row, "distance"
                )
                port_object.theta = fill_quantity(sources_row, "theta")
                port_object.phi = fill_quantity(sources_row, "phi")
                port_list.append(port_object)

                # reference the instrument.port_list into the process.sources
                source_object.port = f"../uploads/{archive.m_context.upload_id}/archive/{hash(archive.m_context.upload_id, instrument_filename)}#data/port_list/{sources_index}"

            # filling in growth process archive
            if sources_row["source_type"] == "SUB":
                # read raw files
                substrate_temperature = epiclog_read(
                    f"{folder_path}{sources_row['temp_mv']}.txt"
                )
                substrate_power = epiclog_read(
                    f"{folder_path}{sources_row['temp_wop']}.txt"
                )

                # instantiate objects
                child_archives["process"].data.steps[0].sample_parameters = [
                    SampleParametersMbe()
                ]
                child_archives["process"].data.steps[0].sample_parameters[
                    0
                ].substrate_temperature = SubstrateHeaterTemperature()
                child_archives["process"].data.steps[0].sample_parameters[
                    0
                ].substrate_power = SubstrateHeaterPower()

                # fill in quantities
                child_archives[
                    "process"
                ].data.name = f'growth_{growth_id.replace("@", "_")}'
                child_archives["process"].data.steps[0].sample_parameters[
                    0
                ].substrate_temperature.value = ureg.Quantity(
                    substrate_temperature.values.ravel(), ureg(temp_mv_unit)
                )
                child_archives["process"].data.steps[0].sample_parameters[
                    0
                ].substrate_temperature.time = np.array(
                    (
                        substrate_temperature.index.tz_localize(timezone)
                        - growth_starttime
                    ).total_seconds()
                )
                child_archives["process"].data.steps[0].sample_parameters[
                    0
                ].substrate_power.value = (
                    substrate_power.values.ravel()
                )  # dimensionless
                child_archives["process"].data.steps[0].sample_parameters[
                    0
                ].substrate_power.time = np.array(
                    (
                        substrate_power.index.tz_localize(timezone) - growth_starttime
                    ).total_seconds()
                )

        # creating instrument archive
        if archive.m_context.raw_path_exists(instrument_filename):
            print(f"Instrument archive already exists: {instrument_filename}")
        else:
            instrument_data = InstrumentMbePDI()
            instrument_data.name = f"{data_file} instrument"
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
            name=f"{data_file} experiment",
            growth_run=GrowthMbePDIReference(
                reference=child_archives["process"].data,
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
