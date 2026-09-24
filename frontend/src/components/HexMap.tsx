import { useState, useCallback } from 'react'
import Map, { Layer, Source, Popup } from 'react-map-gl/maplibre'
import type { MapMouseEvent, MapGeoJSONFeature } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useStore, levelColor } from '../store'
import type { DistrictPulse, PulseLevel } from '../types'

const BASEMAP = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

const INITIAL_VIEW = {
  latitude: 26.9124,
  longitude: 75.7873,
  zoom: 11.5,
}

interface HexFeature {
  type: 'Feature'
  geometry: { type: 'Polygon'; coordinates: number[][][] }
  properties: { district: string; level: PulseLevel; pulse: number; color: string }
}

function districtToHex(d: DistrictPulse): HexFeature | null {
  // Use district centroid H3 cell — approximate from lat/lon
  // We generate a fixed GeoJSON polygon per district name
  // In production this would use h3.latlng_to_cell but we approximate here
  const CENTROIDS: Record<string, [number, number]> = {
    'Walled City':    [26.9239, 75.8267],
    'Mansarovar':     [26.8578, 75.7726],
    'Vaishali Nagar': [26.9107, 75.7397],
    'Malviya Nagar':  [26.8517, 75.8103],
    'C-Scheme':       [26.9115, 75.8054],
    'Tonk Road':      [26.8748, 75.8160],
    'Sodala':         [26.9385, 75.7762],
    'Jagatpura':      [26.8365, 75.8467],
  }
  const [lat, lon] = CENTROIDS[d.name] ?? [26.9124, 75.7873]

  // Build a rough hexagon polygon (~0.7 km radius)
  const R = 0.007 // degrees ≈ 0.7 km
  const coords: number[][] = []
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i
    coords.push([lon + R * Math.cos(angle), lat + R * Math.sin(angle)])
  }
  coords.push(coords[0]) // close ring

  return {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [coords] },
    properties: {
      district: d.name,
      level: d.level,
      pulse: d.pulse,
      color: levelColor(d.level),
    },
  }
}

function buildGeoJSON(districts: DistrictPulse[]) {
  return {
    type: 'FeatureCollection' as const,
    features: districts.map(districtToHex).filter(Boolean),
  }
}

export function HexMap() {
  const city = useStore((s) => s.city)
  const [popup, setPopup] = useState<{ lat: number; lon: number; district: DistrictPulse } | null>(null)

  const geoJSON = city ? buildGeoJSON(city.districts) : { type: 'FeatureCollection' as const, features: [] }

  const onClick = useCallback((e: MapMouseEvent & { features?: MapGeoJSONFeature[] }) => {
    const f = e.features?.[0]
    if (!f) return
    const props = f.properties as HexFeature['properties']
    const district = city?.districts.find((d) => d.name === props.district)
    if (!district) return
    const coords = (f.geometry as { type: 'Polygon'; coordinates: number[][][] }).coordinates[0]
    const lons = coords.map((c: number[]) => c[0])
    const lats = coords.map((c: number[]) => c[1])
    setPopup({
      lon: lons.reduce((a: number, b: number) => a + b) / lons.length,
      lat: lats.reduce((a: number, b: number) => a + b) / lats.length,
      district,
    })
  }, [city])

  return (
    <div className="map-container relative" style={{ height: '100%', minHeight: 320 }}>
      <Map
        initialViewState={INITIAL_VIEW}
        mapStyle={BASEMAP}
        interactiveLayerIds={['hex-fill']}
        onClick={onClick as (e: MapMouseEvent) => void}
        attributionControl={false}
      >
        <Source id="hexes" type="geojson" data={geoJSON}>
          <Layer
            id="hex-fill"
            type="fill"
            paint={{
              'fill-color': ['get', 'color'],
              'fill-opacity': 0.45,
            }}
          />
          <Layer
            id="hex-outline"
            type="line"
            paint={{
              'line-color': ['get', 'color'],
              'line-width': 1.5,
              'line-opacity': 0.8,
            }}
          />
        </Source>

        {popup && (
          <Popup
            latitude={popup.lat}
            longitude={popup.lon}
            onClose={() => setPopup(null)}
            closeButton
            closeOnClick={false}
            style={{ background: 'var(--color-surface)', color: 'var(--color-text)', borderRadius: 8 }}
          >
            <div className="p-2 min-w-[140px]">
              <div className="font-semibold">{popup.district.name}</div>
              <div className="text-sm" style={{ color: levelColor(popup.district.level) }}>
                {popup.district.level} · {popup.district.pulse}
              </div>
              <div className="text-xs mt-1" style={{ color: 'var(--color-text-2)' }}>
                {Object.entries(popup.district.components)
                  .filter(([, v]) => v !== null)
                  .map(([k, v]) => `${k}: ${((v as number) * 100).toFixed(0)}%`)
                  .join(' · ')}
              </div>
            </div>
          </Popup>
        )}
      </Map>

      {/* Attribution */}
      <div
        className="absolute bottom-2 right-2 text-xs"
        style={{ color: 'var(--color-muted)', pointerEvents: 'none' }}
      >
        © CARTO · © OpenStreetMap
      </div>
    </div>
  )
}
