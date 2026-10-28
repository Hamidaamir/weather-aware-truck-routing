import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { searchLocations, submitRoutePlan } from './api/client';
import type { LocationSuggestion, RoutePlanResponse, RouteSummary } from './types';

const { fitBoundsCalls, mockMap } = vi.hoisted(() => {
  const calls: Array<{
    southWest: { lat: number; lng: number };
    northEast: { lat: number; lng: number };
    options: { padding: [number, number]; maxZoom: number };
  }> = [];
  return {
    fitBoundsCalls: calls,
    mockMap: {
      fitBounds: (
        bounds: {
          getSouthWest: () => { lat: number; lng: number };
          getNorthEast: () => { lat: number; lng: number };
        },
        options: { padding: [number, number]; maxZoom: number },
      ) => calls.push({
        southWest: bounds.getSouthWest(),
        northEast: bounds.getNorthEast(),
        options,
      }),
    },
  };
});

vi.mock('./api/client', () => ({
  searchLocations: vi.fn(),
  submitRoutePlan: vi.fn(),
}));

vi.mock('react-leaflet', () => ({
  useMap: () => mockMap,
  MapContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => null,
  Polyline: () => null,
  CircleMarker: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Marker: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Popup: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
const dallas: LocationSuggestion = {
  id: 'place.dallas',
  primary: 'Dallas',
  secondary: 'Texas, United States',
  label: 'Dallas, Texas, United States',
  lat: 32.7767,
  lon: -96.797,
};

const elPaso: LocationSuggestion = {
  id: 'place.el-paso',
  primary: 'El Paso',
  secondary: 'Texas, United States',
  label: 'El Paso, Texas, United States',
  lat: 31.7619,
  lon: -106.485,
};

afterEach(() => {
  vi.resetAllMocks();
  fitBoundsCalls.length = 0;
});

function makeRoute(name: string, geometry: RouteSummary['geometry']): RouteSummary {
  return {
    name,
    distance_miles: 320,
    duration_minutes: 420,
    eta: '2026-10-28T16:30:00-05:00',
    severe_miles: 0,
    high_miles: 0,
    no_travel_checkpoints: 0,
    average_risk_score: 1,
    weather_coverage_percent: 100,
    has_confirmed_no_travel: false,
    recommended: name === 'Alternative 1',
    rank: name === 'Alternative 1' ? 1 : 2,
    checkpoints: [],
    geometry,
  };
}

function makePlan(routes: RouteSummary[]): RoutePlanResponse {
  return {
    origin: { name: 'Origin', lat: 32.7767, lon: -96.797 },
    destination: { name: 'Destination', lat: 31.7619, lon: -106.485 },
    routes,
    warnings: [],
    metadata: {},
  };
}

async function renderWithSelectedLocations() {
  vi.mocked(searchLocations).mockImplementation(async (query) => query.toLowerCase().includes('el') ? [elPaso] : [dallas]);
  render(<App />);
  const origin = screen.getByRole('combobox', { name: 'Origin' });
  const destination = screen.getByRole('combobox', { name: 'Destination' });
  fireEvent.change(origin, { target: { value: 'Dallas' } });
  fireEvent.click(await screen.findByRole('option', { name: /Dallas.*Texas, United States/i }));
  fireEvent.change(destination, { target: { value: 'El Paso' } });
  fireEvent.click(await screen.findByRole('option', { name: /El Paso.*Texas, United States/i }));
}

describe('App', () => {
  it('validates required form fields', async () => {
    render(<App />);
    fireEvent.change(screen.getByLabelText(/origin/i), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText(/destination/i), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /generate routes/i }));
    expect(screen.getByText(/origin is required/i)).toBeInTheDocument();
  });

  it('renders route alternatives when the API responds', async () => {
    vi.mocked(searchLocations).mockImplementation(async (query) => query.toLowerCase().includes('el') ? [elPaso] : [dallas]);
    vi.mocked(submitRoutePlan).mockResolvedValue({
      origin: { name: 'Dallas, TX', lat: 32.7767, lon: -96.797 },
      destination: { name: 'El Paso, TX', lat: 31.7619, lon: -106.485 },
      warnings: [],
      metadata: {},
      routes: [
        {
          name: 'Alternative 1',
          distance_miles: 320,
          duration_minutes: 420,
          eta: '2026-10-28T16:30:00-05:00',
          severe_miles: 0,
          high_miles: 3,
          no_travel_checkpoints: 0,
          average_risk_score: 1.2,
          weather_coverage_percent: 100,
          has_confirmed_no_travel: false,
          recommended: true,
          rank: 1,
          geometry: [
            { lat: 32.7767, lon: -96.797 },
            { lat: 32.8, lon: -97.1 },
            { lat: 31.7619, lon: -106.485 },
          ],
          checkpoints: [
            {
              distance_meters: 0,
              distance_miles: 0,
              lat: 32.7767,
              lon: -96.797,
              eta: '2026-10-28T08:00:00-05:00',
              risk: 'low',
              wind_risk: 'low',
              rain_risk: 'low',
              snow_risk: 'low',
              forecast: { missing: false, wind_mph: 12, rain_in_hr: 0.04, snow_in_hr: 0 },
            },
          ],
        },
      ],
    });

    render(<App />);
    const origin = screen.getByRole('combobox', { name: 'Origin' });
    const destination = screen.getByRole('combobox', { name: 'Destination' });
    fireEvent.change(origin, { target: { value: 'Dallas' } });
    fireEvent.click(await screen.findByRole('option', { name: /Dallas.*Texas, United States/i }));
    fireEvent.change(destination, { target: { value: 'El Paso' } });
    fireEvent.click(await screen.findByRole('option', { name: /El Paso.*Texas, United States/i }));
    fireEvent.change(screen.getByLabelText(/departure date and time/i), { target: { value: '2026-10-28T08:00' } });
    fireEvent.change(screen.getByLabelText(/load weight in pounds/i), { target: { value: '35000' } });
    fireEvent.click(screen.getByRole('button', { name: /generate routes/i }));

    await waitFor(() => expect(submitRoutePlan).toHaveBeenCalled());
    expect(vi.mocked(submitRoutePlan).mock.calls[0][0]).toMatchObject({
      origin: dallas.label,
      destination: elPaso.label,
    });
    expect(screen.getAllByText(/alternative 1/i).length).toBeGreaterThan(0);

    vi.mocked(submitRoutePlan).mockRejectedValueOnce(new Error('Temporary route service failure.'));
    fireEvent.click(screen.getByRole('button', { name: /generate routes/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/temporary route service failure/i);
    expect(screen.getAllByText(/alternative 1/i).length).toBeGreaterThan(0);
  });

  it('fits generated and selected routes, including new geometry with the same number of points', async () => {
    const firstRoute = makeRoute('Alternative 1', [
      { lat: 10, lon: 20 },
      { lat: 11, lon: 21 },
      { lat: 12, lon: 22 },
    ]);
    const secondRoute = makeRoute('Alternative 1', [
      { lat: 30, lon: -100 },
      { lat: 31, lon: -99 },
      { lat: 32, lon: -98 },
    ]);
    const alternateRoute = makeRoute('Alternative 2', [
      { lat: 40, lon: -80 },
      { lat: 41, lon: -79 },
      { lat: 42, lon: -78 },
    ]);
    vi.mocked(submitRoutePlan)
      .mockResolvedValueOnce(makePlan([firstRoute]))
      .mockResolvedValueOnce(makePlan([secondRoute, alternateRoute]));

    await renderWithSelectedLocations();
    fireEvent.click(screen.getByRole('button', { name: /generate routes/i }));

    await waitFor(() => expect(fitBoundsCalls).toHaveLength(1));
    expect(fitBoundsCalls[0]).toEqual({
      southWest: { lat: 10, lng: 20 },
      northEast: { lat: 12, lng: 22 },
      options: { padding: [32, 32], maxZoom: 8 },
    });

    fireEvent.click(screen.getByRole('button', { name: /generate routes/i }));
    await waitFor(() => expect(fitBoundsCalls).toHaveLength(2));
    expect(fitBoundsCalls[1].southWest).toEqual({ lat: 30, lng: -100 });
    expect(fitBoundsCalls[1].northEast).toEqual({ lat: 32, lng: -98 });

    fireEvent.click(screen.getByRole('button', { name: /Alternative 2/ }));
    await waitFor(() => expect(fitBoundsCalls).toHaveLength(3));
    expect(fitBoundsCalls[2].southWest).toEqual({ lat: 40, lng: -80 });
    expect(fitBoundsCalls[2].northEast).toEqual({ lat: 42, lng: -78 });
  });

  it('skips viewport fitting safely for missing, empty, and invalid route geometry', async () => {
    const missingGeometry = makeRoute('Alternative 1', []);
    Reflect.deleteProperty(missingGeometry, 'geometry');
    const emptyGeometry = makeRoute('Alternative 1', []);
    const invalidGeometry = makeRoute('Alternative 1', [
      { lat: 91, lon: 20 },
      { lat: 30, lon: 181 },
    ]);
    vi.mocked(submitRoutePlan)
      .mockResolvedValueOnce(makePlan([missingGeometry]))
      .mockResolvedValueOnce(makePlan([emptyGeometry]))
      .mockResolvedValueOnce(makePlan([invalidGeometry]));

    await renderWithSelectedLocations();

    fireEvent.click(screen.getByRole('button', { name: /generate routes/i }));
    await waitFor(() => expect(submitRoutePlan).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole('button', { name: /generate routes/i })).toBeEnabled());
    expect(screen.getByTestId('map')).toBeInTheDocument();
    expect(fitBoundsCalls).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: /generate routes/i }));
    await waitFor(() => expect(submitRoutePlan).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByRole('button', { name: /generate routes/i })).toBeEnabled());
    expect(fitBoundsCalls).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: /generate routes/i }));
    await waitFor(() => expect(submitRoutePlan).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(screen.getByRole('button', { name: /generate routes/i })).toBeEnabled());
    expect(screen.getByTestId('map')).toBeInTheDocument();
    expect(fitBoundsCalls).toHaveLength(0);
  });

  it('requires a new suggestion after the selected location text is edited', async () => {
    vi.mocked(searchLocations).mockResolvedValue([dallas]);
    render(<App />);
    const origin = screen.getByRole('combobox', { name: 'Origin' });
    fireEvent.change(origin, { target: { value: 'Dallas' } });
    fireEvent.click(await screen.findByRole('option', { name: /Dallas/i }));
    fireEvent.change(origin, { target: { value: 'Dallas edited' } });
    fireEvent.click(screen.getByRole('button', { name: /generate routes/i }));

    expect(await screen.findByText(/choose an origin from the location suggestions/i)).toBeInTheDocument();
    expect(submitRoutePlan).not.toHaveBeenCalled();
  });

  it('prevents submitting identical selected origin and destination locations', async () => {
    vi.mocked(searchLocations).mockResolvedValue([dallas]);
    render(<App />);
    const origin = screen.getByRole('combobox', { name: 'Origin' });
    const destination = screen.getByRole('combobox', { name: 'Destination' });
    fireEvent.change(origin, { target: { value: 'Dallas' } });
    fireEvent.click(await screen.findByRole('option', { name: /Dallas/i }));
    fireEvent.change(destination, { target: { value: 'Dallas' } });
    fireEvent.click(await screen.findByRole('option', { name: /Dallas/i }));
    fireEvent.click(screen.getByRole('button', { name: /generate routes/i }));

    expect(await screen.findByText(/origin and destination cannot be the same/i)).toBeInTheDocument();
    expect(submitRoutePlan).not.toHaveBeenCalled();
  });

  it('disables duplicate submissions and announces route planning while the request is active', async () => {
    let resolvePlan: ((value: {
      origin: { name: string; lat: number; lon: number };
      destination: { name: string; lat: number; lon: number };
      routes: [];
      warnings: string[];
      metadata: Record<string, unknown>;
    }) => void) | undefined;
    vi.mocked(searchLocations).mockImplementation(async (query) => query.toLowerCase().includes('el') ? [elPaso] : [dallas]);
    vi.mocked(submitRoutePlan).mockImplementation(() => new Promise((resolve) => {
      resolvePlan = resolve;
    }));

    render(<App />);
    const origin = screen.getByRole('combobox', { name: 'Origin' });
    const destination = screen.getByRole('combobox', { name: 'Destination' });
    fireEvent.change(origin, { target: { value: 'Dallas' } });
    fireEvent.click(await screen.findByRole('option', { name: /Dallas.*Texas, United States/i }));
    fireEvent.change(destination, { target: { value: 'El Paso' } });
    fireEvent.click(await screen.findByRole('option', { name: /El Paso.*Texas, United States/i }));

    const form = screen.getByRole('button', { name: /generate routes/i }).closest('form');
    expect(form).not.toBeNull();
    fireEvent.submit(form!);
    await waitFor(() => expect(submitRoutePlan).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('status')).toHaveTextContent(/generating routes and checking weather/i);
    expect(screen.getByRole('button', { name: /generating routes/i })).toBeDisabled();

    fireEvent.submit(form!);
    expect(submitRoutePlan).toHaveBeenCalledTimes(1);

    await act(async () => resolvePlan?.({
      origin: { name: 'Dallas', lat: dallas.lat, lon: dallas.lon },
      destination: { name: 'El Paso', lat: elPaso.lat, lon: elPaso.lon },
      routes: [],
      warnings: [],
      metadata: {},
    }));
  });
});
