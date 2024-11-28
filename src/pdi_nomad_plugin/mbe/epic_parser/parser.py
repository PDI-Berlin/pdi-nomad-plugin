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
from datetime import datetime
from zoneinfo import ZoneInfo

import h5py
import numpy as np
import pandas as pd
from epic_scraper.epicfileimport.epic_module import (
    epic_hdf5_exporter,
    epiclog_read_batch,
    extract_growth_messages,
)
from epic_scraper.epicfileimport.epic_module import (
    filename_2_dataframename as fn2dfn,
)
from nomad.datamodel.data import EntryData
from nomad.datamodel.datamodel import EntryArchive
from nomad.datamodel.hdf5 import HDF5Reference
from nomad.datamodel.metainfo.basesections import (
    PureSubstanceSection,
)
from nomad.metainfo import Quantity
from nomad.parsing import MatchingParser
from nomad.units import ureg
from nomad.utils import hash

from pdi_nomad_plugin.characterization.schema import (
    PyrometerTemperature,
    Pyrometry,
)
from pdi_nomad_plugin.mbe.instrument import (
    ColdLipEffusionCell,
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
    SourceGeometry,
    VolumetricFlowRatePDI,
)
from pdi_nomad_plugin.mbe.processes import (
    ChamberEnvironmentMbe,
    GrowthMbePDI,
    GrowthStepMbePDI,
    GrowthMbePDIReference,
    InSituCharacterizationMbePDI,
    PressurePDI,
    SampleParametersMbe,
    SubstrateHeaterPower,
    SubstrateHeaterTemperature,
)
from pdi_nomad_plugin.utils import (
    create_archive,
    fill_quantity,
    handle_unit,
    link_experiment,
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


class ConfigFileMBE(EntryData):
    file = Quantity(
        type=str,
        description="Name of the configuration file",
        a_browser={"adaptor": "RawFileAdaptor"},
        a_eln={"component": "FileEditQuantity"},
    )


class ParserEpicPDI(MatchingParser):
    def parse(
        self,
        mainfile: str,
        archive: EntryArchive,
        logger,
    ) -> None:
        data_file = mainfile.split("/")[-1]
        upload_path = f"{mainfile.split('raw/')[0]}raw/"
        folder_name = mainfile.split("/")[-2]
        folder_path = f"{upload_path}{folder_name}/"
        xlsx = pd.ExcelFile(mainfile)

        child_archives = {
            "experiment": EntryArchive(),
            "instrument": EntryArchive(),
            "process": EntryArchive(),
        }

        filetype = "yaml"
        process_filename = f"{data_file[:-5]}.GrowthMbePDI.archive.{filetype}"
        instrument_filename = f"{data_file[:-5]}.InstrumentMbePDI.archive.{filetype}"

        # Define the sheets to read and process
        sheets = [
            "MBE config files",
            "MBE sources",
            "MBE gas mixing",
            "MBE chamber env",
            "pyrometry config",
            "LR settings",
        ]
        # Read the sheets into a dictionary of DataFrames
        sheets_dict = {
            sheet: pd.read_excel(xlsx, sheet, comment="#").rename(
                columns=lambda x: x.strip()
            )
            for sheet in sheets
        }
        # Access the individual DataFrames
        config_sheet = sheets_dict["MBE config files"]
        sources_sheet = sheets_dict["MBE sources"]
        gasmixing_sheet = sheets_dict["MBE gas mixing"]
        chamber_sheet = sheets_dict["MBE chamber env"]
        pyrometry_sheet = sheets_dict["pyrometry config"]
        # lr_sheet = sheets_dict['LR settings']

        # read Messages.txt file
        assert (
            "messages" in config_sheet and not config_sheet["messages"].empty
        ), "Messages file not found. Provide a valid messages file in the configuration sheet."
        assert pd.notna(
            config_sheet["messages"].iloc[0]
        ), "Messages file not found. Provide a valid messages file in the configuration sheet."
        (
            growth_id,
            growth_starttime,
            growth_endtime,
            growth_duration,
            logger_msg,
        ) = extract_growth_messages(folder_path, config_sheet["messages"].iloc[0])
        exp_string = growth_id.replace("@", "_") if growth_id else None
        growthrun_id = growth_id.split("@")[0] if growth_id else None

        # reading Fitting.txt
        fitting = None
        if (
            "flux_calibration" in config_sheet
            and not config_sheet["flux_calibration"].empty
        ):
            file_path = f"{folder_path}{config_sheet['flux_calibration'][0]}"
            if pd.notna(config_sheet["flux_calibration"].iloc[0]) and os.path.exists(
                file_path
            ):
                with open(
                    file_path,
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
        if "shutters" in config_sheet and not config_sheet["shutters"].empty:
            file_path = f"{folder_path}{config_sheet['shutters'][0]}"
            if pd.notna(config_sheet["shutters"].iloc[0]) and os.path.exists(file_path):
                with open(
                    file_path,
                    encoding="utf-8",
                ) as file:
                    shutters = pd.read_csv(file, skiprows=2)
                shutters["'Date&Time"] = pd.to_datetime(
                    shutters["'Date&Time"], format="%d/%m/%Y %H:%M:%S.%f"
                )
                shutters["TimeDifference"] = (
                    shutters["'Date&Time"].dt.tz_localize(timezone) - growth_starttime
                ).dt.total_seconds()

        # # # # # HDF5 FILE CREATION # # # # #
        dataframe_list = epiclog_read_batch(folder_name, upload_path)
        hdf_filename = f"{data_file[:-5]}.h5"
        with archive.m_context.raw_file(hdf_filename, "w") as newfile:
            epic_hdf5_exporter(newfile.name, dataframe_list, growth_starttime)
            logger.info(logger_msg)

        # instrument archive
        child_archives["instrument"].data = InstrumentMbePDI()
        child_archives["instrument"].data.name = f"{data_file} instrument"
        child_archives["instrument"].data.port_list = []

        # instantiate objects
        child_archives["process"].data = GrowthMbePDI()
        child_archives["process"].data.steps = [GrowthStepMbePDI()]
        child_archives["process"].data.steps[0].sources = []
        child_archives["process"].data.steps[0].environment = ChamberEnvironmentMbe()
        child_archives["process"].data.steps[0].environment.pressure = PressurePDI()
        child_archives["process"].data.steps[0].environment.pressure_2 = PressurePDI()
        child_archives["process"].data.steps[0].environment.bep = PressurePDI()
        child_archives["process"].data.steps[
            0
        ].in_situ_characterization = InSituCharacterizationMbePDI()
        child_archives["process"].data.steps[0].in_situ_characterization.pyrometry = [
            Pyrometry()
        ]
        child_archives["process"].data.steps[0].in_situ_characterization.pyrometry[
            0
        ].pyrometer_temperature = PyrometerTemperature()

        # fill in quantities
        child_archives["process"].data.name = f"{exp_string} process"
        pyro_archive = (
            child_archives["process"]
            .data.steps[0]
            .in_situ_characterization.pyrometry[0]
        )
        pyro_archive.name = f"{exp_string} pyrometry"
        pyrovalpath = f'/{fn2dfn(pyrometry_sheet["temperature"])}/value'
        pyro_archive.pyrometer_temperature.value = (
            f"/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#{pyrovalpath}"
        )
        pyrotimepath = f'/{fn2dfn(pyrometry_sheet["temperature"])}/time'
        pyro_archive.pyrometer_temperature.time = (
            f"/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#{pyrotimepath}"
        )
        child_archives["process"].data.steps[
            0
        ].environment.pressure.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(chamber_sheet["pressure_1"])}/value'
        child_archives["process"].data.steps[
            0
        ].environment.pressure.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(chamber_sheet["pressure_1"])}/time'
        child_archives["process"].data.steps[
            0
        ].environment.pressure_2.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(chamber_sheet["pressure_2"])}/value'
        child_archives["process"].data.steps[
            0
        ].environment.pressure_2.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(chamber_sheet["pressure_2"])}/time'
        child_archives["process"].data.steps[
            0
        ].environment.bep.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(chamber_sheet["bep"])}/value'
        child_archives["process"].data.steps[
            0
        ].environment.bep.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(chamber_sheet["bep"])}/time'

        with archive.m_context.raw_file(hdf_filename, "a") as newfile:
            with h5py.File(newfile.name, "a") as hdf:
                hdf[f'{fn2dfn(pyrometry_sheet["temperature"])}/time'].attrs["units"] = (
                    "s"
                )
                unit = handle_unit(pyrometry_sheet, "temperature_unit")
                if unit:
                    hdf[f'{fn2dfn(pyrometry_sheet["temperature"])}/value'].attrs[
                        "units"
                    ] = unit

                hdf[f'{fn2dfn(chamber_sheet["pressure_1"])}/time'].attrs["units"] = "s"
                hdf[f'{fn2dfn(chamber_sheet["pressure_2"])}/time'].attrs["units"] = "s"
                hdf[f'{fn2dfn(chamber_sheet["bep"])}/time'].attrs["units"] = "s"

                unit = handle_unit(chamber_sheet, "pressure_1_unit")
                if unit:
                    hdf[f'{fn2dfn(chamber_sheet["pressure_1"])}/value'].attrs[
                        "units"
                    ] = unit
                unit = handle_unit(chamber_sheet, "pressure_2_unit")
                if unit:
                    hdf[f'{fn2dfn(chamber_sheet["pressure_2"])}/value'].attrs[
                        "units"
                    ] = unit
                unit = handle_unit(chamber_sheet, "bep_unit")
                if unit:
                    hdf[f'{fn2dfn(chamber_sheet["bep"])}/value'].attrs["units"] = unit

        # filling in the sources objects list
        for sources_index, sources_row in sources_sheet.iterrows():
            if sources_row["source_type"] == "PLASMA":
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
                source_object.vapor_source.forward_power.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["f_power"])}/value'
                source_object.vapor_source.forward_power.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["f_power"])}/time'
                source_object.vapor_source.reflected_power.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["r_power"])}/value'
                source_object.vapor_source.reflected_power.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["r_power"])}/time'

                with archive.m_context.raw_file(hdf_filename, "a") as newfile:
                    with h5py.File(newfile.name, "a") as hdf:
                        hdf[f'{fn2dfn(sources_row["f_power"])}/time'].attrs["units"] = (
                            "s"
                        )
                        unit = handle_unit(sources_row, "f_power_unit")
                        if unit:
                            hdf[f'{fn2dfn(sources_row["f_power"])}/value'].attrs[
                                "units"
                            ] = unit
                        hdf[f'{fn2dfn(sources_row["r_power"])}/time'].attrs["units"] = (
                            "s"
                        )
                        unit = handle_unit(sources_row, "r_power_unit")
                        if unit:
                            hdf[f'{fn2dfn(sources_row["r_power"])}/value'].attrs[
                                "units"
                            ] = unit

                # TODO fill in dissipated power as the difference between forward and reflected power

                # fill the gas mixing in the plasma source:
                i = 0
                for gas_index in reversed(gasmixing_sheet.index):
                    gas_row = gasmixing_sheet.loc[
                        gas_index
                    ]  # this allows to loop in reverse order. Use .iterrows() instead

                    if gas_row["date"] and gas_row["time"]:
                        gasmixing_datetime = fill_datetime(
                            gas_row["date"], gas_row["time"]
                        )
                        if growth_starttime is None:
                            logger.warning(
                                "Growth start time not found. Possibly, Messages.txt file is missing."
                            )
                        elif gasmixing_datetime > growth_starttime:
                            continue

                        print(f"this mixing was done at: {gasmixing_datetime}")
                        print(f"growth started at: {growth_starttime}")
                        source_object.gas_flow.append(
                            GasFlowPDI(flow_rate=VolumetricFlowRatePDI())
                        )

                        source_object.gas_flow[
                            i
                        ].flow_rate.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(gas_row["mfc_flow"])}/value'
                        source_object.gas_flow[
                            i
                        ].flow_rate.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(gas_row["mfc_flow"])}/time'
                        i += 1

                        with archive.m_context.raw_file(hdf_filename, "a") as newfile:
                            with h5py.File(newfile.name, "a") as hdf:
                                hdf[f'{fn2dfn(gas_row["mfc_flow"])}/time'].attrs[
                                    "units"
                                ] = "s"
                                unit = handle_unit(gas_row, "mfc_flow_unit")
                                if unit:
                                    hdf[f'{fn2dfn(gas_row["mfc_flow"])}/value'].attrs[
                                        "units"
                                    ] = unit

                        # measurement_type ='Mass Flow Controller',
                        # gas=

            if (
                sources_row["source_type"] == "SFC"
                or sources_row["source_type"] == "DFC"
                or sources_row["source_type"] == "CLC"
            ):
                # instantiate objects
                if sources_row["source_type"] == "SFC":
                    child_archives["process"].data.steps[0].sources.append(
                        SingleFilamentEffusionCell()
                    )
                elif sources_row["source_type"] == "DFC":
                    child_archives["process"].data.steps[0].sources.append(
                        DoubleFilamentEffusionCell()
                    )
                elif sources_row["source_type"] == "CLC":
                    child_archives["process"].data.steps[0].sources.append(
                        ColdLipEffusionCell()
                    )
                source_object = (
                    child_archives["process"].data.steps[0].sources[sources_index]
                )
                source_object.impinging_flux = [ImpingingFluxPDI()]
                source_object.vapor_source = EffusionCellHeater()
                source_object.vapor_source.temperature = EffusionCellHeaterTemperature()
                source_object.vapor_source.power = EffusionCellHeaterPower()

                # fill in quantities
                if sources_row["source_type"] == "SFC":
                    source_object.type = "Single filament effusion cell (SFC)"
                if sources_row["source_type"] == "DFC":
                    source_object.type = "Double filament effusion cell (DFC)"
                if sources_row["source_type"] == "CLC":
                    source_object.type = "Cold lip cell (CLC)"
                temp_mv_time = f'{fn2dfn(sources_row["temp_mv"])}/time'  # used later for impinging flux too
                source_object.vapor_source.temperature.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["temp_mv"])}/value'
                source_object.vapor_source.temperature.time = f"/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{temp_mv_time}"
                source_object.vapor_source.power.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["temp_wop"])}/value'
                source_object.vapor_source.power.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["temp_wop"])}/time'

                with archive.m_context.raw_file(hdf_filename, "a") as newfile:
                    with h5py.File(newfile.name, "a") as hdf:
                        hdf[temp_mv_time].attrs["units"] = "s"
                        unit = handle_unit(sources_row, "temp_mv_unit")
                        if unit:
                            hdf[f'{fn2dfn(sources_row["temp_mv"])}/value'].attrs[
                                "units"
                            ] = unit

            if sources_row["source_type"] == "DFC":
                # instantiate objects
                source_object.vapor_source_hot_lip = EffusionCellHeater()
                source_object.vapor_source_hot_lip.temperature = (
                    EffusionCellHeaterTemperature()
                )

                # fill in quantities
                source_object.vapor_source_hot_lip.power = EffusionCellHeaterPower()

                source_object.vapor_source_hot_lip.temperature.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["hl_temp_mv"])}/value'
                source_object.vapor_source_hot_lip.temperature.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["hl_temp_mv"])}/time'
                source_object.vapor_source_hot_lip.power.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["hl_temp_wop"])}/value'
                source_object.vapor_source_hot_lip.power.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["hl_temp_wop"])}/time'

                with archive.m_context.raw_file(hdf_filename, "a") as newfile:
                    with h5py.File(newfile.name, "a") as hdf:
                        hdf[f'{fn2dfn(sources_row["hl_temp_mv"])}/time'].attrs[
                            "units"
                        ] = "s"
                        unit = handle_unit(sources_row, "hl_temp_mv_unit")
                        if unit:
                            hdf[f'{fn2dfn(sources_row["hl_temp_mv"])}/value'].attrs[
                                "units"
                            ] = unit

            if (
                sources_row["EPIC_loop"]
                and fitting is not None
                and sources_row["source_type"] != "SUB"
            ):
                source_object.epic_loop = sources_row["EPIC_loop"]
                if sources_row["EPIC_loop"] in fitting.keys():
                    a_param, t0_param = fitting[sources_row["EPIC_loop"]][
                        "Coeff"
                    ].split(",")
                    t0_param_pint = ureg.Quantity(float(t0_param), ureg("°C"))
                    bep_to_flux_pint = ureg.Quantity(
                        float(fitting[sources_row["EPIC_loop"]]["BEPtoFlux"]),
                        ureg("nanometer ** -2 * second ** -1 * mbar ** -1"),
                    )
                    # with source_object.vapor_source.temperature.value as temperature: # Native parsing mode
                    temperature_pint = ureg.Quantity(
                        HDF5Reference.read_dataset(
                            archive, source_object.vapor_source.temperature.value
                        )[:],
                        ureg("°C"),
                    )
                    impinging_flux = (
                        bep_to_flux_pint.magnitude
                        * np.exp(float(a_param))
                        * np.exp(
                            t0_param_pint.to("kelvin").magnitude
                            / temperature_pint.to("kelvin").magnitude
                        )
                    )

                    # make shutter status a vector
                    time_vector = HDF5Reference.read_dataset(
                        archive, source_object.vapor_source.temperature.time
                    )
                    shutter_vector = np.zeros(len(time_vector))
                    if shutters is not None:
                        # Iterate over the shutters DataFrame
                        for _, shutter_status in shutters.iterrows():
                            shutter_change_time = shutter_status["TimeDifference"]
                            shutter_value = shutter_status[
                                f'{sources_row["EPIC_loop"]}_Sh'
                            ]

                            # Find the index in time_vector where the shutter change occurs
                            for i, time_value in enumerate(time_vector):
                                if time_value >= shutter_change_time:
                                    shutter_vector[i:] = shutter_value
                                    break

                    modulated_flux = impinging_flux * shutter_vector

                    with archive.m_context.raw_file(hdf_filename, "a") as newfile:
                        with h5py.File(newfile.name, "a") as hdf:
                            group_name = f'{sources_row["EPIC_loop"]}_impinging_flux'
                            group = hdf.create_group(group_name)
                            value = group.create_dataset("value", data=modulated_flux)
                            value.attrs["units"] = "nanometer ** -2 * second ** -1"
                            hdf[f"/{group_name}/time"] = hdf[f"/{temp_mv_time}"]
                            group.attrs["axes"] = "time"
                            group.attrs["signal"] = "value"
                            group.attrs["NX_class"] = "NXdata"

                    source_object.impinging_flux[0].bep_to_flux = bep_to_flux_pint
                    source_object.impinging_flux[0].t_0_parameter = t0_param_pint
                    source_object.impinging_flux[0].a_parameter = float(a_param)
                    source_object.impinging_flux[
                        0
                    ].value = f"/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{group_name}/value"
                    source_object.impinging_flux[
                        0
                    ].time = f"/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{group_name}/time"

            elif fitting is None:
                logger.warning(
                    "No fitting parameters found. Please provide a Fitting.txt file."
                )

            # fill in quantities common to all sources
            # and create Source objects and Port objects lists
            if source_object:
                source_name = (
                    str(fill_quantity(sources_row, "source_type"))
                    + " "
                    + str(fill_quantity(sources_row, "source_material"))
                    + f" (primary species: {fill_quantity(sources_row, 'primary_flux_species')})"
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
                port_object.flange_diameter = fill_quantity(
                    sources_row, "port_diameter", read_unit="mm"
                )
                port_object.flange_to_substrate_distance = fill_quantity(
                    sources_row, "port_to_sub_distance", read_unit="mm"
                )
                port_object.theta = fill_quantity(sources_row, "theta")
                port_object.phi = fill_quantity(sources_row, "phi")
                child_archives["instrument"].data.port_list.append(port_object)

                # reference the instrument.port_list into the process.sources
                source_object.port = f"../uploads/{archive.m_context.upload_id}/archive/{hash(archive.m_context.upload_id, instrument_filename)}#data/port_list/{sources_index}"
                # child_archives["instrument"].data.port_list[sources_index] # Native parsing mode

                if sources_row["source_length"]:
                    source_object.geometry = SourceGeometry()
                    source_object.geometry.source_length = fill_quantity(
                        sources_row, "source_length", read_unit="mm"
                    )
                    source_object.geometry.source_to_substrate_distance = (
                        port_object.flange_to_substrate_distance
                        - source_object.geometry.source_length
                    )

            # filling in growth process archive
            if sources_row["source_type"] == "SUB":
                # instantiate objects
                hdf5_path = f"/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}"
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
                tempvalpath = f'/{fn2dfn(sources_row["temp_mv"])}/value'
                child_archives["process"].data.steps[0].sample_parameters[
                    0
                ].substrate_temperature.value = f"{hdf5_path}#{tempvalpath}"
                temptimepath = f'/{fn2dfn(sources_row["temp_mv"])}/time'
                child_archives["process"].data.steps[0].sample_parameters[
                    0
                ].substrate_temperature.time = f"{hdf5_path}#{temptimepath}"
                subpower_value = f'{fn2dfn(sources_row["temp_wop"])}/value'
                child_archives["process"].data.steps[0].sample_parameters[
                    0
                ].substrate_power.value = f"{hdf5_path}#/{subpower_value}"
                subpower_time = f'{fn2dfn(sources_row["temp_wop"])}/time'
                child_archives["process"].data.steps[0].sample_parameters[
                    0
                ].substrate_power.time = f"{hdf5_path}#/{subpower_time}"

                with archive.m_context.raw_file(hdf_filename, "a") as newfile:
                    with h5py.File(newfile.name, "a") as hdf:
                        # parsing units in hdf5 file
                        hdf[f'{fn2dfn(sources_row["temp_mv"])}/time'].attrs["units"] = (
                            "s"
                        )
                        unit = handle_unit(sources_row, "temp_mv_unit")
                        if unit:
                            hdf[f'{fn2dfn(sources_row["temp_mv"])}/value'].attrs[
                                "units"
                            ] = unit

                        # creating link for pyro vs. substrate temperature plot
                        hdf["/pyro_vs_subtemp/pyrometer_value"] = hdf[pyrovalpath]
                        hdf["/pyro_vs_subtemp/pyrometer_value"].attrs["long_name"] = (
                            "Pyrometer T vs. Substrate T (°C)"
                        )
                        hdf["/pyro_vs_subtemp/pyrometer_time"] = hdf[pyrotimepath]
                        hdf["/pyro_vs_subtemp/pyrometer_time"].attrs["long_name"] = (
                            "time (s)"
                        )
                        hdf["/pyro_vs_subtemp/substrate_temp_value"] = hdf[tempvalpath]
                        hdf["/pyro_vs_subtemp/substrate_temp_value"].attrs[
                            "long_name"
                        ] = "Substrate T (°C)"
                        hdf["/pyro_vs_subtemp/substrate_temp_time"] = hdf[temptimepath]
                        hdf["/pyro_vs_subtemp/substrate_temp_time"].attrs[
                            "long_name"
                        ] = "time (s)"
                        hdf["/pyro_vs_subtemp"].attrs["axes"] = "pyrometer_time"
                        hdf["/pyro_vs_subtemp"].attrs["signal"] = "pyrometer_value"
                        hdf["/pyro_vs_subtemp"].attrs["auxiliary_signals"] = [
                            "substrate_temp_value"
                        ]
                        hdf["/pyro_vs_subtemp"].attrs["NX_class"] = "NXdata"

                pyro_value = "pyro_vs_subtemp/pyrometer_value"
                child_archives["process"].data.steps[0].sample_parameters[
                    0
                ].substrate_temperature.pyro_value = f"{hdf5_path}#/{pyro_value}"
                pyro_time = "pyro_vs_subtemp/pyrometer_time"
                child_archives["process"].data.steps[0].sample_parameters[
                    0
                ].substrate_temperature.pyro_time = f"{hdf5_path}#/{pyro_time}"

            source_object = None  # reset source object at the end of each iteration

        create_archive(
            child_archives["process"].m_to_dict(),
            archive.m_context,
            process_filename,
            filetype,
            logger,
        )

        create_archive(
            child_archives["instrument"].m_to_dict(),
            archive.m_context,
            instrument_filename,
            filetype,
            logger,
        )

        # it is deactivated so far because it is meant to be instantiate from the ELN
        # # # #
        # # creating experiment archive
        # # archive.data = ExperimentMbePDI(  # Native parsing mode
        # experiment_filename = f'{data_file[:-5]}.ExperimentMbePDI.archive.{filetype}'
        # child_archives["experiment"].data = ExperimentMbePDI(
        #     name=f"{exp_string} experiment",
        #     growth_run=GrowthMbePDIReference(
        #         reference=f"/uploads/{archive.m_context.upload_id}/archive/{hash(archive.m_context.upload_id, process_filename)}#data",
        #         # reference=child_archives['process'].data, # Native parsing mode
        #     ),
        # )
        # create_archive(
        #     child_archives["experiment"].m_to_dict(),
        #     archive.m_context,
        #     experiment_filename,
        #     filetype,
        #     logger,
        # )

        # reference the experiment into the process

        link_experiment(
            archive,
            growthrun_id,
            process_filename,
            GrowthMbePDIReference,
            logger,
        )

        archive.data = ConfigFileMBE(file=mainfile)


# Native parsing mode

# class ParserEpicPDI(MatchingParser):
#     def is_mainfile(
#         self,
#         filename: str,
#         mime: str,
#         buffer: bytes,
#         decoded_buffer: str,
#         compression: str = None,
#     ) -> Union[bool, Iterable[str]]:
#         is_mainfile = super().is_mainfile(
#             filename=filename,
#             mime=mime,
#             buffer=buffer,
#             decoded_buffer=decoded_buffer,
#             compression=compression,
#         )
#         if is_mainfile:
#             try:
#                 # try to resolve mainfile keys from parser
#                 mainfile_keys = ['process', 'instrument']
#                 self.creates_children = True
#                 return mainfile_keys
#             except Exception:
#                 return is_mainfile
#         return is_mainfile

#     def parse(
#         self,
#         mainfile: str,
#         archive: EntryArchive,
#         child_archives: dict(process=EntryArchive, instrument=EntryArchive),
#         logger,
#     ) -> None:

#         child_archives['instrument'].data = InstrumentMbePDI()
