import { useEffect, useMemo, useRef, useState } from 'react';
import { CircleMarker, MapContainer, Marker, Polyline, Popup, TileLayer } from 'react-leaflet';
import { AlertTriangle, Clock3, Gauge, LoaderCircle, MapPin, Route, ShieldAlert, Wind, Zap } from 'lucide-react';
import { submitRoutePlan } from './api/client';
import LocationAutocomplete from './components/LocationAutocomplete';
import type { LocationSuggestion, RoutePlanResponse } from './types';

type FormState = {
  origin: string;
  destination: string;
  departure_datetime: string;
  load_weight_lbs: number;
  checkpoint_interval_miles: number;
  forecast_offset_hours: number;
};

const DEFAULT_FORM: FormState = {
  origin: '',
  destination: '',
  departure_datetime: '2026-10-28T08:00:00-05:00',
  load_weight_lbs: 35000,
  checkpoint_interval_miles: 25,
  forecast_offset_hours: 0,
};

const riskClasses = {
  low: 'bg-emerald-100 text-emerald-800',
  moderate: 'bg-amber-100 text-amber-800',
  high: 'bg-orange-100 text-orange-800',
  severe: 'bg-red-100 text-red-800',
  no_travel: 'bg-slate-900 text-white',
  unknown: 'bg-slate-200 text-slate-700',
};

