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

import json
import math

import pandas as pd
import yaml
from nomad.datamodel.context import ClientContext
from nomad.datamodel.metainfo.basesections import (
    ExperimentStep,
)
from nomad.units import ureg


def get_reference(upload_id, entry_id):
    return f'../uploads/{upload_id}/archive/{entry_id}'


def get_entry_id(upload_id, filename):
    from nomad.utils import hash

    return hash(upload_id, filename)


def get_hash_ref(upload_id, filename):
    return f'{get_reference(upload_id, get_entry_id(upload_id, filename))}#data'


def nan_equal(a, b):
    """
    Compare two values with NaN values.
    """
    if isinstance(a, float) and isinstance(b, float):
        return a == b or (math.isnan(a) and math.isnan(b))
    elif isinstance(a, dict) and isinstance(b, dict):
        return dict_nan_equal(a, b)
    elif isinstance(a, list) and isinstance(b, list):
        return list_nan_equal(a, b)
    else:
        return a == b


def list_nan_equal(list1, list2):
    """
    Compare two lists with NaN values.
    """
    if len(list1) != len(list2):
        return False
    for a, b in zip(list1, list2):
        if not nan_equal(a, b):
            return False
    return True


def dict_nan_equal(dict1, dict2):
    """
    Compare two dictionaries with NaN values.
    """
    if set(dict1.keys()) != set(dict2.keys()):
        return False
    for key in dict1:
        if not nan_equal(dict1[key], dict2[key]):
            return False
    return True


def create_archive(
    entry_dict, context, filename, file_type, logger, *, overwrite: bool = False
):
    file_exists = context.raw_path_exists(filename)
    dicts_are_equal = None
    if isinstance(context, ClientContext):
        return None
    if file_exists:
        with context.raw_file(filename, 'r') as file:
            existing_dict = yaml.safe_load(file)
            dicts_are_equal = dict_nan_equal(existing_dict, entry_dict)
    if not file_exists or overwrite or dicts_are_equal:
        with context.raw_file(filename, 'w') as newfile:
            if file_type == 'json':
                json.dump(entry_dict, newfile)
            elif file_type == 'yaml':
                yaml.dump(entry_dict, newfile)
        context.upload.process_updated_raw_file(filename, allow_modify=True)
    elif file_exists and not overwrite and not dicts_are_equal:
        logger.error(
            f'{filename} archive file already exists. '
            f'You are trying to overwrite it with a different content. '
            f'To do so, remove the existing archive and click reprocess again.'
        )
    return get_hash_ref(context.upload_id, filename)

    # !! useful to fetch the upload_id from another upload.
    # experiment_context = ServerContext(
    #         get_upload_with_read_access(
    #             matches["upload_id"][0],
    #             User(
    #                 is_admin=True,
    #                 user_id=current_parse_archive.metadata.main_author.user_id,
    #             ),
    #             include_others=True,
    #         )
    #     )  # Upload(upload_id=matches["upload_id"][0]))


def is_activity_section(section):
    return any('Activity' in i.label for i in section.m_def.all_base_sections)


def handle_section(section):
    if hasattr(section, 'reference') and is_activity_section(section.reference):
        return [ExperimentStep(activity=section.reference, name=section.reference.name)]
    if section.m_def.label == 'CharacterizationMbePDI':
        sub_sect_list = []
        for sub_section in vars(section).values():
            if isinstance(sub_section, list):
                for item in sub_section:
                    if hasattr(item, 'reference') and is_activity_section(
                        item.reference
                    ):
                        sub_sect_list.append(
                            ExperimentStep(
                                activity=item.reference, name=item.reference.name
                            )
                        )
        return sub_sect_list
    if not hasattr(section, 'reference') and is_activity_section(section):
        return [ExperimentStep(activity=section, name=section.name)]


# see imem plugin for this function
def fill_quantity(dataframe, column_header, read_unit=None, array=False):
    """
    Fetches a value from a DataFrame and optionally converts it to a specified unit.
    """
    try:
        if isinstance(dataframe[column_header], str):
            value = (
                dataframe[column_header].strip()
                if not pd.isna(dataframe[column_header])
                else None
            )
        else:
            value = (
                dataframe[column_header]
                if not pd.isna(dataframe[column_header])
                else None
            )
    except (KeyError, IndexError):
        value = None

    pint_value = None
    if read_unit is not None:
        try:
            if value != '' and value is not None:
                if not array:
                    pint_value = ureg.Quantity(
                        value,
                        ureg(read_unit),
                    )
                else:
                    pint_value = ureg.Quantity(
                        [value],
                        ureg(read_unit),
                    )

            else:
                value = None
        except ValueError:
            if hasattr(value, 'empty') and not value.empty():
                pint_value = ureg.Quantity(
                    value,
                    ureg(read_unit),
                )
            elif value == '':
                pint_value = None

    return pint_value if read_unit is not None else value


