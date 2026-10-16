"""Contracts for original NOMAD substrate geometry schemas (no custom recipe)."""

from pathlib import Path

import pytest

from nomad_material_processing.general import (
    Geometry,
    SquareCuboid,
    RectangleCuboid,
    Cylinder,
    CylinderSector,
)
from pdi_nomad_plugin.general.schema import SampleCutPDI
from pdi_nomad_plugin.mbe.materials import SubstrateMbe


ROOT = Path(__file__).resolve().parents[1]


def test_no_custom_geometry_schemas():
    source = (ROOT / "src/pdi_nomad_plugin/general/schema.py").read_text(
        encoding="utf-8-sig"
    )
    for name in ("SubstrateGeometryPDI", "SampleCutGeometryPDI", "SampleCutRecipePDI"):
        assert f"class {name}(" not in source


def test_all_subsections_use_original_nomad_geometry():
    for cls, field in (
        (SubstrateMbe, "geometry"),
        (SampleCutPDI, "children_geometry"),
    ):
        subsection = cls.m_def.all_sub_sections[field]
        assert subsection.sub_section.section_cls is Geometry


@pytest.mark.parametrize(
    "geometry",
    [
        SquareCuboid(width=0.005, length=0.005, height=0.0005),
        RectangleCuboid(width=0.005, length=0.010, height=0.0005),
        Cylinder(radius=0.0254, height=0.0005),
        CylinderSector(radius=0.0254, central_angle=90, height=0.0005),
    ],
)
def test_sample_cut_geometry_roundtrip(geometry):
    """Test the existing cut process; the removed custom recipe is not reintroduced."""
    cut = SampleCutPDI(children_geometry=geometry, number_of_samples=4)
    restored = SampleCutPDI.m_from_dict(cut.m_to_dict())
    actual = restored.children_geometry
    assert actual.m_def is geometry.m_def
    assert actual.m_to_dict() == geometry.m_to_dict()
    assert restored.number_of_samples == 4
