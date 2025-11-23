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
    LaserReflectance,
    LaserReflectanceIntensity,
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
    Shutter,
    ShutterStatus,
    SingleFilamentEffusionCell,
    SourceGeometry,
    VolumetricFlowRatePDI,
)
from pdi_nomad_plugin.mbe.processes import (
    ChamberEnvironmentMbe,
    GrowthMbePDI,
    GrowthMbePDIReference,
    GrowthStepMbePDI,
    InSituCharacterizationMbePDI,
    PressurePDI,
    SampleParametersMbe,
    SubstrateHeaterPower,
    SubstrateHeaterTemperature,
)
from pdi_nomad_plugin.utils import (
    add_impinging_flux_to_hdf5,
    add_units_to_hdf5,
    calculate_impinging_flux,
    create_archive,
    create_hdf5_file,
    fill_datetime,
    fill_quantity,
    link_experiment,
    read_fitting,
    read_shutters,
    xlsx_to_dict,
)

timezone = 'Europe/Berlin'


class ConfigFileMBE(EntryData):
    file = Quantity(
        type=str,
        description='Name of the configuration file',
        a_browser={'adaptor': 'RawFileAdaptor'},
        a_eln={'component': 'FileEditQuantity'},
    )


class ParserEpicPDI(MatchingParser):
    def parse(
        self,
        mainfile: str,
        archive: EntryArchive,
        logger,
    ) -> None:
        data_file = mainfile.rsplit('/', 1)[-1]

        folder_name = (mainfile.split('raw/', 1)[1]).rsplit('/', 1)[-2]
        upload_path = f'{mainfile.split("raw/", 1)[0]}raw/'
        folder_path = f'{upload_path}{folder_name}/'

        child_archives = {
            'experiment': EntryArchive(),
            'instrument': EntryArchive(),
            'process': EntryArchive(),
        }

        # Read excel file sheets
        (
            config_sheet,
            sources_sheet,
            gasmixing_sheet,
            chamber_sheet,
            pyrometry_sheet,
            lr_sheet,
        ) = xlsx_to_dict(pd.ExcelFile(mainfile))

        # Read Messages.txt file
        assert 'messages' in config_sheet and not config_sheet['messages'].empty, (
            'Messages file not found. Provide a valid messages file in the configuration sheet.'
        )
        assert pd.notna(config_sheet['messages'].iloc[0]), (
            'Messages file not found. Provide a valid messages file in the configuration sheet.'
        )
        (
            growth_id,
            substrate_load_time,
            substrate_unload_time,
            growth_duration,
            logger_msg,
        ) = extract_growth_messages(folder_path, config_sheet['messages'].iloc[0])
        exp_string = growth_id.replace('@', '_') if growth_id else None
        growthrun_id = growth_id.split('@')[0] if growth_id else None

        # Create entity paths based on growthrun_id
        filetype = 'yaml'
        process_filename = (
            f'{growthrun_id}/{data_file[:-5]}.GrowthMbePDI.archive.{filetype}'
        )
        instrument_filename = (
            f'{growthrun_id}/{data_file[:-5]}.InstrumentMbePDI.archive.{filetype}'
        )

        # Read Fitting.txt
        fitting = None
        if (
            'flux_calibration' in config_sheet
            and not config_sheet['flux_calibration'].empty
        ):
            file_path = f'{folder_path}{config_sheet["flux_calibration"][0]}'
            fitting = read_fitting(file_path, config_sheet)

        # Read Shutters.txt
        shutters = None
        if 'shutters' in config_sheet and not config_sheet['shutters'].empty:
            file_path = f'{folder_path}{config_sheet["shutters"][0]}'
            shutters = read_shutters(
                file_path, config_sheet, substrate_load_time, timezone
            )

        # # # # # HDF5 FILE CREATION 1/3 # # # # #
        # WARNING: the ExperimentMbePDI normalize function reuses this method to overwrite the growth start time !
        # Every change made here should be reflected there, too
        hdf_filename = f'{growthrun_id}/{data_file[:-5]}.h5'
        create_hdf5_file(
            archive, folder_name, upload_path, substrate_load_time, hdf_filename
        )

        # instrument archive
        child_archives['instrument'].data = InstrumentMbePDI()
        child_archives['instrument'].data.name = f'{data_file} instrument'
        child_archives['instrument'].data.port_list = []

        # instantiate objects
        child_archives['process'].data = GrowthMbePDI()
        child_archives['process'].data.steps = [GrowthStepMbePDI()]
        child_archives['process'].data.steps[0].sources = []
        child_archives['process'].data.steps[0].environment = ChamberEnvironmentMbe()
        child_archives['process'].data.steps[0].environment.pressure = PressurePDI()
        child_archives['process'].data.steps[0].environment.pressure_2 = PressurePDI()
        child_archives['process'].data.steps[0].environment.bep = PressurePDI()
        child_archives['process'].data.steps[
            0
        ].in_situ_characterization = InSituCharacterizationMbePDI()
        child_archives['process'].data.steps[0].in_situ_characterization.pyrometry = [
            Pyrometry()
        ]
        child_archives['process'].data.steps[0].in_situ_characterization.pyrometry[
            0
        ].pyrometer_temperature = PyrometerTemperature()
        child_archives['process'].data.steps[
            0
        ].in_situ_characterization.laser_reflectance = [LaserReflectance()]
        child_archives['process'].data.steps[
            0
        ].in_situ_characterization.laser_reflectance[
            0
        ].laser_reflectance_intensity = LaserReflectanceIntensity()

        # fill in quantities
        child_archives['process'].data.name = f'{exp_string} process'
        child_archives['process'].data.start_time = substrate_load_time
        child_archives['process'].data.end_time = substrate_unload_time
        if child_archives['process'].data.datetime is None:
            child_archives['process'].data.datetime = substrate_load_time
        child_archives['process'].data.hdf5_file = hdf_filename
        child_archives['process'].data.data_file = f'{folder_name}/{data_file}'
        child_archives['process'].data.lab_id = f'{growthrun_id}'
        child_archives['process'].data.steps[
            0
        ].environment.pressure.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(chamber_sheet["pressure_1"])}/value'
        child_archives['process'].data.steps[
            0
        ].environment.pressure.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(chamber_sheet["pressure_1"])}/time'
        child_archives['process'].data.steps[
            0
        ].environment.pressure_2.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(chamber_sheet["pressure_2"])}/value'
        child_archives['process'].data.steps[
            0
        ].environment.pressure_2.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(chamber_sheet["pressure_2"])}/time'
        child_archives['process'].data.steps[
            0
        ].environment.bep.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(chamber_sheet["bep"])}/value'
        child_archives['process'].data.steps[
            0
        ].environment.bep.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(chamber_sheet["bep"])}/time'
        # shutters status
        if shutters is not None:
            for shutter_key, shutter_value in shutters.items():
                if isinstance(shutter_value, pd.Series) and (shutter_value == 0).all():
                    continue
                if shutter_key in ['TimeDifference', "'Date&Time"]:
                    continue

                shutter = Shutter(
                    name=shutter_key,
                    shutter_status=ShutterStatus(
                        time=shutters['TimeDifference'],
                        timestamp=pd.to_datetime(
                            shutters["'Date&Time"].values, format='%Y-%m-%d %H:%M:%S.%f'
                        ).tolist(),
                        value=shutter_value,
                    ),
                )
                child_archives['process'].data.m_add_sub_section(
                    GrowthMbePDI.shutters, shutter
                )
        # pyrometry
        pyro_archive = (
            child_archives['process']
            .data.steps[0]
            .in_situ_characterization.pyrometry[0]
        )
        pyro_archive.name = f'{exp_string} pyrometry'
        pyrovalpath = f'/{fn2dfn(pyrometry_sheet["temperature"])}/value'
        pyro_archive.pyrometer_temperature.value = (
            f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#{pyrovalpath}'
        )
        pyrotimepath = f'/{fn2dfn(pyrometry_sheet["temperature"])}/time'
        pyro_archive.pyrometer_temperature.time = (
            f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#{pyrotimepath}'
        )
        # laser reflectance
        lr_archive = (
            child_archives['process']
            .data.steps[0]
            .in_situ_characterization.laser_reflectance[0]
        )
        lr_archive.name = f'{exp_string} laser reflectance'
        lrvalpath = f'/{fn2dfn(lr_sheet["intensity_mv"])}/value'
        lr_archive.laser_reflectance_intensity.value = (
            f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#{lrvalpath}'
        )
        lrtimepath = f'/{fn2dfn(lr_sheet["intensity_mv"])}/time'
        lr_archive.laser_reflectance_intensity.time = (
            f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#{lrtimepath}'
        )
        lr_archive.wavelength = fill_quantity(
            lr_sheet.iloc[0], 'wavelength', read_unit='nm'
        )  # only the first row is currenly read iloc[0]
        lr_archive.incidence_angle = fill_quantity(
            lr_sheet.iloc[0], 'angle', read_unit='degree'
        )  # only the first row is currenly read iloc[0]

        # filling in the sources objects list
        sources_index = -1
        for _, sources_row in sources_sheet.iterrows():
            source_object = None  # set source object at the start of each iteration
            if sources_row['source_type'] != 'SUB':
                sources_index += 1
            if sources_row['source_type'] == 'PLASMA':
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
                source_object.vapor_source.forward_power.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["f_power"])}/value'
                source_object.vapor_source.forward_power.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["f_power"])}/time'
                source_object.vapor_source.reflected_power.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["r_power"])}/value'
                source_object.vapor_source.reflected_power.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["r_power"])}/time'

                # TODO fill in dissipated power as the difference between forward and reflected power

                # fill the gas mixing in the plasma source:
                i = 0
                for gas_index in reversed(gasmixing_sheet.index):
                    gas_row = gasmixing_sheet.loc[
                        gas_index
                    ]  # this allows to loop in reverse order. Use .iterrows() instead

                    if gas_row['date'] and gas_row['time']:
                        gasmixing_datetime = fill_datetime(
                            gas_row['date'], gas_row['time']
                        )
                        if substrate_load_time is None:
                            logger.warning(
                                'Growth start time not found. Possibly, Messages.txt file is missing.'
                            )
                        elif gasmixing_datetime > substrate_load_time:
                            continue

                        logger.info(f'This mixing was done at: {gasmixing_datetime}')
                        logger.info(f'Growth Cell was loaded at: {substrate_load_time}')
                        logger.info(f'Growth run start time: {substrate_load_time}')
                        source_object.gas_flow.append(
                            GasFlowPDI(
                                name=gas_row['mfc_gas'],
                                gas=PureSubstanceSection(
                                    name=gas_row['mfc_gas']
                                ),  # TODO use PubChemPureSubstanceSection
                                flow_rate=VolumetricFlowRatePDI(),
                            )
                        )

                        source_object.gas_flow[
                            i
                        ].flow_rate.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(gas_row["mfc_flow"])}/value'
                        source_object.gas_flow[
                            i
                        ].flow_rate.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(gas_row["mfc_flow"])}/time'
                        i += 1

                        # measurement_type ='Mass Flow Controller',
                        # gas=

            if (
                sources_row['source_type'] == 'SFC'
                or sources_row['source_type'] == 'DFC'
                or sources_row['source_type'] == 'CLC'
            ):
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
                temp_mv_time = f'{fn2dfn(sources_row["temp_mv"])}/time'  # used later for impinging flux too
                source_object.vapor_source.temperature.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["temp_mv"])}/value'
                source_object.vapor_source.temperature.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{temp_mv_time}'
                source_object.vapor_source.power.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["temp_wop"])}/value'
                source_object.vapor_source.power.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["temp_wop"])}/time'

            if sources_row['source_type'] == 'DFC':
                # instantiate objects
                source_object.vapor_source_hot_lip = EffusionCellHeater()
                source_object.vapor_source_hot_lip.temperature = (
                    EffusionCellHeaterTemperature()
                )
                source_object.vapor_source_hot_lip.power = EffusionCellHeaterPower()
                # fill in quantities
                source_object.vapor_source_hot_lip.temperature.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["hl_temp_mv"])}/value'
                source_object.vapor_source_hot_lip.temperature.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["hl_temp_mv"])}/time'
                source_object.vapor_source_hot_lip.power.value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["hl_temp_wop"])}/value'
                source_object.vapor_source_hot_lip.power.time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{fn2dfn(sources_row["hl_temp_wop"])}/time'

            # Impinging flux
            if (
                sources_row['EPIC_loop']
                and fitting is not None
                and sources_row['source_type'] != 'SUB'
                and hasattr(source_object.vapor_source, 'temperature')
            ):
                # fill in quantities
                source_object.epic_loop = sources_row['EPIC_loop']
                # prepare variables for impinging flux calculation
                temperature_pint = ureg.Quantity(
                    HDF5Reference.read_dataset(
                        archive, source_object.vapor_source.temperature.value
                    )[:],
                    ureg('°C'),
                )
                time_vector = HDF5Reference.read_dataset(
                    archive, source_object.vapor_source.temperature.time
                )
                # # # # # HDF5 FILE CREATION 2/3 # # # # #
                # WARNING: the ExperimentMbePDI normalize function reuses this method to overwrite the growth start time !
                # Every change made here should be reflected there, too
                # The impinging flux modulated by shutters opening is being added to the HDF5 file
                modulated_flux, a_param, t0_param_pint, bep_to_flux_pint = (
                    calculate_impinging_flux(
                        logger,
                        sources_row,
                        fitting,
                        temperature_pint,
                        time_vector,
                        shutters,
                    )
                )
                if modulated_flux is not None:
                    group_name = add_impinging_flux_to_hdf5(
                        archive, sources_row, modulated_flux, hdf_filename, temp_mv_time
                    )
                    # fill in quantities
                    source_object.impinging_flux[0].bep_to_flux = bep_to_flux_pint
                    source_object.impinging_flux[0].t_0_parameter = t0_param_pint
                    source_object.impinging_flux[0].a_parameter = float(a_param)
                    source_object.impinging_flux[
                        0
                    ].value = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{group_name}/value'
                    source_object.impinging_flux[
                        0
                    ].time = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}#/{group_name}/time'

            elif fitting is None:
                logger.warning(
                    'No fitting parameters found. Please provide a Fitting.txt file.'
                )

            # fill in quantities common to all sources
            # and create Source objects and Port objects lists
            if source_object:
                source_name = (
                    str(fill_quantity(sources_row, 'source_type'))
                    + ' '
                    + str(fill_quantity(sources_row, 'source_material'))
                    + f' (primary species: {fill_quantity(sources_row, "primary_flux_species")})'
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
                port_object.flange_diameter = fill_quantity(
                    sources_row, 'port_diameter', read_unit='mm'
                )
                port_object.flange_to_substrate_distance = fill_quantity(
                    sources_row, 'port_to_sub_distance', read_unit='mm'
                )
                port_object.theta = fill_quantity(sources_row, 'theta')
                port_object.phi = fill_quantity(sources_row, 'phi')
                child_archives['instrument'].data.port_list.append(port_object)

                # reference the instrument.port_list into the process.sources
                source_object.port = f'../uploads/{archive.m_context.upload_id}/archive/{hash(archive.m_context.upload_id, instrument_filename)}#data/port_list/{sources_index}'
                # child_archives["instrument"].data.port_list[sources_index] # Native parsing mode

                if sources_row['source_length']:
                    source_object.geometry = SourceGeometry()
                    source_object.geometry.source_length = fill_quantity(
                        sources_row, 'source_length', read_unit='mm'
                    )
                    source_object.geometry.source_to_substrate_distance = (
                        port_object.flange_to_substrate_distance
                        - source_object.geometry.source_length
                    )

            # filling in growth process archive
            if sources_row['source_type'] == 'SUB':
                # instantiate objects
                hdf5_path = f'/uploads/{archive.m_context.upload_id}/raw/{hdf_filename}'
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
                tempvalpath = f'/{fn2dfn(sources_row["temp_mv"])}/value'
                child_archives['process'].data.steps[0].sample_parameters[
                    0
                ].substrate_temperature.value = f'{hdf5_path}#{tempvalpath}'
                temptimepath = f'/{fn2dfn(sources_row["temp_mv"])}/time'
                child_archives['process'].data.steps[0].sample_parameters[
                    0
                ].substrate_temperature.time = f'{hdf5_path}#{temptimepath}'
                subpower_value = f'{fn2dfn(sources_row["temp_wop"])}/value'
                child_archives['process'].data.steps[0].sample_parameters[
                    0
                ].substrate_power.value = f'{hdf5_path}#/{subpower_value}'
                subpower_time = f'{fn2dfn(sources_row["temp_wop"])}/time'
                child_archives['process'].data.steps[0].sample_parameters[
                    0
                ].substrate_power.time = f'{hdf5_path}#/{subpower_time}'
            source_object = None  # reset source object at the end of each iteration

        # # # # # HDF5 FILE CREATION 3/3 # # # # #
        # WARNING: the ExperimentMbePDI normalize function reuses this method to overwrite the growth start time !
        # Every change made here should be reflected there, too
        # Complete the HDF5 file with the units and other derived datasets
        add_units_to_hdf5(
            archive,
            logger,
            hdf_filename,
            sources_sheet,
            gasmixing_sheet,
            chamber_sheet,
            pyrometry_sheet,
            temp_mv_time,
        )

        # create archives
        create_archive(
            child_archives['process'].m_to_dict(),
            archive.m_context,
            process_filename,
            filetype,
            logger,
        )
        create_archive(
            child_archives['instrument'].m_to_dict(),
            archive.m_context,
            instrument_filename,
            filetype,
            logger,
        )

        # reference the experiment into the process
        link_experiment(
            archive,
            growthrun_id,
            process_filename,
            GrowthMbePDIReference,
            logger,
        )

        archive.data = ConfigFileMBE(file=f'{folder_name}/{data_file}')


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
