import React, { useState, useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import {
  Search,
  Plus,
  Trash2,
  ArrowUp,
  ArrowDown,
  Zap,
  Printer,
  CheckSquare,
  Square,
  RotateCcw,
  Building2,
  MapPin,
} from 'lucide-react';

const rawApiUrl = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const API_URL = rawApiUrl.startsWith('http') ? rawApiUrl : `https://${rawApiUrl}`;

function safeNum(val, fallback = 0) {
  const n = Number(val);
  return Number.isFinite(n) ? n : fallback;
}

function sanitizeStop(item, idx = 0) {
  if (!item || typeof item !== 'object') return null;
  return {
    id: String(item.id ?? `loc-${idx}`),
    gcpsId: String(item.gcpsId ?? ''),
    name: String(item.name ?? 'Unknown Location'),
    type: String(item.type ?? ''),
    cluster: String(item.cluster ?? 'CENTRAL GWINNETT'),
    lat: safeNum(item.lat, 33.9562),
    lon: safeNum(item.lon, -83.988),
  };
}

function StreetRouteMap({ depot, stops, geometry, isOptimized }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const layerGroupRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, {
      center: [33.96, -84.02],
      zoom: 11,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map);

    layerGroupRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      layerGroupRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const group = layerGroupRef.current;
    if (!map || !group || !depot) return;

    group.clearLayers();
    const bounds = [];

    const lineCoords =
      Array.isArray(geometry) && geometry.length > 1
        ? geometry
        : [
            [depot.lat, depot.lon],
            ...stops.map((s) => [s.lat, s.lon]),
          ];

    if (lineCoords.length > 1) {
      L.polyline(lineCoords, {
        color: isOptimized ? '#15803d' : '#1d4ed8',
        weight: 6,
        opacity: 0.9,
      }).addTo(group);
    }

    const startIcon = L.divIcon({
      className: '',
      html: `<div style="background:#0f172a;color:#fff;font-weight:800;font-size:12px;padding:4px 8px;border-radius:8px;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.4);white-space:nowrap;">START</div>`,
      iconSize: [54, 28],
      iconAnchor: [27, 14],
    });
    L.marker([depot.lat, depot.lon], { icon: startIcon })
      .bindPopup(`<strong>START:</strong> ${depot.name} (Loc #${depot.gcpsId})`)
      .addTo(group);
    bounds.push([depot.lat, depot.lon]);

    stops.forEach((stop, index) => {
      const bg = isOptimized ? '#15803d' : '#1d4ed8';
      const stopIcon = L.divIcon({
        className: '',
        html: `<div style="background:${bg};color:#fff;font-weight:800;font-size:15px;width:32px;height:32px;border-radius:9999px;display:flex;align-items:center;justify-content:center;border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.4);">${
          index + 1
        }</div>`,
        iconSize: [32, 32],
        iconAnchor: [16, 16],
      });
      L.marker([stop.lat, stop.lon], { icon: stopIcon })
        .bindPopup(`<strong>Stop ${index + 1}:</strong> ${stop.name} (Loc #${stop.gcpsId})`)
        .addTo(group);
      bounds.push([stop.lat, stop.lon]);
    });

    if (bounds.length === 1) {
      map.setView(bounds[0], 13);
    } else if (bounds.length > 1) {
      map.fitBounds(bounds, { padding: [45, 45] });
    }
  }, [depot, stops, geometry, isOptimized]);

  return (
    <div
      ref={containerRef}
      style={{ height: '380px', width: '100%' }}
      className="rounded-xl border-2 border-slate-300 z-0"
    />
  );
}

