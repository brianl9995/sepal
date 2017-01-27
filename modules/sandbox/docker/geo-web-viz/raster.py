from subprocess import call

import gdal
import mapnik
import osr

from config import to_file, to_path
from layer import Layer


def band_count(raster_file):
    ds = gdal.OpenShared(raster_file)
    if not ds:
        return 0
    band = 1
    while True:
        if not ds.GetRasterBand(band):
            return band - 1
        band += 1


def band_info(raster_file, band_index, nodata, use_file_nodata):
    ds = gdal.OpenShared(raster_file, gdal.GA_Update)
    band = ds.GetRasterBand(band_index)

    if not band.GetOverviewCount():
        call([
            'gdaladdo', '-ro', '-q', '-b', str(band_index), '-r', 'average', raster_file, '2', '4', '8'
        ])

    old_nodata = band.GetNoDataValue()
    try:
        if nodata:
            band.SetNoDataValue(nodata)
        elif use_file_nodata:
            nodata = old_nodata
        else:
            band.DeleteNoDataValue()

        if old_nodata == nodata:
            (min, max, mean, std_dev) = band.GetStatistics(True, True)
        else:
            (min, max, mean, std_dev) = band.ComputeStatistics(False)

        histogram = band.GetHistogram(min, max, 256, approx_ok=1)
    finally:
        if old_nodata:
            band.SetNoDataValue(old_nodata)
        elif band.GetNoDataValue():
            band.DeleteNoDataValue()
    return {
        'nodata': nodata,
        'min': min,
        'max': max,
        'mean': mean,
        'stdDev': std_dev,
        'histogram': histogram
    }


def from_dict(layer_dict):
    return RasterLayer(
        id=layer_dict['id'],
        file=to_file(layer_dict['path']),
        bands=_Band.from_dict(layer_dict['bands'])
    )


# noinspection PyUnresolvedReferences
class RasterLayer(Layer):
    """Represents a map layer."""

    concurrent = False

    def __init__(self, id, file, bands):
        """Creates a raster layer.

        :param file: Path to raster image.
        :type file: str

        :param bands: Iterable of gwv.Band instances to include.
        :type bands: iterable
        """
        super(RasterLayer, self).__init__()
        self.id = id
        self.file = file
        # self._add_overview(bands)
        self.band_layers = [
            _BandLayer(file, band)
            for band in bands]
        self._persist_nodata(bands)

    def append_to(self, map):
        """Appends Mapnik layers and styles for the bands in this layer.

        :param map: The mapnik Map.
        :type map: mapnik.Map
        """
        for band_layer in self.band_layers:
            band_layer.append_to(map)

    def to_dict(self):
        return {
            'id': self.id,
            'type': 'raster',
            'path': to_path(self.file),
            'bands': [band_layer.band.to_dict() for band_layer in self.band_layers],
            'bounds': self.bounds()
        }

    def update(self, layer_dict):
        layer = self.to_dict()
        layer.update(layer_dict)
        updated_layer = from_dict(layer)
        bands = [band_layer.band for band_layer in updated_layer.band_layers]
        self._persist_nodata(bands)
        return updated_layer

    def _persist_nodata(self, bands):
        ds = gdal.OpenShared(self.file, gdal.GA_Update)
        for band in bands:
            gdal_band = ds.GetRasterBand(int(band.index))
            nodata = band.nodata
            if nodata:
                gdal_band.SetNoDataValue(float(nodata))
            else:
                gdal_band.DeleteNoDataValue()

    def features(self, lat, lng):
        return [
            self.band_value(band_layer, lat, lng)
            for band_layer in self.band_layers
            ]

    def band_value(self, band_layer, lat, lng):
        features = self.layer_features(band_layer.band.index - 1, lat, lng)
        if features:
            return features[0]['value']
        return None

    def _flatten(self, items):
        if items == []:
            return items
        if isinstance(items[0], list):
            return self._flatten(items[0]) + self._flatten(items[1:])
        return items[:1] + self._flatten(items[1:])


class _BandLayer(object):
    def __init__(self, file, band):
        self.file = file
        self.band = band
        self.style = self.create_style()
        self.mapnik_datasource = mapnik.Gdal(
            file=file,
            band=band.index,
            shared=True,
            nodata=band.nodata,
            nodata_tolerance=band.nodata_tolerance
        )
        self.mapnik_layer = self.create_mapnik_layer()

    def create_mapnik_layer(self):
        layer = mapnik.Layer(self.band.name)
        layer.srs = self.extract_srs(self.file)
        layer.datasource = self.mapnik_datasource
        layer.styles.append(self.band.name)
        return layer

    def extract_srs(self, file):
        ds = gdal.Open(file)
        projInfo = ds.GetProjection()
        spatialRef = osr.SpatialReference()
        spatialRef.ImportFromWkt(projInfo)
        return spatialRef.ExportToProj4()

    def create_style(self):
        symbolizer = mapnik.RasterSymbolizer()
        symbolizer.colorizer = self.create_colorizer()
        rule = mapnik.Rule()
        rule.symbols.append(symbolizer)
        style = mapnik.Style()
        style.comp_op = mapnik.CompositeOp.plus
        style.rules.append(rule)
        return style

    def create_colorizer(self):
        band = self.band
        colorizer = mapnik.RasterColorizer(mapnik.COLORIZER_LINEAR, mapnik.Color('#00000000'))
        for stop, color in band.palette:
            colorizer.add_stop(stop, mapnik.COLORIZER_LINEAR, mapnik.Color(str(color)))
        return colorizer

    def append_to(self, map):
        map.layers.append(self.mapnik_layer)
        map.append_style(self.band.name, self.style)


class _Band(object):
    """Represents a band to include in a map layer, and it's visualisation properties"""

    def __init__(self, index, nodata, nodata_tolerance, palette):
        """Creates a band.

        :param index: Index of band in image.
        :type index: int

        :param min: Value to map to first color in palette.
        :type min: float

        :param max: Value to map to last color in palette.
        :type max: float

        :param nodata: Value to assign pixels with no data.
        :type nodata: float

        :param nodata_tolerance: Distance from nodata value pixels still are considered nodata.
        :type nodata_tolerance: float

        :param palette: Iterable of hex-color strings, which will be used for the values in the band.
        :type palette: iterable
        """
        self.name = 'B' + str(index)
        self.index = index
        self.nodata = nodata
        self.nodata_tolerance = nodata_tolerance
        self.palette = palette

    def to_dict(self):
        return {
            'index': self.index,
            'nodata': self.nodata if self.nodata else '',
            'nodataTolerance': self.nodata_tolerance,
            'palette': self.palette
        }

    @staticmethod
    def from_dict(bands_dict):
        return [
            _Band(
                index=int(band['index']),
                nodata=float(band['nodata']) if band.get('nodata', None) else None,
                nodata_tolerance=float(band.get('nodataTolerance', 1e-12)),
                palette=band['palette']
            )
            for band in bands_dict
            ]