function formatLabel(level: string) {
  return level.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function locationsMatch(first: LocationSuggestion | null, second: LocationSuggestion | null) {
  if (!first || !second) return false;
  if (first.id === second.id) return true;
  return Math.abs(first.lat - second.lat) < 0.0001
    && Math.abs(first.lon - second.lon) < 0.0001;
}

function App() {
  const [form, setForm] = useState(DEFAULT_FORM);
  const [originLocation, setOriginLocation] = useState<LocationSuggestion | null>(null);
  const [destinationLocation, setDestinationLocation] = useState<LocationSuggestion | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [result, setResult] = useState<RoutePlanResponse | null>(null);
  const [selectedRouteIndex, setSelectedRouteIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const requestSeq = useRef(0);
  const requestInFlight = useRef(false);
  const forecastRequestTimer = useRef<number | null>(null);

  const visibleRoute = result?.routes[selectedRouteIndex] ?? null;

  useEffect(() => () => {
    if (forecastRequestTimer.current !== null) {
      window.clearTimeout(forecastRequestTimer.current);
    }
  }, []);

  const mapCenter = useMemo(() => {
    if (!visibleRoute || visibleRoute.geometry.length === 0) {
      return [32.7767, -96.797] as [number, number];
    }
    const first = visibleRoute.geometry[0];
    return [first.lat, first.lon] as [number, number];
  }, [visibleRoute]);

  function updateField(field: string, value: string | number) {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: '' }));
  }

  function updateLocation(field: 'origin' | 'destination', value: string) {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: '' }));
    if (field === 'origin') setOriginLocation(null);
    else setDestinationLocation(null);
  }

  function selectLocation(field: 'origin' | 'destination', location: LocationSuggestion) {
    setForm((current) => ({ ...current, [field]: location.label }));
    setErrors((current) => ({ ...current, [field]: '' }));
    if (field === 'origin') setOriginLocation(location);
    else setDestinationLocation(location);
  }

  function validateForm(nextForm: typeof form) {
    const nextErrors: Record<string, string> = {};
    if (!nextForm.origin.trim()) nextErrors.origin = 'Origin is required.';
    else if (!originLocation || originLocation.label !== nextForm.origin) nextErrors.origin = 'Choose an origin from the location suggestions.';
    if (!nextForm.destination.trim()) nextErrors.destination = 'Destination is required.';
    else if (!destinationLocation || destinationLocation.label !== nextForm.destination) nextErrors.destination = 'Choose a destination from the location suggestions.';
    if (
      (originLocation && destinationLocation && locationsMatch(originLocation, destinationLocation))
      || (nextForm.origin.trim() && nextForm.origin.trim().toLowerCase() === nextForm.destination.trim().toLowerCase())
    ) {
      nextErrors.destination = 'Origin and destination cannot be the same.';
    }
    if (!Number.isFinite(Number(nextForm.load_weight_lbs)) || Number(nextForm.load_weight_lbs) <= 0) {
      nextErrors.load_weight_lbs = 'Load weight must be a positive number.';
    }
    if (Number(nextForm.load_weight_lbs) > 150000) {
      nextErrors.load_weight_lbs = 'Load weight exceeds the supported application limit.';
    }
    if (!Number.isInteger(Number(nextForm.forecast_offset_hours)) || Number(nextForm.forecast_offset_hours) < 0 || Number(nextForm.forecast_offset_hours) > 48) {
      nextErrors.forecast_offset_hours = 'Forecast offset must be an integer between 0 and 48.';
    }
    if (![10, 25, 50].includes(Number(nextForm.checkpoint_interval_miles))) {
      nextErrors.checkpoint_interval_miles = 'Checkpoint interval must be 10, 25, or 50 miles.';
    }
    if (!nextForm.departure_datetime) nextErrors.departure_datetime = 'Departure time is required.';
    return nextErrors;
  }

  async function runPlanner(nextForm: typeof form, fromSlider = false) {
    if (requestInFlight.current) return;
    const nextErrors = validateForm(nextForm);
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      setError('Please correct the highlighted fields and try again.');
      return;
    }

    const currentRequestId = ++requestSeq.current;
    requestInFlight.current = true;
    setLoading(true);
    setError('');
    setErrors({});

    try {
      const response = await submitRoutePlan({
        origin: nextForm.origin,
        destination: nextForm.destination,
        departure_datetime: nextForm.departure_datetime,
        load_weight_lbs: Number(nextForm.load_weight_lbs),
        checkpoint_interval_miles: Number(nextForm.checkpoint_interval_miles),
        forecast_offset_hours: Number(nextForm.forecast_offset_hours),
      });
      if (requestSeq.current !== currentRequestId) return;
      setResult(response);
      setSelectedRouteIndex(0);
      if (!fromSlider) {
        setError('');
      }
    } catch (submitError) {
      if (requestSeq.current !== currentRequestId) return;
      setError(submitError instanceof Error ? submitError.message : 'Unable to generate routes.');
    } finally {
      if (requestSeq.current === currentRequestId) {
        requestInFlight.current = false;
        setLoading(false);
      }
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (forecastRequestTimer.current !== null) {
      window.clearTimeout(forecastRequestTimer.current);
      forecastRequestTimer.current = null;
    }
    await runPlanner(form);
  }

  function handleForecastOffsetChange(value: number) {
    const nextForm = { ...form, forecast_offset_hours: value };
    setForm(nextForm);
    if (!result) return;
    if (forecastRequestTimer.current !== null) {
      window.clearTimeout(forecastRequestTimer.current);
    }
    forecastRequestTimer.current = window.setTimeout(() => {
      forecastRequestTimer.current = null;
      void runPlanner(nextForm, true);
    }, 300);
  }

  if (!result) {
    return (
      <div className="min-h-screen bg-slate-100 text-slate-900">
        <header className="border-b border-slate-200 bg-white/80 backdrop-blur-sm">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 text-sm font-semibold text-white">WA</div>
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Dispatch planning</p>
                <h1 className="text-lg font-semibold">Weather-Aware Truck Routing</h1>
              </div>
            </div>
          </div>
        </header>

        <main className="mx-auto grid max-w-7xl gap-8 px-4 py-10 sm:px-6 lg:grid-cols-[420px_minmax(0,1fr)] lg:px-8">
          <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="mb-6 flex items-start justify-between">
              <div>
                <p className="text-sm font-medium text-slate-500">Route planning</p>
                <h2 className="mt-1 text-2xl font-semibold">Plan a weather-safe trip</h2>
              </div>
              <Route className="h-7 w-7 text-slate-600" />
            </div>

            <form className="space-y-5" onSubmit={handleSubmit} noValidate aria-busy={loading}>
              <LocationAutocomplete
                label="Origin"
                value={form.origin}
                selectedLocation={originLocation}
                error={errors.origin}
                onChange={(value) => updateLocation('origin', value)}
                onSelect={(location) => selectLocation('origin', location)}
              />

              <LocationAutocomplete
                label="Destination"
                value={form.destination}
                selectedLocation={destinationLocation}
                error={errors.destination}
                onChange={(value) => updateLocation('destination', value)}
                onSelect={(location) => selectLocation('destination', location)}
              />

              <div className="grid gap-5 sm:grid-cols-2">
                <label className="block text-sm font-medium text-slate-700">
                  Departure
                  <input aria-label="Departure date and time" type="datetime-local" value={form.departure_datetime.slice(0, 16)} onChange={(event) => updateField('departure_datetime', `${event.target.value}:00-05:00`)} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 focus:border-slate-400 focus:outline-none" />
                  {errors.departure_datetime && <span className="mt-1 block text-xs text-red-600">{errors.departure_datetime}</span>}
                </label>

                <label className="block text-sm font-medium text-slate-700">
                  Load weight (lb)
                  <input aria-label="Load weight in pounds" type="number" min="1" value={form.load_weight_lbs} onChange={(event) => updateField('load_weight_lbs', Number(event.target.value))} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 focus:border-slate-400 focus:outline-none" />
                  {errors.load_weight_lbs && <span className="mt-1 block text-xs text-red-600">{errors.load_weight_lbs}</span>}
                </label>
              </div>

              <div className="grid gap-5 sm:grid-cols-2">
                <label className="block text-sm font-medium text-slate-700">
                  Checkpoint interval
                  <select aria-label="Checkpoint interval" value={form.checkpoint_interval_miles} onChange={(event) => updateField('checkpoint_interval_miles', Number(event.target.value))} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 focus:border-slate-400 focus:outline-none">
                    {[10, 25, 50].map((interval) => <option key={interval} value={interval}>{interval} miles</option>)}
                  </select>
                  {errors.checkpoint_interval_miles && <span className="mt-1 block text-xs text-red-600">{errors.checkpoint_interval_miles}</span>}
                </label>

                <label className="block text-sm font-medium text-slate-700">
                  Forecast offset
                  <div className="mt-2 flex items-center gap-2">
                    <input aria-label="Forecast offset hours" type="range" min="0" max="48" value={form.forecast_offset_hours} disabled={loading} onChange={(event) => handleForecastOffsetChange(Number(event.target.value))} className="w-full accent-slate-900 disabled:opacity-50" />
                    <span className="min-w-12 rounded-lg bg-slate-100 px-2 py-1 text-center text-sm font-medium">{form.forecast_offset_hours}h</span>
                  </div>
                  {errors.forecast_offset_hours && <span className="mt-1 block text-xs text-red-600">{errors.forecast_offset_hours}</span>}
                </label>
              </div>

              {error && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                  {error}
                </div>
              )}

              <button type="submit" disabled={loading} className="w-full rounded-xl bg-slate-900 px-4 py-3 font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400">
                {loading ? <span className="inline-flex items-center gap-2"><LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" />Generating routes...</span> : 'Generate routes'}
              </button>
              {loading && <p className="text-center text-sm text-slate-600" role="status">Generating routes and checking weather along the trip. This can take a moment.</p>}
            </form>
          </section>

          <section className="flex min-h-[500px] flex-col justify-center rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
            <div className="mb-6 flex items-center justify-between text-slate-600">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">System status</p>
                <h2 className="mt-1 text-xl font-semibold text-slate-900">Awaiting route plan</h2>
              </div>
              <ShieldAlert className="h-8 w-8 text-slate-400" />
            </div>
            <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-sm leading-6 text-slate-600">
              Enter a trip and generate a route to compare weather risk, ETA, and route alternatives. The app checks weather coverage and highlights road conditions that need dispatcher review.
            </div>
          </section>
        </main>
      </div>
    );
  }

  const selected = result.routes[selectedRouteIndex];
  const routeCoordinates = selected?.geometry ?? [];
  const routePoints: [number, number][] = routeCoordinates.map((coord) => [coord.lat, coord.lon] as [number, number]);
  const hasNoTravel = selected?.has_confirmed_no_travel ?? false;

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b border-slate-200 bg-white/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 text-sm font-semibold text-white">WA</div>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Dispatch planning</p>
              <h1 className="text-lg font-semibold">Weather-Aware Truck Routing</h1>
            </div>
          </div>
          <div className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-sm text-slate-600">
            {result.routes.length} route alternatives
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <div className="grid gap-6 xl:grid-cols-[420px_minmax(0,1fr)]">
          <aside className="space-y-6">
            <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="mb-5 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-500">Trip details</p>
                  <h2 className="text-2xl font-semibold">Compare routes</h2>
                </div>
                <Route className="h-7 w-7 text-slate-600" />
              </div>

              <form className="space-y-4" onSubmit={handleSubmit} noValidate aria-busy={loading}>
                <LocationAutocomplete
                  label="Origin"
                  value={form.origin}
                  selectedLocation={originLocation}
                  error={errors.origin}
                  onChange={(value) => updateLocation('origin', value)}
                  onSelect={(location) => selectLocation('origin', location)}
                />
                <LocationAutocomplete
                  label="Destination"
                  value={form.destination}
                  selectedLocation={destinationLocation}
                  error={errors.destination}
                  onChange={(value) => updateLocation('destination', value)}
                  onSelect={(location) => selectLocation('destination', location)}
                />
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="block text-sm font-medium text-slate-700">
                    Departure
                    <input aria-label="Departure date and time" type="datetime-local" value={form.departure_datetime.slice(0, 16)} onChange={(event) => updateField('departure_datetime', `${event.target.value}:00-05:00`)} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 focus:border-slate-400 focus:outline-none" />
                  </label>
                  <label className="block text-sm font-medium text-slate-700">
                    Weight (lb)
                    <input aria-label="Load weight in pounds" type="number" min="1" value={form.load_weight_lbs} onChange={(event) => updateField('load_weight_lbs', Number(event.target.value))} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 focus:border-slate-400 focus:outline-none" />
                  </label>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="block text-sm font-medium text-slate-700">
                    Interval
                    <select value={form.checkpoint_interval_miles} onChange={(event) => updateField('checkpoint_interval_miles', Number(event.target.value))} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 focus:border-slate-400 focus:outline-none">
                      {[10, 25, 50].map((interval) => <option key={interval} value={interval}>{interval} miles</option>)}
                    </select>
                  </label>
                  <label className="block text-sm font-medium text-slate-700">
                    Forecast offset
                    <div className="mt-2 flex items-center gap-2">
                      <input aria-label="Forecast offset" type="range" min="0" max="48" value={form.forecast_offset_hours} disabled={loading} onChange={(event) => handleForecastOffsetChange(Number(event.target.value))} className="w-full accent-slate-900 disabled:opacity-50" />
                      <span className="min-w-11 rounded-lg bg-slate-100 px-2 py-1 text-center text-sm font-medium">{form.forecast_offset_hours}h</span>
                    </div>
                  </label>
                </div>

                {error && (
                  <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                    {error}
                  </div>
                )}

                <button type="submit" disabled={loading} className="w-full rounded-xl bg-slate-900 px-4 py-3 font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400">
                  {loading ? <span className="inline-flex items-center gap-2"><LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" />Generating routes...</span> : 'Generate routes'}
                </button>
                {loading && <p className="text-center text-sm text-slate-600" role="status">Generating routes and checking weather along the trip. Previous results remain visible.</p>}
              </form>
            </section>

            <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-lg font-semibold">Route comparison</h3>
                <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Ranking</div>
              </div>
              <div className="space-y-3">
                {result.routes.map((route, index) => (
                  <button key={route.name} type="button" onClick={() => setSelectedRouteIndex(index)} className={`w-full rounded-2xl border p-4 text-left transition ${index === selectedRouteIndex ? 'border-slate-900 bg-slate-50 shadow-sm' : 'border-slate-200 bg-white hover:border-slate-300'}`}>
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium text-slate-500">{route.name}</p>
                        <p className="text-lg font-semibold text-slate-900">{route.distance_miles.toFixed(0)} mi</p>
                      </div>
                      <span className={`rounded-full px-2 py-1 text-xs font-medium ${route.recommended ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-700'}`}>
                        {route.recommended ? 'Recommended' : `Rank ${route.rank ?? index + 1}`}
                      </span>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600">
                      <div className="rounded-xl bg-slate-50 px-2 py-2"><span className="block text-slate-500">ETA</span>{new Date(route.eta).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</div>
                      <div className="rounded-xl bg-slate-50 px-2 py-2"><span className="block text-slate-500">Risk</span>{route.weather_coverage_percent.toFixed(0)}% coverage</div>
                      <div className="rounded-xl bg-slate-50 px-2 py-2"><span className="block text-slate-500">Severe</span>{route.severe_miles.toFixed(1)} mi</div>
                      <div className="rounded-xl bg-slate-50 px-2 py-2"><span className="block text-slate-500">High</span>{route.high_miles.toFixed(1)} mi</div>
                    </div>
                  </button>
                ))}
              </div>
            </section>
          </aside>

          <section className="space-y-6">
            <div className="rounded-3xl border border-slate-200 bg-white p-3 shadow-sm">
              <div className="mb-3 flex items-center justify-between gap-3 px-3 pt-2">
                <div>
                  <p className="text-sm font-medium text-slate-500">Map view</p>
                  <h2 className="text-xl font-semibold">{selected?.name ?? 'Route overview'}</h2>
                </div>
                {hasNoTravel && <div className="rounded-full bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700">No travel warning</div>}
              </div>
              <div className="overflow-hidden rounded-2xl border border-slate-200">
                <MapContainer center={mapCenter} zoom={6} style={{ height: '480px', width: '100%' }} scrollWheelZoom>
                  <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap contributors" />
                  {routeCoordinates.length > 0 && (
                    <Polyline positions={routePoints} pathOptions={{ color: selected?.recommended ? '#0f172a' : '#475569', weight: 5 }} />
                  )}
                  {selected?.checkpoints?.map((checkpoint, index) => (
                    <CircleMarker key={`${checkpoint.lat}-${checkpoint.lon}-${index}`} center={[checkpoint.lat, checkpoint.lon]} radius={7} pathOptions={{ color: 'white', weight: 2, fillColor: checkpoint.risk === 'unknown' ? '#94a3b8' : checkpoint.risk === 'low' ? '#10b981' : checkpoint.risk === 'moderate' ? '#f59e0b' : checkpoint.risk === 'high' ? '#f97316' : checkpoint.risk === 'severe' ? '#ef4444' : '#0f172a', fillOpacity: 1 }}>
                      <Popup>
                        <div className="space-y-2 text-sm">
                          <div className="flex items-center justify-between gap-4">
                            <strong>{formatLabel(checkpoint.risk || 'unknown')}</strong>
                            <span className={`rounded-full px-2 py-1 text-[10px] font-medium ${riskClasses[checkpoint.risk || 'unknown']}`}>{formatLabel(checkpoint.risk || 'unknown')}</span>
                          </div>
                          <div>Distance: {checkpoint.distance_miles.toFixed(1)} mi</div>
                          <div>ETA: {new Date(checkpoint.eta).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</div>
                          <div>Wind: {checkpoint.forecast?.wind_mph != null ? `${Number(checkpoint.forecast.wind_mph).toFixed(1)} mph` : 'Unavailable'}</div>
                          <div>Rain: {checkpoint.forecast?.rain_in_hr != null ? `${Number(checkpoint.forecast.rain_in_hr).toFixed(2)} in/hr` : 'Unavailable'}</div>
                          <div>Snow: {checkpoint.forecast?.snow_in_hr != null ? `${Number(checkpoint.forecast.snow_in_hr).toFixed(2)} in/hr` : 'Unavailable'}</div>
                        </div>
                      </Popup>
                    </CircleMarker>
                  ))}
                  <Marker position={[result.origin.lat, result.origin.lon]}>
                    <Popup>Origin: {result.origin.name}</Popup>
                  </Marker>
                  <Marker position={[result.destination.lat, result.destination.lon]}>
                    <Popup>Destination: {result.destination.name}</Popup>
                  </Marker>
                </MapContainer>
              </div>
            </div>

            <div className="grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
              <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="mb-5 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-slate-500">Route overview</p>
                    <h3 className="text-xl font-semibold">{selected?.name}</h3>
                  </div>
                  <div className={`rounded-full px-2.5 py-1 text-xs font-medium ${riskClasses[selected?.checkpoints?.[0]?.risk || 'unknown']}`}>{selected?.checkpoints?.[0] ? formatLabel(selected.checkpoints[0].risk) : 'Unknown'}</div>
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  <StatCard icon={<Route className="h-5 w-5" />} label="Distance" value={`${selected?.distance_miles.toFixed(1) ?? '0.0'} mi`} />
                  <StatCard icon={<Clock3 className="h-5 w-5" />} label="Travel time" value={`${selected?.duration_minutes.toFixed(0) ?? '0'} min`} />
                  <StatCard icon={<Gauge className="h-5 w-5" />} label="Coverage" value={`${selected?.weather_coverage_percent.toFixed(0) ?? '0'}%`} />
                </div>

                <div className="mt-6 space-y-3">
                  <div className="flex items-center gap-2 text-sm text-slate-600"><MapPin className="h-4 w-4" /> {result.origin.name} to {result.destination.name}</div>
                  <div className="flex items-center gap-2 text-sm text-slate-600"><Wind className="h-4 w-4" /> Forecast offset: {form.forecast_offset_hours}h</div>
                  <div className="flex items-center gap-2 text-sm text-slate-600"><Zap className="h-4 w-4" /> Load weight: {form.load_weight_lbs.toLocaleString()} lb</div>
                </div>
              </section>

              <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="text-lg font-semibold">Weather legend</h3>
                  <AlertTriangle className="h-5 w-5 text-slate-500" />
                </div>
                <div className="space-y-2">
                  {Object.entries(riskClasses).map(([level, classes]) => (
                    <div key={level} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2">
                      <span className={`rounded-full px-2 py-1 text-xs font-medium ${classes}`}>{formatLabel(level)}</span>
                      <span className="text-xs text-slate-500">{level === 'no_travel' ? 'Do not dispatch' : level === 'unknown' ? 'Coverage missing' : 'Weather risk'} </span>
                    </div>
                  ))}
                </div>
              </section>
            </div>

            <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-500">Checkpoint detail</p>
                  <h3 className="text-xl font-semibold">Weather and ETA timeline</h3>
                </div>
              </div>
              <div className="max-h-[420px] overflow-auto">
                <div className="grid gap-3">
                  {selected?.checkpoints?.map((checkpoint, index) => (
                    <div key={`${checkpoint.lat}-${checkpoint.lon}-${index}`} className="flex flex-col gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-4 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className={`rounded-full px-2 py-1 text-[10px] font-medium ${riskClasses[checkpoint.risk || 'unknown']}`}>{formatLabel(checkpoint.risk || 'unknown')}</span>
                          <span className="text-sm font-medium">Checkpoint {index + 1}</span>
                        </div>
                        <div className="mt-2 text-sm text-slate-600">Distance {checkpoint.distance_miles.toFixed(1)} mi • ETA {new Date(checkpoint.eta).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</div>
                      </div>
                      <div className="grid gap-1 text-xs text-slate-600 sm:text-right">
                        <span>Wind: {checkpoint.forecast?.wind_mph != null ? `${checkpoint.forecast.wind_mph.toFixed(1)} mph` : 'n/a'}</span>
                        <span>Rain: {checkpoint.forecast?.rain_in_hr != null ? `${checkpoint.forecast.rain_in_hr.toFixed(2)} in/hr` : 'n/a'}</span>
                        <span>Snow: {checkpoint.forecast?.snow_in_hr != null ? `${checkpoint.forecast.snow_in_hr.toFixed(2)} in/hr` : 'n/a'}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </section>
          </section>
        </div>
      </main>
    </div>
  );
}

type StatCardProps = {
  icon: React.ReactNode;
  label: string;
  value: string;
};

function StatCard({ icon, label, value }: StatCardProps) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-xl bg-white text-slate-700 shadow-sm">{icon}</div>
      <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{label}</div>
      <div className="mt-2 text-lg font-semibold text-slate-900">{value}</div>
    </div>
  );
}

export default App;
