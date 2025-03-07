import numpy as np
from nomad.datamodel.data import EntryData
from nomad.datamodel.hdf5 import HDF5Reference
from nomad.datamodel.metainfo.annotations import (
    ELNAnnotation,
    ELNComponentEnum,
    H5WebAnnotation,
)
from nomad.datamodel.metainfo.basesections import (
    Measurement,
    MeasurementResult,
)
from nomad.metainfo import Datetime, Quantity, SchemaPackage, Section, SubSection
from nomad_material_processing.general import (
    TimeSeries,
)

from pdi_nomad_plugin.general.schema import (
    PDICategory,
)

m_package = SchemaPackage()


class AFMresults(MeasurementResult):
    """
    The results of an AFM measurement
    """

    roughness = Quantity(
        type=np.float64,
        description='RMS roughness value obtained by AFM',
        a_eln={'component': 'NumberEditQuantity', 'defaultDisplayUnit': 'picometer'},
        unit='picometer',
    )
    # surface_features = Quantity(
    #     type=MEnum(["Step Flow", "Step Bunching", "2D Island"]),
    #     a_eln={"component": "EnumEditQuantity"},
    # )
    surface_features = Quantity(
        type=str,
        a_eln={'component': 'StringEditQuantity'},
    )
    scale = Quantity(
        type=np.float64,
        description='scale of the image, to be multiplied by 5 to know the image size',
        a_eln={'component': 'NumberEditQuantity', 'defaultDisplayUnit': 'nanometer'},
        unit='nanometer',
    )
    image = Quantity(
        type=str,
        description='image showing the thickness measurement points',
        a_browser={'adaptor': 'RawFileAdaptor'},
        a_eln={'component': 'FileEditQuantity'},
    )
    crop_image = Quantity(
        type=str,
        description='crop image ready to be used for AI-based analysis',
        a_browser={'adaptor': 'RawFileAdaptor'},
        a_eln={'component': 'FileEditQuantity'},
    )


class MassSpectrometry(Measurement, EntryData):
    """
    line-of-sight Quadrupole Mass Spectometry
    """

    pass


class RHEEDMeasurement(Measurement, EntryData):
    """
    Reflection High Energy Electron Diffraction (RHEED) measurement
    """

    pass


class AFMmeasurement(Measurement, EntryData):
    """
    Class autogenerated from yaml schema.
    """

    m_def = Section(
        a_eln={'hide': ['steps']},
        categories=[PDICategory],
        label='AFM',
    )

    method = Quantity(
        type=str,
        default='AFM (PDI MBE)',
    )
    tags = Quantity(
        type=str,
        shape=['*'],
        description='Searchable tags for this entry. Use Explore tab for searching.',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    description = Quantity(
        type=str,
        a_eln={'component': 'StringEditQuantity'},
    )
    datetime = Quantity(
        type=Datetime,
        a_eln={'component': 'DateTimeEditQuantity'},
    )
    results = SubSection(
        section_def=AFMresults,
        repeats=True,
    )


class LiMiresults(MeasurementResult):
    """
    The results of a Light Microscope measurement
    """

    image = Quantity(
        type=str,
        description='image showing the thickness measurement points',
        a_browser={'adaptor': 'RawFileAdaptor'},
        a_eln={'component': 'FileEditQuantity'},
    )
    crop_image = Quantity(
        type=str,
        description='crop image ready to be used for AI-based analysis',
        a_browser={'adaptor': 'RawFileAdaptor'},
        a_eln={'component': 'FileEditQuantity'},
    )
    scale = Quantity(
        type=np.float64,
        description='scale of the image',
        a_eln={'component': 'NumberEditQuantity', 'defaultDisplayUnit': 'micrometer'},
        unit='micrometer',
    )


class LightMicroscope(Measurement, EntryData):
    """
    Class autogenerated from yaml schema.
    """

    m_def = Section(
        a_eln={'hide': ['steps']},
        categories=[PDICategory],
        label='Light Microscope',
    )
    method = Quantity(
        type=str,
        default='Light Microscope (MBE PDI)',
    )
    tags = Quantity(
        type=str,
        shape=['*'],
        description='Searchable tags for this entry. Use Explore tab for searching.',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    datetime = Quantity(
        type=Datetime,
        a_eln={'component': 'DateTimeEditQuantity'},
    )
    results = SubSection(
        section_def=LiMiresults,
        repeats=True,
    )


class PyrometerTemperature(TimeSeries):
    """
    The temperature of the substrate measured by a pyrometer.
    """

    m_def = Section(a_h5web=H5WebAnnotation(axes='time', signal='value'))
    value = Quantity(
        type=HDF5Reference,
        unit='kelvin',
        shape=[],
    )
    time = Quantity(
        type=HDF5Reference,
        description='The process time when each of the values were recorded.',
        shape=[],
    )


class LaserReflectanceIntensity(TimeSeries):
    """
    The current measured during the pyrometry experiment.
    """

    m_def = Section(a_h5web=H5WebAnnotation(axes='time', signal='value'))
    value = Quantity(
        type=HDF5Reference,
        shape=[],
    )
    time = Quantity(
        type=HDF5Reference,
        description='The process time when each of the values were recorded.',
        shape=[],
    )


class Pyrometry(Measurement):
    """
    Class autogenerated from yaml schema.
    """

    m_def = Section(
        a_eln={'hide': ['steps']},
        categories=[PDICategory],
        label='Pyrometry',
    )

    method = Quantity(
        type=str,
        default='Pyrometry (MBE PDI)',
    )
    tags = Quantity(
        type=str,
        shape=['*'],
        description='Searchable tags for this entry. Use Explore tab for searching.',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    description = Quantity(
        type=str,
        a_eln={'component': 'StringEditQuantity'},
    )

    pyrometer_temperature = SubSection(
        section_def=PyrometerTemperature,
    )


class LaserReflectance(Measurement, EntryData):
    """
    Class autogenerated from yaml schema.
    """

    m_def = Section(
        a_eln={'hide': ['steps']},
        categories=[PDICategory],
        label='Laser Reflectance',
    )

    method = Quantity(
        type=str,
        default='Laser Reflectance (MBE PDI)',
    )
    tags = Quantity(
        type=str,
        shape=['*'],
        description='Searchable tags for this entry. Use Explore tab for searching.',
        a_eln=ELNAnnotation(
            component='StringEditQuantity',
        ),
    )
    description = Quantity(
        type=str,
        a_eln={'component': 'StringEditQuantity'},
    )
    wavelength = Quantity(
        type=float,
        unit='meter',
        description="""
        Wavelength of the light used for the pyrometry measurement.
        """,
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            defaultDisplayUnit='nanometer',
        ),
    )
    incidence_angle = Quantity(
        type=float,
        unit='degree',
        description="""
        The angle of incidence of the light used for the pyrometry measurement.
        """,
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            defaultDisplayUnit='degree',
        ),
    )
    laser_reflectance_intensity = SubSection(
        section_def=LaserReflectanceIntensity,
    )