export default function App() {
  const [depot, setDepot] = useState(null);
  const [depotSearch, setDepotSearch] = useState('');
  const [depotDropdownOpen, setDepotDropdownOpen] = useState(false);

  const [locations, setLocations] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [clusterFilter, setClusterFilter] = useState('ALL');
  const [selectedStops, setSelectedStops] = useState([]);
  const [routeStats, setRouteStats] = useState({
    total_miles: 0,
    total_minutes: 0,
    legs: [],
    geometry: [],
  });
  const [isOptimized, setIsOptimized] = useState(false);
  const [savedMiles, setSavedMiles] = useState(0);
  const [completedIds, setCompletedIds] = useState({});
  const [loadingRoute, setLoadingRoute] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    fetch(`${API_URL}/api/locations`)
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Error loading locations');
        const cleanLocations = (data.locations || []).map(sanitizeStop).filter(Boolean);
        setDepot(sanitizeStop(data.depot) || cleanLocations[0] || null);
        setLocations(cleanLocations);
      })
      .catch((err) => setErrorMessage(err.message));
  }, []);

  const refreshRoadRoute = async (currentDepot, currentStops) => {
    if (!currentDepot || currentStops.length === 0) {
      setRouteStats({ total_miles: 0, total_minutes: 0, legs: [], geometry: [] });
      return;
    }
    try {
      setLoadingRoute(true);
      const res = await fetch(`${API_URL}/api/route`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ depot: currentDepot, stops: currentStops }),
      });
      const data = await res.json();
      if (res.ok) {
        setRouteStats({
          total_miles: safeNum(data.total_miles, 0),
          total_minutes: safeNum(data.total_minutes, 0),
          legs: Array.isArray(data.legs) ? data.legs : [],
          geometry: Array.isArray(data.geometry) ? data.geometry : [],
        });
      }
    } finally {
      setLoadingRoute(false);
    }
  };

  const supportFacilities = locations.filter((loc) => loc.type === 'SF');
  const clusters = ['ALL', ...Array.from(new Set(locations.map((l) => l.cluster))).sort()];

  const matchingDepots = locations.filter((loc) => {
    const q = depotSearch.toLowerCase().trim();
    if (!q) return loc.type === 'SF';
    return (
      loc.name.toLowerCase().includes(q) ||
      loc.gcpsId.toLowerCase().includes(q) ||
      loc.cluster.toLowerCase().includes(q)
    );
  });

  const filteredLocations = locations.filter((loc) => {
    const matchesCluster = clusterFilter === 'ALL' || loc.cluster === clusterFilter;
    const q = searchTerm.toLowerCase().trim();
    const matchesSearch =
      !q ||
      loc.name.toLowerCase().includes(q) ||
      loc.gcpsId.toLowerCase().includes(q) ||
      loc.cluster.toLowerCase().includes(q);
    return matchesCluster && matchesSearch;
  });

  const handleSelectDepot = (chosen) => {
    if (!chosen) return;
    const nextStops = selectedStops.filter((s) => s.id !== chosen.id);
    setDepot(chosen);
    setSelectedStops(nextStops);
    setDepotSearch('');
    setDepotDropdownOpen(false);
    setIsOptimized(false);
    setSavedMiles(0);
    refreshRoadRoute(chosen, nextStops);
  };

  const handleAddStop = (location) => {
    if (!location || (depot && depot.id === location.id)) return;
    if (selectedStops.some((s) => s.id === location.id)) return;
    const nextStops = [...selectedStops, location];
    setSelectedStops(nextStops);
    setIsOptimized(false);
    setSavedMiles(0);
    refreshRoadRoute(depot, nextStops);
  };

  const handleRemoveStop = (id) => {
    const nextStops = selectedStops.filter((s) => s.id !== id);
    setSelectedStops(nextStops);
    setIsOptimized(false);
    setSavedMiles(0);
    refreshRoadRoute(depot, nextStops);
  };

  const handleMoveStop = (index, direction) => {
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= selectedStops.length) return;
    const nextStops = [...selectedStops];
    [nextStops[index], nextStops[targetIndex]] = [nextStops[targetIndex], nextStops[index]];
    setSelectedStops(nextStops);
    setIsOptimized(false);
    setSavedMiles(0);
    refreshRoadRoute(depot, nextStops);
  };

  const handleOptimize = async () => {
    if (!depot || selectedStops.length < 2) return;
    try {
      setLoadingRoute(true);
      setErrorMessage('');
      const res = await fetch(`${API_URL}/api/optimize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ depot, stops: selectedStops }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Optimization failed');

      const cleanStops = (data.stops || []).map(sanitizeStop).filter(Boolean);
      setSelectedStops(cleanStops);
      setSavedMiles(safeNum(data.saved_miles, 0));
      setRouteStats({
        total_miles: safeNum(data.total_miles, 0),
        total_minutes: safeNum(data.total_minutes, 0),
        legs: Array.isArray(data.legs) ? data.legs : [],
        geometry: Array.isArray(data.geometry) ? data.geometry : [],
      });
      setIsOptimized(true);
    } catch (err) {
      setErrorMessage(err.message);
    } finally {
      setLoadingRoute(false);
    }
  };

  const handleReset = () => {
    setSelectedStops([]);
    setRouteStats({ total_miles: 0, total_minutes: 0, legs: [], geometry: [] });
    setIsOptimized(false);
    setSavedMiles(0);
    setCompletedIds({});
  };

  const toggleCheck = (id) => {
    setCompletedIds((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900 p-4 md:p-6 font-sans">
      {/* HEADER */}
      <header className="max-w-7xl mx-auto bg-white border-2 border-slate-300 rounded-2xl p-5 mb-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <h1 className="text-3xl font-extrabold text-slate-900">GCPS Daily Route Planner</h1>

            {depot && (
              <div className="mt-3 p-4 bg-slate-50 border-2 border-slate-300 rounded-xl">
                <div className="flex flex-wrap items-center gap-2 text-lg">
                  <span className="inline-flex items-center gap-1.5 font-extrabold text-slate-700">
                    <MapPin className="w-5 h-5 text-slate-900 shrink-0" />
                    Starting Location:
                  </span>
                  <span className="font-extrabold text-slate-950">
                    {depot.name} (Loc #{depot.gcpsId})
                  </span>
                </div>

                <div className="no-print mt-3 flex flex-col lg:flex-row gap-3 lg:items-center">
                  <div className="relative flex-1 max-w-md">
                    <Search className="w-5 h-5 text-slate-500 absolute left-3.5 top-3" />
                    <input
                      type="text"
                      value={depotSearch}
                      onFocus={() => setDepotDropdownOpen(true)}
                      onBlur={() => setTimeout(() => setDepotDropdownOpen(false), 180)}
                      onChange={(e) => {
                        setDepotSearch(e.target.value);
                        setDepotDropdownOpen(true);
                      }}
                      placeholder="Type school name or Loc # to change start..."
                      className="w-full h-11 pl-11 pr-4 text-base font-medium bg-white border-2 border-slate-400 rounded-xl focus:outline-none focus:border-blue-700"
                    />

                    {depotDropdownOpen && (
                      <div className="absolute z-50 left-0 right-0 mt-1.5 max-h-64 overflow-y-auto bg-white border-2 border-slate-400 rounded-xl shadow-lg divide-y divide-slate-200">
                        {matchingDepots.length > 0 ? (
                          matchingDepots.slice(0, 25).map((loc) => (
                            <button
                              key={`depot-opt-${loc.id}`}
                              type="button"
                              onMouseDown={() => handleSelectDepot(loc)}
                              className="w-full text-left px-4 py-2.5 hover:bg-blue-50 flex items-center justify-between gap-3 cursor-pointer"
                            >
                              <span className="font-bold text-slate-900 text-base truncate">
                                {loc.name}
                              </span>
                              <span className="text-sm font-semibold text-slate-600 shrink-0">
                                #{loc.gcpsId} • {loc.cluster}
                              </span>
                            </button>
                          ))
                        ) : (
                          <div className="px-4 py-3 text-base text-slate-600">
                            No matching starting location.
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {supportFacilities.length > 0 && (
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-bold text-slate-600">Quick Hubs:</span>
                      {supportFacilities.map((sf) => (
                        <button
                          key={`hub-${sf.id}`}
                          type="button"
                          onClick={() => handleSelectDepot(sf)}
                          className={`h-10 px-3.5 rounded-xl text-sm font-bold border-2 inline-flex items-center justify-center cursor-pointer ${
                            depot.id === sf.id
                              ? 'bg-slate-900 text-white border-slate-950'
                              : 'bg-white hover:bg-slate-200 text-slate-800 border-slate-400'
                          }`}
                        >
                          #{sf.gcpsId} {sf.name.split(' ')[0]}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {selectedStops.length > 0 && (
            <button
              onClick={handleReset}
              className="no-print h-12 px-5 shrink-0 inline-flex items-center justify-center gap-2 text-lg font-bold text-slate-800 bg-slate-200 hover:bg-slate-300 rounded-xl border-2 border-slate-400 cursor-pointer"
            >
              <RotateCcw className="w-5 h-5 shrink-0" />
              Start Over
            </button>
          )}
        </div>
      </header>

      {errorMessage && (
        <div className="max-w-7xl mx-auto mb-6 p-5 bg-red-100 border-2 border-red-600 rounded-2xl text-red-950 text-lg font-bold">
          {errorMessage}
        </div>
      )}

      <main className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* STEP 1: SCROLLABLE SCHOOL WIDGET */}
        <section className="no-print lg:col-span-5 bg-white border-2 border-slate-300 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between gap-2 mb-3">
            <div className="flex items-center gap-3">
              <span className="bg-blue-700 text-white text-lg font-extrabold px-3.5 py-1 rounded-lg">
                STEP 1
              </span>
              <h2 className="text-2xl font-extrabold">Pick Schools</h2>
            </div>
            <span className="text-base font-bold text-slate-600 bg-slate-100 px-3 py-1 rounded-lg border border-slate-300">
              {filteredLocations.length} found
            </span>
          </div>

          <div className="relative mb-3">
            <Search className="w-5 h-5 text-slate-500 absolute left-3.5 top-3.5" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search school name or Loc #..."
              className="w-full h-12 pl-11 pr-4 text-lg border-2 border-slate-400 rounded-xl focus:outline-none focus:border-blue-700"
            />
          </div>

          <div className="mb-3">
            <select
              value={clusterFilter}
              onChange={(e) => setClusterFilter(e.target.value)}
              className="w-full h-12 px-3.5 text-lg font-semibold bg-slate-50 border-2 border-slate-400 rounded-xl"
            >
              {clusters.map((c) => (
                <option key={c} value={c}>
                  {c === 'ALL' ? `All Clusters (${locations.length} Locations)` : `Cluster: ${c}`}
                </option>
              ))}
            </select>
          </div>

          <div
            style={{ height: '380px' }}
            className="overflow-y-auto border-2 border-slate-300 rounded-xl bg-slate-100 p-2.5 space-y-2.5"
          >
            {filteredLocations.map((loc) => {
              const isStart = depot && depot.id === loc.id;
              const alreadyAdded = selectedStops.some((s) => s.id === loc.id);
              const disabled = isStart || alreadyAdded;

              return (
                <div
                  key={loc.id}
                  className="p-3.5 border-2 border-slate-300 rounded-xl flex items-center justify-between gap-3 bg-white"
                >
                  {/* Flexible text column so right buttons stay identical across all rows */}
                  <div className="min-w-0 flex-1">
                    <div className="text-base font-bold text-slate-900 leading-snug">
                      {loc.name}
                    </div>
                    <div className="text-sm font-medium text-slate-700 flex items-center gap-1.5 mt-1">
                      <Building2 className="w-4 h-4 shrink-0" />
                      <span className="truncate">
                        Loc #{loc.gcpsId} • {loc.cluster} ({loc.type})
                      </span>
                    </div>
                  </div>

                  {/* Fixed-scale action buttons */}
                  <div className="flex items-center gap-2 shrink-0">
                    {!isStart && (
                      <button
                        type="button"
                        onClick={() => handleSelectDepot(loc)}
                        className="h-10 px-3 rounded-xl text-sm font-bold bg-slate-100 hover:bg-slate-200 text-slate-800 border-2 border-slate-300 inline-flex items-center justify-center whitespace-nowrap cursor-pointer"
                      >
                        Set Start
                      </button>
                    )}

                    <button
                      disabled={disabled}
                      onClick={() => handleAddStop(loc)}
                      className={`h-10 w-24 rounded-xl text-sm font-bold inline-flex items-center justify-center gap-1 border-2 whitespace-nowrap ${
                        isStart
                          ? 'bg-slate-800 text-white border-slate-900 cursor-not-allowed'
                          : alreadyAdded
                          ? 'bg-slate-200 text-slate-500 border-slate-300 cursor-not-allowed'
                          : 'bg-blue-700 hover:bg-blue-800 text-white border-blue-900 cursor-pointer'
                      }`}
                    >
                      {!disabled && <Plus className="w-4 h-4 shrink-0" />}
                      {isStart ? 'Start' : alreadyAdded ? 'Added' : 'Add'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* STEP 2: REAL DRIVING ROUTE & INTERACTIVE MAP */}
        <section className="lg:col-span-7 space-y-6">
          <div className="bg-white border-2 border-slate-300 rounded-2xl p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
              <div className="flex items-center gap-3">
                <span className="bg-green-700 text-white text-lg font-extrabold px-3.5 py-1 rounded-lg">
                  STEP 2
                </span>
                <h2 className="text-2xl font-extrabold">Your Driving Route</h2>
              </div>

              {selectedStops.length > 0 && (
                <div className="text-lg font-extrabold bg-slate-100 px-4 py-2 rounded-xl border-2 border-slate-300">
                  {loadingRoute
                    ? 'Calculating roads...'
                    : `${routeStats.total_miles} mi • ~${routeStats.total_minutes} min`}
                </div>
              )}
            </div>

            {selectedStops.length >= 2 && (
              <button
                onClick={handleOptimize}
                disabled={loadingRoute}
                className="no-print w-full mb-4 h-14 px-6 bg-green-700 hover:bg-green-800 disabled:opacity-60 text-white text-xl font-extrabold rounded-xl border-2 border-green-950 flex items-center justify-center gap-3 shadow-sm cursor-pointer"
              >
                <Zap className="w-7 h-7 shrink-0" />
                {loadingRoute ? 'CALCULATING REAL ROADS...' : 'FIND SHORTEST DRIVING ROUTE'}
              </button>
            )}

            {isOptimized && (
              <div className="mb-4 p-4 bg-green-100 border-2 border-green-700 rounded-xl text-green-950 text-lg font-bold">
                Route Updated! Stops are in the shortest driving order
                {savedMiles > 0 ? ` (Saves ${savedMiles} driving miles)` : ''}.
              </div>
            )}

            {selectedStops.length === 0 ? (
              <div className="text-center py-10 px-4 border-2 border-dashed border-slate-300 rounded-xl bg-slate-50">
                <p className="text-xl font-bold text-slate-700">No stops added yet.</p>
                <p className="text-lg text-slate-600 mt-1">
                  Search on the left and press <strong>"+ Add"</strong> to build your route.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {selectedStops.map((stop, index) => {
                  const leg = routeStats.legs[index];
                  const isDone = !!completedIds[stop.id];

                  return (
                    <div
                      key={stop.id}
                      className={`p-4 border-2 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
                        isDone
                          ? 'bg-slate-100 border-slate-300 opacity-75'
                          : 'bg-white border-slate-400'
                      }`}
                    >
                      {/* Left column: Checkbox, Number badge, and flexible text block */}
                      <div className="flex items-center gap-3.5 min-w-0 flex-1">
                        <button
                          onClick={() => toggleCheck(stop.id)}
                          className="shrink-0 text-slate-800 hover:text-green-700 cursor-pointer"
                        >
                          {isDone ? (
                            <CheckSquare className="w-8 h-8 text-green-700" />
                          ) : (
                            <Square className="w-8 h-8" />
                          )}
                        </button>

                        <div className="w-10 h-10 rounded-full bg-slate-900 text-white text-lg font-extrabold flex items-center justify-center shrink-0">
                          {index + 1}
                        </div>

                        <div className="min-w-0 flex-1">
                          <div
                            className={`text-lg font-extrabold leading-snug ${
                              isDone ? 'line-through text-slate-500' : 'text-slate-900'
                            }`}
                          >
                            {stop.name}
                          </div>
                          <div className="text-sm text-slate-700 mt-0.5">
                            Loc #{stop.gcpsId} • {stop.cluster}
                            {leg && (
                              <>
                                {' '}
                                •{' '}
                                <strong>
                                  {leg.miles} mi (~{leg.minutes} min)
                                </strong>
                              </>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Right column: Fixed-scale Up, Down, and Remove buttons */}
                      <div className="no-print flex items-center gap-2 shrink-0 self-end sm:self-center">
                        <button
                          type="button"
                          onClick={() => handleMoveStop(index, -1)}
                          disabled={index === 0}
                          title="Move Stop Up"
                          className="w-11 h-11 bg-slate-200 hover:bg-slate-300 disabled:opacity-40 rounded-xl border-2 border-slate-400 inline-flex items-center justify-center shrink-0 cursor-pointer"
                        >
                          <ArrowUp className="w-5 h-5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleMoveStop(index, 1)}
                          disabled={index === selectedStops.length - 1}
                          title="Move Stop Down"
                          className="w-11 h-11 bg-slate-200 hover:bg-slate-300 disabled:opacity-40 rounded-xl border-2 border-slate-400 inline-flex items-center justify-center shrink-0 cursor-pointer"
                        >
                          <ArrowDown className="w-5 h-5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleRemoveStop(stop.id)}
                          className="h-11 px-4 bg-red-100 hover:bg-red-200 text-red-900 font-bold text-sm rounded-xl border-2 border-red-400 inline-flex items-center justify-center gap-1.5 shrink-0 whitespace-nowrap cursor-pointer"
                        >
                          <Trash2 className="w-4 h-4 shrink-0" />
                          Remove
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {selectedStops.length > 0 && (
              <button
                onClick={() => window.print()}
                className="no-print mt-5 w-full h-14 px-6 bg-slate-900 hover:bg-slate-800 text-white text-xl font-bold rounded-xl flex items-center justify-center gap-3 cursor-pointer"
              >
                <Printer className="w-6 h-6 shrink-0" />
                Print Paper Checklist
              </button>
            )}
          </div>

          {depot && (
            <div className="bg-white border-2 border-slate-300 rounded-2xl p-5 shadow-sm">
              <h3 className="text-xl font-extrabold mb-3">Interactive Gwinnett Road Map</h3>
              <StreetRouteMap
                depot={depot}
                stops={selectedStops}
                geometry={routeStats.geometry}
                isOptimized={isOptimized}
              />
            </div>
          )}
        </section>
      </main>
    </div>
  );
}