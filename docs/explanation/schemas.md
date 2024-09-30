## PDI NOMAD Plugin

The PDI NOMAD Plugin contains schemas for different synthesis methods.
An overview of the package structure is shown below.

### Technical description

There are some technical aspects to understand the Python package built for this plugin, they are not crucial for the data model understanding itself:

- It is structured according to the [src layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/).
- It is a [regular Python package](https://docs.python.org/3/reference/import.html#regular-packages), i. e., the structure is defined by the presence of `__init__.py` files. Each of these files contains one or multiple [entry points](https://nomad-lab.eu/prod/v1/staging/docs/howto/plugins/plugins.html#plugin-entry-points). These are used to load a portion of the code within your NOMAD through a specific section in the `nomad.yaml` file.
- It is pip installable. The `project.toml` file defines what will be installed, the dependencies, further details. The **entry points** included are listed in this file.

```text
nomad-material-processing/
├── docs
├── pyproject.toml
├── README.md
├── src
│   └── pdi_nomad_plugin
│       ├── __init__.py
│       ├── utils.py
│       ├── general
│       │   └── schema.py
│       ├── mbe
│       │   ├── __init__.py
│       │   ├── instrument.py
│       │   ├── materials.py
│       │   ├── processes.py
│       │   ├── epic_parser
│       │   │   ├── __init__.py
│       │   │   └── parser.py
│       │   └── mbe_app
│       │       └── __init__.py
│       └── characterization
│           ├── __init__.py
│           └── schema.py
└── tests
    └── data
        └── mbe
```

### Data model description

Each method has a dedicated [module](https://docs.python.org/3/tutorial/modules.html), i. e., a python file.

#### Dependencies

This plugin uses the NOMAD community plugins. Check the repos and their documentations:

- [nomad-material-processing repo](https://github.com/FAIRmat-NFDI/nomad-material-processing), [nomad-material-processing docs](https://fairmat-nfdi.github.io/nomad-material-processing/)
- [nomad-measurements repo](https://github.com/FAIRmat-NFDI/nomad-measurements), [nomad-measurements docs](https://fairmat-nfdi.github.io/nomad-measurements/)

#### mbe.materials



#### mbe.processes

#### mbe.instrument

#### nomad_material_processing.solution.general

`solution.general` module contains the following entry sections (used to create
NOMAD [entries](https://nomad-lab.eu/prod/v1/docs/reference/glossary.html#entry)):

##### `Solution`
Describes liquid solutions by extending the
[`CompositeSystem`](https://nomad-lab.eu/prod/v1/docs/howto/customization/base_sections.html#system) with quantities: _pH_, _mass_,
_calculated_volume_, _measured_volume_, _density_, and sub-sections:
_solvents_, _solutes_, and _solution_storage_.

```py
# pseudocode for `Solution` datamodel
class Solution(CompositeSystem, EntryData):
    ph_value: float
    mass: float
    calculated_volume: float
    measured_volume: float
    density: float
    components: list[
        Union(
            SolutionComponent,
            SolutionComponentReference,
        )
    ]
    solutes: list[SolutionComponent]
    solvents: list[SolutionComponent]
    solution_storage: SolutionStorage
```

!!! hint
    The _measured_volume_ field is user-defined. By default, the automation in
    `Solution` uses _calculated_volume_, but if _measured_volume_ is provided, it will take
    precedence. This is useful when the final solution volume differs from the sum of its
    component volumes, and should be specified by the user.
The _components_ sub-section, inherited from `CompositeSystem` and re-defined, is used to describe
a list of components used in the solution. Each of them contributes to the _mass_ and
_calculated_volume_ of the solution. The component can either nest a
sub-section describing its composition, or can be another `Solution` entry connected
via reference.
These options are are handled by
`SolutionComponent` and `SolutionComponentReference` sections respectively.

Let's take a closer look at each of them.


`SolutionComponent` extends `PureSubstanceComponent` with quantities:
_component_role_, _mass_, _volume_, _density_, and sub-section: _molar_concentration_.
The _pure_substance_ sub-section inherited from `PureSubstanceComponent` specifies the
chemical compound. This information along with the mass of the component and
total volume of the solution is used to automatically determine the molar concentration of
the component, populating the corresponding sub-section.
Based on the _component_role_, the components are copied over to either
`Solution.solvents` or `Solution.solutes`.
```py
class SolutionComponent(PureSubstanceComponent):
    component_role: Enum('Solvent', 'Solute')
    mass: float
    volume: float
    density: float
    molar_concentration: MolarConcentration
```


`SolutionComponentReference` makes a reference to another `Solution` entry and specifies
the amount used. Based on this, _solutes_ and _solvents_ of the referenced solution are
copied over to the first solution. Their mass and volume are adjusted based on the
amount of the referenced solution used.
```py
class SolutionComponentReference(SystemComponent):
    mass: float
    volume: float
    system: Solution
```

Both `Solution.solvents` and `Solution.solutes` are a list of `SolutionComponent`. The
molar concentration of each of them is automatically determined. Additionally, if the
list has multiple `SolutionComponent` representing the same chemical entity, there are
combined into one.

The _solution_storage_ uses `SolutionStorage` section to describe storage conditions
, i.e., temperature and atmosphere, along with preparation and expiry dates.

##### `SolutionPreparation`
Extends [`Process`](https://nomad-lab.eu/prod/v1/docs/howto/customization/base_sections.html#process)
to describe the recipe for solution preparation. It generates a `Solution` entry based
on the data added to it.
