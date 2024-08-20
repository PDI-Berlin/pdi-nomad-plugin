# PDI Plugins

See also:

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

### Local installation

To install these plugins in your local installation, or in your development environemnt, you need to:

1. add the path to the `src/` directory in this repo in your `PYTHONPATH` environment variable, after activating the python virtual environment where you have [installed NOMAD](https://nomad-lab.eu/prod/v1/staging/docs/howto/develop/setup.html).

You can do this by running the following command in the terminal where you run NOMAD:

```sh
export PYTHONPATH="$PYTHONPATH:/your/path/PDI-NOMAD-plugins/src"
```

Export this system variable in the same terminal where you run NOMAD (`nomad admin run appworker`).

To make this path persistent, write into the .pyenv/bin/activate file of your virtual environment. Use the path of your local OS where you cloned this repository.

2. include it in your `nomad.yaml` configuration file and specify the Python package for the plugin in the options section.

```yaml
plugins:
  include:
    - 'parsers/mbe'
```

The name after the `/` is user defined.
Then, specify the Python package for the plugin in the options section:

```yaml
options:
  parsers/mbe:
    python_package: pdi_nomad_plugin.mbe.growth_excel
```

This plugin has some other plugins as dependencies.

It requires to clone in your local machines other plugin repositories:

```sh
git clone https://github.com/FAIRmat-NFDI/nomad-measurements
git clone https://github.com/FAIRmat-NFDI/nomad-material-processing
git clone https://github.com/FAIRmat-NFDI/AreaA-data_modeling_and_schemas
```

Consequentlty, other paths must be appended to `PYTHONPATH` system variable:

```sh
export MYPATH=/your/path
export PYTHONPATH=$PYTHONPATH:$MYPATH/PLUGINS/nomad-material-processing/src
export PYTHONPATH=$PYTHONPATH:$MYPATH/PLUGINS/nomad-measurements/src
export PYTHONPATH=$PYTHONPATH:$MYPATH/PLUGINS/nomad-measurements/src/nomad_measurements
export PYTHONPATH=$PYTHONPATH:$MYPATH/PLUGINS/nomad-analysis/src
```

To load the full functionality, use the following `plugins` section:

```yaml
plugins:
  include:
    - "nomad_measurements.general:schema"
    - "nomad_measurements.xrd:schema"
    - "nomad_measurements.xrd.parser:parser"
    - "nomad_measurements.transmission:schema"
    - "nomad_measurements.transmission:parser"
    - 'schemas/nomad_material_processing'
    - 'schemas/nomad_material_processing/vd'
    - 'schemas/nomad_material_processing/vd/cvd'
    - 'schemas/nomad_material_processing/vd/pvd'
  options:
    schemas/analysis:
      python_package: nomad_analysis
    schemas/nomad_material_processing:
      python_package: nomad_material_processing
    schemas/nomad_material_processing/vd:
      python_package: nomad_material_processing.vapor_deposition
    schemas/nomad_material_processing/vd/cvd:
      python_package: nomad_material_processing.vapor_deposition.cvd
    schemas/nomad_material_processing/vd/pvd:
      python_package: nomad_material_processing.vapor_deposition.pvd
```

## Usage

You need to copy and fill the tabular files in `tests/data` folder, then drag and drop them into a new NOMAD upload.

Please refer to the README.md file in each subdirectory for more information about each plugin.
