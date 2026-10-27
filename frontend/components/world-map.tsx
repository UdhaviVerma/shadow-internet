"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { geoGraticule10, geoNaturalEarth1, geoPath } from "d3";
import type { Location } from "@/lib/types";

export function WorldMap({ locations }: { locations: Location[] }) {
  const container = useRef<HTMLDivElement>(null);
  const [mapError, setMapError] = useState("");
  const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
  const projection = useMemo(() => geoNaturalEarth1().scale(118).translate([340, 170]), []);
  const path = geoPath(projection);
  useEffect(() => {
    if (!token || !container.current) return;
    let active = true;
    let dispose: (() => void) | undefined;
    import("mapbox-gl").then(({ default: mapboxgl }) => {
      if (!active || !container.current) return;
      const map = new mapboxgl.Map({
        container: container.current, style: "mapbox://styles/mapbox/dark-v11",
        center: [15, 20], zoom: 0.8, accessToken: token,
      });
      map.addControl(new mapboxgl.NavigationControl(), "top-right");
      for (const location of locations) {
        new mapboxgl.Marker({ color: "#42e3c2" })
          .setLngLat([location.longitude, location.latitude])
          .setPopup(new mapboxgl.Popup().setText(`${location.country}: ${location.ip}. ${location.source}`))
          .addTo(map);
      }
      map.on("error", () => setMapError("Mapbox could not load. Check the public token, URL restrictions and network."));
      dispose = () => map.remove();
    }).catch(() => setMapError("Mapbox could not initialize; map module unavailable."));
    return () => { active = false; dispose?.(); };
  }, [locations, token]);
  return <div className="world-panel">
    {token ? <div ref={container} className="mapbox-container" aria-label="Approximate infrastructure IP locations" /> :
      <svg viewBox="0 0 680 340" role="img" aria-label="Approximate IP geolocation world projection">
        <defs><radialGradient id="ocean"><stop stopColor="#122e39" /><stop offset="1" stopColor="#0b131c" /></radialGradient></defs>
        <path d={path({ type: "Sphere" }) ?? ""} fill="url(#ocean)" stroke="#27424f" />
        <path d={path(geoGraticule10()) ?? ""} fill="none" stroke="#21404c" strokeWidth=".6" />
        {locations.map((location, index) => {
          const point = projection([location.longitude, location.latitude]);
          return point ? <g key={`${location.ip}-${index}`}><circle cx={point[0]} cy={point[1]} r="10" fill="#42e3c219" /><circle cx={point[0]} cy={point[1]} r="3" fill="#42e3c2" /><text x={point[0] + 8} y={point[1] - 8} fill="#b9d1db" fontSize="10">{location.country}</text></g> : null;
        })}
      </svg>}
    {mapError && <p className="error" role="alert">{mapError}</p>}
    <div className="map-caption"><span>{token ? "MAPBOX" : "D3 WORLD PROJECTION / NO MAP TOKEN REQUIRED"}</span><span>{locations.length} LOCATION OBSERVATIONS</span></div>
    <p className="disclaimer">Approximate IP geolocation, not origin server location or routing countries. Anycast and CDN edges may vary by observer.</p>
  </div>;
}