def clean_col_names(growth_run_dataframe):
    """
    Clean column names by removing spaces and splitting on '.'
    """
    growth_run_dataframe.columns = growth_run_dataframe.columns.str.strip()
    string = []
    for col_name in growth_run_dataframe.columns:
        pre, sep, post = col_name.rpartition('.')
        if sep:
            string.append(pre)
        else:
            string.append(post)
    return string


def split_list_by_element(lst, element):
    """
    Split a list by an element
    """
    indices = [i for i, x in enumerate(lst) if element in x]
    start = 0
    result = []
    for index in indices:
        result.append(lst[start:index])
        start = index
    result.append(lst[start:])
    return result


def rename_block_cols(string, block_cols, initial_col):
    """
    Rename columns by splitting on '.' and appending the index of the block column
    """

    split_list = split_list_by_element(string, initial_col)

    new_columns = []
    for index, chunk in enumerate(split_list):
        bubbler = [f'{i}.{index}' for i in chunk if i in block_cols]
        other_cols = [i for i in chunk if i not in block_cols]
        if bubbler:
            new_columns.extend(bubbler)
            bubbler = []
        if other_cols:
            new_columns.extend(other_cols)
            other_cols = []
    return new_columns


def fetch_substrate(archive, sample_id, substrate_id, logger):
    from nomad.app.v1.models.models import User
    from nomad.datamodel.context import ServerContext
    from nomad.search import search

    substrate_reference_str = None
    search_result = search(
        owner='all',
        query={
            'results.eln.sections:any': ['SubstrateMbe', 'Substrate'],
            'results.eln.lab_ids:any': [substrate_id],
        },
        user_id=archive.metadata.main_author.user_id,
    )
    if not search_result.data:
        logger.warn(
            f'Substrate entry [{substrate_id}] was not found, upload and reprocess to reference it in ThinFilmStack entry [{sample_id}]'
        )
        return None
    if len(search_result.data) > 1:
        logger.warn(
            f'Found {search_result.pagination.total} entries with lab_id: '
            f'"{substrate_id}". Will use the first one found.'
        )
        return None
    if len(search_result.data) >= 1:
        upload_id = search_result.data[0]['upload_id']
        from nomad.app.v1.routers.uploads import get_upload_with_read_access
        from nomad.files import UploadFiles

        upload_files = UploadFiles.get(upload_id)

        substrate_context = ServerContext(
            get_upload_with_read_access(
                upload_id,
                User(
                    is_admin=True,
                    user_id=archive.metadata.main_author.user_id,
                ),
                include_others=True,
            )
        )

        if upload_files.raw_path_is_file(substrate_context.raw_path()):
            substrate_reference_str = f"../uploads/{search_result.data[0]['upload_id']}/archive/{search_result.data[0]['entry_id']}#data"
            return substrate_reference_str
        else:
            logger.warn(
                f"The path '../uploads/{search_result.data[0]['upload_id']}/archive/{search_result.data[0]['entry_id']}#data' is not a file, upload and reprocess to reference it in ThinFilmStack entry [{sample_id}]"
            )
            return None


def set_sample_status(
    sample_reference,
    context,
    logger,
    *,
    as_delivered=False,
    fresh=False,
    processed=False,
    grown=False,
):
    """
    Defines the status of a sample by updating the status attribute
    in the sample reference file.
    The Sample archive file is then overwritten.
    """
    if sample_reference:
        if (
            hasattr(sample_reference, 'fresh')
            and hasattr(sample_reference, 'as_delivered')
            and hasattr(sample_reference, 'processed')
            and hasattr(sample_reference, 'grown')
        ):
            filename = sample_reference.m_parent.metadata.mainfile
            with context.raw_file(filename, 'r') as file:
                sample_dict = (
                    yaml.safe_load(file)
                    if filename.split('.')[-1] == 'yaml'
                    else json.load(file)
                )
                sample_dict['data']['fresh'] = fresh
                sample_dict['data']['as_delivered'] = as_delivered
                sample_dict['data']['processed'] = processed
                sample_dict['data']['grown'] = grown
            with context.raw_file(filename, 'w') as newfile:
                if filename.split('.')[-1] == 'json':
                    json.dump(sample_dict, newfile)
                elif filename.split('.')[-1] == 'yaml':
                    yaml.dump(sample_dict, newfile)
            context.upload.process_updated_raw_file(filename, allow_modify=True)
        else:
            logger.warn(
                f'Sample {filename} with entry_id {sample_reference.m_parent.metadata.entry_id} does not have status attribute. Please use a sample class with status.'
            )
            return
    else:
        logger.warn(
            f'Sample {sample_reference} is not a valid reference. Upload and reprocess to set the status.'
        )
