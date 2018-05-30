import FusionTable from './fusionTable'
import {map} from './map'
import './map.module.css'
import Polygon from './polygon'

export const countryFusionTable = '1iCjlLvNDpVtI80HpYrxEtjnw2w6sLEHX0QVTLqqU'

export const removeAoiLayer = (contextId) => {
    map.getLayers(contextId).remove('aoi')
}

export const setAoiLayer = (contextId, aoi, destroy$, onInitialized) => {
    const id = 'aoi'
    const layers = map.getLayers(contextId)
    const setCountryLayer = () =>
        FusionTable.setLayer(layers, {
            id,
            table: countryFusionTable,
            keyColumn: 'id',
            key: aoi.areaCode || aoi.countryCode,
            bounds: aoi.bounds
        }, destroy$, onInitialized)

    const setFusionTableLayer = () =>
        FusionTable.setLayer(layers, {
            id,
            table: aoi.id,
            keyColumn: aoi.keyColumn,
            key: aoi.key,
            bounds: aoi.bounds
        }, destroy$, onInitialized)

    const setPolygonLayer = () =>
        Polygon.setLayer(layers, {
            id,
            path: aoi.path
        }, destroy$, onInitialized)

    switch (aoi && aoi.type) {
        case 'country':
            return setCountryLayer()
        case 'fusionTable':
            return setFusionTableLayer()
        case 'polygon':
            return setPolygonLayer()
        default:
            removeAoiLayer(contextId)
    }
}

