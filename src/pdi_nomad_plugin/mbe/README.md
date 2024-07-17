# MBE PDI Plugin

[NOMAD Materials Processing plugin](https://github.com/FAIRmat-NFDI/nomad-material-processing)

[NOMAD Measurement plugin](https://github.com/FAIRmat-NFDI/nomad-measurements)

[NOMAD Analysis plugin](https://github.com/FAIRmat-NFDI/nomad-analysis)

## Overview

This directory contains the MBE PDI plugin for the NOMAD project.


## Structure

The directory tree:

```bash
PDI_plugin/
├── src
│   └── pdi_nomad_plugin
│       ├── __init__.py
│       ├── mbe
│       │   ├── growth_excel
│       │   │   ├── __init__.py
│       │   │   └── parser.py
│       │   ├── __init__.py
│       │   └── schema.py
│       ├── __init__.py
│       └── utils.py
└── tests
    └── data
        └── mbe
            └── 013_example_dataset.xlsx
```

- `src/`: contains the source code of the plugin.
- `tests/`: contains the tests and template file to use with the plugin.
- `growth_excel/`: contains the source code to parse the excel file.
- `schema.py` defines the structure of the data after it has been parsed. It specifies the fields that the structured data will contain and the types of those fields.
- `parser.py` contains the logic for parsing the raw data from the MBE growth process. This includes reading the data from its original format, extracting the relevant information, and transforming it into a structured format.
- `__init__.py` defines the raw file matching rules of the parser. Check [NOMAD plugin official docs](https://nomad-lab.eu/prod/v1/staging/docs/howto/customization/plugins_dev.html#parser-plugin-metadata) for more info.


## Installation

Check out the root folder [pdi-nomad-plugin README file](https://github.com/PDI-Berlin/pdi-nomad-plugin)