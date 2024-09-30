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


from nomad.config.models.plugins import SchemaPackageEntryPoint

# from .schema import *


class PDIMbeMaterialsEntryPoint(SchemaPackageEntryPoint):
    def load(self):
        from pdi_nomad_plugin.mbe.materials import m_package

        return m_package


materials_schema = PDIMbeMaterialsEntryPoint(
    name='MbeMaterialsSchema',
    description='Schema package defined using the new plugin mechanism.',
)


class PDIMbeInstrumentEntryPoint(SchemaPackageEntryPoint):
    def load(self):
        from pdi_nomad_plugin.mbe.instrument import m_package

        return m_package


instrument_schema = PDIMbeInstrumentEntryPoint(
    name='MbeInstrumentSchema',
    description='Schema package defined using the new plugin mechanism.',
)


class PDIMbeProcessesEntryPoint(SchemaPackageEntryPoint):
    def load(self):
        from pdi_nomad_plugin.mbe.processes import m_package

        return m_package


processes_schema = PDIMbeProcessesEntryPoint(
    name='MbeProcessesSchema',
    description='Schema package for synthesis and characterization processes.',
)
