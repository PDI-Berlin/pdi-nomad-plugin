# PDI NOMAD Plugin

[Full documentation of the plugin]( https://pdi-berlin.github.io/pdi-nomad-plugin/)

Many classes are inherited from the NOMAD community plugins:

[NOMAD Materials Processing plugin](https://github.com/FAIRmat-NFDI/nomad-material-processing)

[NOMAD Measurement plugin](https://github.com/FAIRmat-NFDI/nomad-measurements)

[NOMAD Analysis plugin](https://github.com/FAIRmat-NFDI/nomad-analysis)

## Structure

The directory tree:

```bash
PDI-NOMAD-plugins/
├── nomad.yaml
├── src
│   └── mbe
└── tests
    └── data
        └── mbe
```

- `src/`: contains the source code of the plugin.
- `tests/`: contains the tests and template file to use with the plugin.

**Please refer to the README.md file in each subdirectory for more information about each plugin.**

## Installation

This and other plugins are already loaded in the [Docker image](hhttps://github.com/PDI-Berlin/PDI-NOMAD-Oasis-image/pkgs/container/pdi-nomad-oasis-image) built for the PDI.

### Setting up your OASIS

Read the [NOMAD plugin documentation](https://nomad-lab.eu/prod/v1/staging/docs/plugins/plugins.html#add-a-plugin-to-your-nomad) for all details on how to deploy the plugin on your NOMAD instance.

You don't need to modify the ```nomad.yaml``` configuration file of your NOMAD instance, beacuse the package is pip installed and all the available modules (entry points) are loaded.
To include, instead, only some of the entry points, you need to specify them in the ```include``` section of the ```nomad.yaml```. In the following lines, a list of all the available entry points:

```yaml
plugins:
  include:
    - "nomad_material_processing:schema"
    - "nomad_material_processing.solution:schema"
    - "nomad_material_processing.vapor_deposition.cvd:schema"
    - "nomad_material_processing.vapor_deposition.pvd:schema"
    - "nomad_material_processing.vapor_deposition.pvd:mbe_schema"
    - "nomad_material_processing.vapor_deposition.pvd:pld_schema"
    - "nomad_material_processing.vapor_deposition.pvd:sputtering_schema"
    - "nomad_material_processing.vapor_deposition.pvd:thermal_schema"
    - "nomad_measurements:schema"
    - "nomad_measurements.xrd:schema"
    - "nomad_measurements.xrd:parser"
    - "nomad_measurements.transmission:schema"
    - "nomad_measurements.transmission:parser"
    - 'pdi_nomad_plugin.general:general_schema'
    - 'pdi_nomad_plugin.characterization:characterization_schema'
    - "pdi_nomad_plugin.mbe:materials_schema"
    - "pdi_nomad_plugin.mbe:instrument_schema"
    - "pdi_nomad_plugin.mbe:processes_schema"
    - "pdi_nomad_plugin.mbe.epic_parser:parser"
```

## Usage

You need to copy and fill the tabular files in `tests/data` folder, then drag and drop them into a new NOMAD upload.

Please refer to the README.md file in each subdirectory for more information about each plugin.
