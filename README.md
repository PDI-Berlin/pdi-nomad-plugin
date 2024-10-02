# PDI NOMAD Plugin

[Full documentation of the plugin](https://pdi-berlin.github.io/pdi-nomad-plugin/)

Many classes are inherited from the NOMAD community plugins:

[NOMAD Materials Processing plugin](https://github.com/FAIRmat-NFDI/nomad-material-processing)

[NOMAD Measurement plugin](https://github.com/FAIRmat-NFDI/nomad-measurements)

[NOMAD Analysis plugin](https://github.com/FAIRmat-NFDI/nomad-analysis)

## Package Structure

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

## Installation

This and other plugins are already loaded in the [Docker image](https://github.com/PDI-Berlin/PDI-NOMAD-Oasis-image/pkgs/container/pdi-nomad-oasis-image) built for the PDI.
