import { useEffect, useId, useRef, useState } from 'react';
import { AlertCircle, LoaderCircle, MapPin, Search, X } from 'lucide-react';
import { searchLocations } from '../api/client';
import type { LocationSuggestion } from '../types';

type LocationAutocompleteProps = {
  label: string;
  value: string;
  selectedLocation: LocationSuggestion | null;
  error?: string;
  onChange: (value: string) => void;
  onSelect: (location: LocationSuggestion) => void;
};

const MIN_QUERY_LENGTH = 3;
const SEARCH_DEBOUNCE_MS = 300;

const POPULAR_US_LOCATIONS: LocationSuggestion[] = ([
  ['new-york-ny', 'New York', 'New York, United States', 'New York, NY, USA', 40.7128, -74.006],
  ['los-angeles-ca', 'Los Angeles', 'California, United States', 'Los Angeles, CA, USA', 34.0522, -118.2437],
  ['chicago-il', 'Chicago', 'Illinois, United States', 'Chicago, IL, USA', 41.8781, -87.6298],
  ['houston-tx', 'Houston', 'Texas, United States', 'Houston, TX, USA', 29.7604, -95.3698],
  ['phoenix-az', 'Phoenix', 'Arizona, United States', 'Phoenix, AZ, USA', 33.4484, -112.074],
  ['philadelphia-pa', 'Philadelphia', 'Pennsylvania, United States', 'Philadelphia, PA, USA', 39.9526, -75.1652],
  ['san-antonio-tx', 'San Antonio', 'Texas, United States', 'San Antonio, TX, USA', 29.4241, -98.4936],
  ['san-diego-ca', 'San Diego', 'California, United States', 'San Diego, CA, USA', 32.7157, -117.1611],
  ['dallas-tx', 'Dallas', 'Texas, United States', 'Dallas, TX, USA', 32.7767, -96.797],
  ['san-jose-ca', 'San Jose', 'California, United States', 'San Jose, CA, USA', 37.3382, -121.8863],
  ['austin-tx', 'Austin', 'Texas, United States', 'Austin, TX, USA', 30.2672, -97.7431],
  ['jacksonville-fl', 'Jacksonville', 'Florida, United States', 'Jacksonville, FL, USA', 30.3322, -81.6557],
  ['fort-worth-tx', 'Fort Worth', 'Texas, United States', 'Fort Worth, TX, USA', 32.7555, -97.3308],
  ['columbus-oh', 'Columbus', 'Ohio, United States', 'Columbus, OH, USA', 39.9612, -82.9988],
  ['charlotte-nc', 'Charlotte', 'North Carolina, United States', 'Charlotte, NC, USA', 35.2271, -80.8431],
  ['indianapolis-in', 'Indianapolis', 'Indiana, United States', 'Indianapolis, IN, USA', 39.7684, -86.1581],
] satisfies Array<[string, string, string, string, number, number]>).map(([id, primary, secondary, label, lat, lon]) => ({
  id: String(id),
  primary: String(primary),
  secondary: String(secondary),
  label: String(label),
  lat: Number(lat),
  lon: Number(lon),
}));

