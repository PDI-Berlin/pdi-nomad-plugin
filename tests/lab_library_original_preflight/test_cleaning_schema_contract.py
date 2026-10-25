from nomad_material_processing.general import CleaningRecipe, CleaningStep
from nomad.datamodel.metainfo.basesections.v1 import (
    CompositeSystemReference,
    InstrumentReference,
)

expected = {
    CleaningRecipe: {
        "name", "datetime", "lab_id", "description", "method",
        "location", "end_time", "tags", "recipe", "duration",
    },
    CleaningStep: {
        "name", "start_time", "comment", "duration",
        "temperature", "agitation",
    },
    CompositeSystemReference: {"name", "lab_id", "reference"},
    InstrumentReference: {"name", "lab_id", "reference"},
}

for cls, fields in expected.items():
    assert fields <= set(cls.m_def.all_quantities), cls.__name__
    assert cls.__module__.startswith(("nomad.", "nomad_material_processing."))
    print("PASS:", cls.__name__, "original quantities")

for parent, section, child, repeats in [
    (CleaningRecipe, "steps", CleaningStep, True),
    (CleaningRecipe, "instruments", InstrumentReference, True),
    (CleaningRecipe, "samples", CompositeSystemReference, True),
    (CleaningStep, "cleaning_reagents", CompositeSystemReference, False),
]:
    definition = parent.m_def.all_sub_sections[section]
    assert definition.sub_section.section_cls is child
    assert bool(definition.repeats) is repeats
    print("PASS:", parent.__name__ + "." + section)

assert str(CleaningStep.m_def.all_quantities["duration"].unit) == "second"
assert str(CleaningStep.m_def.all_quantities["temperature"].unit) == "degree_Celsius"
assert str(CleaningRecipe.m_def.all_quantities["duration"].unit) == "second"

values = CleaningStep.m_def.all_quantities["agitation"].type._unique_values
assert {"Sonication", "Magnetic Stirring"} <= set(values)
print("PASS: Original units and agitation enum")
