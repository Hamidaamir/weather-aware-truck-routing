import { act, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import LocationAutocomplete from './LocationAutocomplete';
import { searchLocations } from '../api/client';
import type { LocationSuggestion } from '../types';

vi.mock('../api/client', () => ({
  searchLocations: vi.fn(),
}));

const dallas: LocationSuggestion = {
  id: 'place.123',
  primary: 'Dallas',
  secondary: 'Texas, United States',
  label: 'Dallas, Texas, United States',
  lat: 32.7767,
  lon: -96.797,
};

const elPaso: LocationSuggestion = {
  id: 'place.456',
  primary: 'El Paso',
  secondary: 'Texas, United States',
  label: 'El Paso, Texas, United States',
  lat: 31.7619,
  lon: -106.485,
};

function Harness() {
  const [value, setValue] = useState('');
  const [selected, setSelected] = useState<LocationSuggestion | null>(null);
  return (
    <>
      <LocationAutocomplete
        label="Origin"
        value={value}
        selectedLocation={selected}
        onChange={(nextValue) => {
          setValue(nextValue);
          setSelected(null);
        }}
        onSelect={(location) => {
          setValue(location.label);
          setSelected(location);
        }}
      />
      <output data-testid="selected-location">{selected?.id ?? 'none'}</output>
    </>
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('LocationAutocomplete', () => {
  it('debounces location searches until the user pauses typing', async () => {
    vi.useFakeTimers();
    vi.mocked(searchLocations).mockResolvedValue([dallas]);
    render(<Harness />);
    fireEvent.change(screen.getByRole('combobox', { name: 'Origin' }), { target: { value: 'Dal' } });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(299);
    });
    expect(searchLocations).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(searchLocations).toHaveBeenCalledWith('Dal', expect.any(AbortSignal));
    expect(screen.getByRole('option', { name: /Dallas.*Texas, United States/i })).toBeInTheDocument();
  });

  it('renders and selects a suggestion by click', async () => {
    vi.mocked(searchLocations).mockResolvedValue([dallas]);
    render(<Harness />);
    fireEvent.change(screen.getByRole('combobox', { name: 'Origin' }), { target: { value: 'Dallas' } });

    const option = await screen.findByRole('option', { name: /Dallas.*Texas, United States/i });
    fireEvent.click(option);

    expect(screen.getByRole('combobox', { name: 'Origin' })).toHaveValue(dallas.label);
    expect(screen.getByTestId('selected-location')).toHaveTextContent(dallas.id);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('opens labeled popular US suggestions on focus and supports keyboard selection', () => {
    render(<Harness />);
    const input = screen.getByRole('combobox', { name: 'Origin' });
    fireEvent.focus(input);

    expect(screen.getByText('Popular US locations')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /New York.*New York, United States/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Dallas.*Texas, United States/i })).toBeInTheDocument();
    expect(searchLocations).not.toHaveBeenCalled();

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(input).toHaveValue('New York, NY, USA');
    expect(screen.getByTestId('selected-location')).toHaveTextContent('new-york-ny');
  });

  it('keeps an ambiguous city distinct using provider-returned state context', async () => {
    const springfields: LocationSuggestion[] = [
      { ...dallas, id: 'springfield-il', primary: 'Springfield', secondary: 'Illinois, United States', label: 'Springfield, Illinois, United States', lat: 39.7817, lon: -89.6501 },
      { ...dallas, id: 'springfield-mo', primary: 'Springfield', secondary: 'Missouri, United States', label: 'Springfield, Missouri, United States', lat: 37.209, lon: -93.2923 },
    ];
    vi.mocked(searchLocations).mockResolvedValue(springfields);
    render(<Harness />);
    fireEvent.change(screen.getByRole('combobox', { name: 'Origin' }), { target: { value: 'Springfield' } });

    expect(await screen.findByRole('option', { name: /Springfield.*Illinois, United States/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Springfield.*Missouri, United States/i })).toBeInTheDocument();
  });

  it('supports Arrow navigation, Enter selection, and Escape dismissal', async () => {
    vi.mocked(searchLocations).mockResolvedValue([dallas, elPaso]);
    render(<Harness />);
    const input = screen.getByRole('combobox', { name: 'Origin' });
    fireEvent.change(input, { target: { value: 'Tex' } });
    await screen.findByRole('option', { name: /Dallas/i });

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(screen.getByRole('option', { name: /Dallas/i })).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(screen.getByRole('option', { name: /El Paso/i })).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(input).toHaveValue(elPaso.label);

    fireEvent.change(input, { target: { value: 'Texa' } });
    await screen.findByRole('option', { name: /Dallas/i });
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('shows loading, empty, and recoverable error states', async () => {
    vi.useFakeTimers();
    let resolveSearch: ((value: LocationSuggestion[]) => void) | undefined;
    vi.mocked(searchLocations).mockImplementation(() => new Promise((resolve) => {
      resolveSearch = resolve;
    }));
    render(<Harness />);
    fireEvent.change(screen.getByRole('combobox', { name: 'Origin' }), { target: { value: 'xyz' } });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(screen.getByText('Searching locations…')).toBeInTheDocument();
    await act(async () => resolveSearch?.([]));
    expect(screen.getByText(/no locations found/i)).toBeInTheDocument();

    vi.mocked(searchLocations).mockRejectedValue(new Error('Search is temporarily unavailable.'));
    fireEvent.change(screen.getByRole('combobox', { name: 'Origin' }), { target: { value: 'abc' } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(screen.getByRole('alert')).toHaveTextContent(/temporarily unavailable/i);
  });

  it('clears a selected location and invalidates it when the text is edited', async () => {
    vi.mocked(searchLocations).mockResolvedValue([dallas]);
    render(<Harness />);
    const input = screen.getByRole('combobox', { name: 'Origin' });
    fireEvent.change(input, { target: { value: 'Dallas' } });
    fireEvent.click(await screen.findByRole('option', { name: /Dallas/i }));
    expect(screen.getByTestId('selected-location')).toHaveTextContent(dallas.id);

    fireEvent.change(input, { target: { value: 'Dall' } });
    expect(screen.getByTestId('selected-location')).toHaveTextContent('none');
    fireEvent.click(screen.getByRole('button', { name: 'Clear Origin' }));
    expect(input).toHaveValue('');
    expect(screen.getByTestId('selected-location')).toHaveTextContent('none');
    expect(screen.getByText('Popular US locations')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /New York.*New York, United States/i })).toBeInTheDocument();
  });

  it('ignores a slower response for an older query', async () => {
    vi.useFakeTimers();
    const pending: Array<(value: LocationSuggestion[]) => void> = [];
    vi.mocked(searchLocations).mockImplementation(() => new Promise((resolve) => pending.push(resolve)));
    render(<Harness />);
    const input = screen.getByRole('combobox', { name: 'Origin' });

    fireEvent.change(input, { target: { value: 'Dal' } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    fireEvent.change(input, { target: { value: 'Dall' } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    await act(async () => pending[1]?.([dallas]));
    expect(screen.getByRole('option', { name: /Dallas/i })).toBeInTheDocument();
    await act(async () => pending[0]?.([elPaso]));
    expect(screen.getByRole('option', { name: /Dallas/i })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /El Paso/i })).not.toBeInTheDocument();
  });
});