function deduplicateSuggestions(results: LocationSuggestion[]) {
  const seen = new Set<string>();
  return results.filter((suggestion) => {
    const key = `${suggestion.lat.toFixed(5)},${suggestion.lon.toFixed(5)}:${suggestion.label.trim().toLocaleLowerCase()}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export default function LocationAutocomplete({
  label,
  value,
  selectedLocation,
  error,
  onChange,
  onSelect,
}: LocationAutocompleteProps) {
  const generatedId = useId();
  const inputId = `${generatedId}-input`;
  const listboxId = `${generatedId}-listbox`;
  const errorId = `${generatedId}-error`;
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const requestId = useRef(0);
  const [isOpen, setIsOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<LocationSuggestion[]>([]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [isLoading, setIsLoading] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [hasSearched, setHasSearched] = useState(false);

  useEffect(() => {
    if (!isOpen || value.trim().length < MIN_QUERY_LENGTH || selectedLocation?.label === value) {
      return;
    }

    const currentRequestId = ++requestId.current;
    const controller = new AbortController();

    const timeoutId = window.setTimeout(async () => {
      setIsLoading(true);
      try {
        const results = await searchLocations(value.trim(), controller.signal);
        if (requestId.current !== currentRequestId || controller.signal.aborted) return;
        setSuggestions(deduplicateSuggestions(results));
        setHasSearched(true);
      } catch (error) {
        if (controller.signal.aborted || requestId.current !== currentRequestId) return;
        setSearchError(error instanceof TypeError
          ? 'Could not connect to location search. Check your connection and try again.'
          : error instanceof Error
            ? error.message
            : 'Location search failed. Please try again.');
        setHasSearched(true);
      } finally {
        if (requestId.current === currentRequestId && !controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timeoutId);
      controller.abort();
      if (requestId.current === currentRequestId) requestId.current += 1;
    };
  }, [isOpen, selectedLocation?.label, value]);

  useEffect(() => {
    function handleOutsidePointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
        setActiveIndex(-1);
      }
    }

    document.addEventListener('mousedown', handleOutsidePointerDown);
    return () => document.removeEventListener('mousedown', handleOutsidePointerDown);
  }, []);

  function chooseSuggestion(suggestion: LocationSuggestion) {
    requestId.current += 1;
    onSelect(suggestion);
    setIsOpen(false);
    setActiveIndex(-1);
    setSuggestions([]);
    setIsLoading(false);
    setSearchError('');
    setHasSearched(false);
  }

  const normalizedQuery = value.trim();
  const showDropdown = isOpen && selectedLocation?.label !== value;
  const displayedSuggestions = normalizedQuery.length === 0
    ? POPULAR_US_LOCATIONS
    : normalizedQuery.length < MIN_QUERY_LENGTH
      ? []
      : suggestions;

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      setIsOpen(false);
      setActiveIndex(-1);
      return;
    }

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (!isOpen && selectedLocation?.label === value) return;
      if (!isOpen) setIsOpen(true);
      if (displayedSuggestions.length === 0) return;
      event.preventDefault();
      setActiveIndex((current) => {
        if (event.key === 'ArrowDown') return current >= displayedSuggestions.length - 1 ? 0 : current + 1;
        return current <= 0 ? displayedSuggestions.length - 1 : current - 1;
      });
      return;
    }

    if (event.key === 'Enter' && isOpen && activeIndex >= 0 && displayedSuggestions[activeIndex]) {
      event.preventDefault();
      chooseSuggestion(displayedSuggestions[activeIndex]);
    }
  }

  const statusText = !isOpen
    ? ''
    : isLoading
    ? 'Searching locations'
    : value.trim().length === 0
      ? `${POPULAR_US_LOCATIONS.length} popular US locations available.`
    : value.trim().length < MIN_QUERY_LENGTH
      ? `Type at least ${MIN_QUERY_LENGTH} characters to search US locations.`
    : searchError
      ? searchError
      : hasSearched
        ? suggestions.length === 0
          ? 'No matching locations found.'
          : `${suggestions.length} location suggestions available.`
        : '';
  return (
    <div
      ref={containerRef}
      className={`relative ${isOpen ? 'z-50' : 'z-10'}`}
      onBlurCapture={(event) => {
        if (!containerRef.current?.contains(event.relatedTarget as Node | null)) {
          setIsOpen(false);
          setActiveIndex(-1);
        }
      }}
    >
      <label htmlFor={inputId} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      <div className={`relative mt-2 rounded-xl border bg-slate-50 transition focus-within:ring-2 focus-within:ring-slate-300 ${error ? 'border-red-400 focus-within:ring-red-200' : 'border-slate-200 focus-within:border-slate-400'}`}>
        <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          id={inputId}
          type="text"
          role="combobox"
          aria-label={label}
          aria-autocomplete="list"
          aria-expanded={showDropdown}
          aria-controls={showDropdown && displayedSuggestions.length > 0 && !isLoading && !searchError ? listboxId : undefined}
          aria-activedescendant={isOpen && activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? errorId : undefined}
          autoComplete="off"
          maxLength={120}
          ref={inputRef}
          value={value}
          onFocus={() => {
            if (selectedLocation?.label !== value) setIsOpen(true);
          }}
          onChange={(event) => {
            requestId.current += 1;
            onChange(event.target.value);
            setSuggestions([]);
            setIsLoading(false);
            setSearchError('');
            setHasSearched(false);
            setIsOpen(true);
            setActiveIndex(-1);
          }}
          onKeyDown={handleKeyDown}
          placeholder="Search for a city, address, or place..."
          className="h-11 w-full rounded-xl bg-transparent py-2.5 pl-10 pr-10 text-sm text-slate-900 outline-none placeholder:text-slate-400"
        />
        {isLoading ? (
          <LoaderCircle aria-hidden="true" className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-slate-500" />
        ) : value ? (
          <button
            type="button"
            aria-label={`Clear ${label}`}
            onClick={() => {
              requestId.current += 1;
              onChange('');
              setSuggestions([]);
              setIsLoading(false);
              setSearchError('');
              setHasSearched(false);
              setIsOpen(true);
              setActiveIndex(-1);
              inputRef.current?.focus();
            }}
            className="absolute right-2 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-200 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-500"
          >
            <X aria-hidden="true" className="h-4 w-4" />
          </button>
        ) : null}
      </div>
      <div className="sr-only" aria-live="polite" aria-atomic="true">{statusText}</div>
      {error && <p id={errorId} className="mt-1 text-xs text-red-600">{error}</p>}

      {showDropdown && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-[min(20rem,calc(100vh-10rem))] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg">
          {normalizedQuery.length === 0 && (
            <div className="border-b border-slate-100 px-3 py-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Popular US locations</p>
              <p className="mt-0.5 text-xs text-slate-500">Start typing to search all US locations.</p>
            </div>
          )}
          {normalizedQuery.length > 0 && normalizedQuery.length < MIN_QUERY_LENGTH && (
            <p className="px-3 py-3 text-sm text-slate-600">Type at least {MIN_QUERY_LENGTH} characters to search locations.</p>
          )}
          {isLoading && (
            <p className="flex items-center gap-2 px-3 py-3 text-sm text-slate-600" role="status">
              <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" />
              Searching locations…
            </p>
          )}
          {!isLoading && searchError && (
            <p className="flex min-h-12 items-center gap-2 bg-red-50 px-3 py-3 text-sm text-red-800" role="alert">
              <AlertCircle aria-hidden="true" className="h-4 w-4 shrink-0" />
              <span>{searchError} You can edit the search and try again.</span>
            </p>
          )}
          {!isLoading && !searchError && normalizedQuery.length >= MIN_QUERY_LENGTH && hasSearched && suggestions.length === 0 && (
            <p className="px-3 py-3 text-sm text-slate-600">No locations found. Check the spelling or try a nearby city.</p>
          )}
          {!isLoading && !searchError && displayedSuggestions.length > 0 && (
            <ul id={listboxId} role="listbox" aria-label={`${label} location suggestions`} className="max-h-[min(16rem,calc(100vh-14rem))] overflow-y-auto py-1">
              {displayedSuggestions.map((suggestion, index) => (
                <li
                  id={`${listboxId}-option-${index}`}
                  key={suggestion.id}
                  role="option"
                  aria-selected={activeIndex === index}
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => chooseSuggestion(suggestion)}
                  className={`flex cursor-pointer items-start gap-3 px-3 py-2.5 text-left transition-colors ${activeIndex === index ? 'bg-slate-100' : 'hover:bg-slate-50'}`}
                >
                  <MapPin aria-hidden="true" className={`mt-0.5 h-4 w-4 shrink-0 ${activeIndex === index ? 'text-slate-800' : 'text-slate-500'}`} />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-slate-900">{suggestion.primary}</span>
                    <span className="block truncate text-xs text-slate-500">{suggestion.secondary}</span>
                  </span>
                  {activeIndex === index && <span className="sr-only">Highlighted</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
