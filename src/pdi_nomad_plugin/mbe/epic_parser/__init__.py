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

from nomad.config.models.plugins import ParserEntryPoint
from pydantic import Field


class ConfigurationParserEntryPoint(ParserEntryPoint):
    def load(self):
        from pdi_nomad_plugin.mbe.epic_parser.parser import ParserConfigurationMbePDI

        return ParserConfigurationMbePDI(**self.dict())


config_parser = ConfigurationParserEntryPoint(
    name='ConfigMbeParser',
    description='Parse excel files for configuration parameters logged manually.',
    mainfile_name_re=r'.+\.xlsx',
    mainfile_mime_re='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    mainfile_contents_dict={
        'MBE sources': {'__has_all_keys': ['source type', 'EPIC_loop']},
        '__comment_symbol': '#',
        #'MBE gas mixing': {'__has_all_keys': ['mfc1_EPIC_name']},
    },
)


class EpicParserEntryPoint(ParserEntryPoint):
    def load(self):
        from pdi_nomad_plugin.mbe.epic_parser.parser import ParserEpicPDI

        return ParserEpicPDI(**self.dict())


epic_parser = EpicParserEntryPoint(
    name='EpicMbeParser',
    description='Parser for EPIC log files.',
    mainfile_mime_re=r'text/.*|application/zip',
    mainfile_name_re=r'.+\.txt',
    mainfile_contents_re=r'EPIC',
)
