export type RiskLevel = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel' | 'unknown';

export type Coordinate = {
  lat: number;
  lon: number;
};

export type LocationSuggestion = Coordinate & {
  id: string;
  primary: string;
  secondary: string;
  label: string;
};

export type Checkpoint = {
  distance_meters: number;
  distance_miles: number;
  lat: number;
  lon: number;
  eta: string;
  risk: RiskLevel;
  wind_risk: RiskLevel;
  rain_risk: RiskLevel;
  snow_risk: RiskLevel;
  weather_coverage?: number;
  forecast?: {
    missing: boolean;
    warning?: string;
    forecast_time?: string;
    wind_mph?: number | null;
    rain_in_hr?: number | null;
    snow_in_hr?: number | null;
  };
};

export type RoutePlanResponse = {
  origin: { name: string; lat: number; lon: number };
  destination: { name: string; lat: number; lon: number };
  routes: RouteSummary[];
  recommended_route?: RouteSummary | null;
  warnings: string[];
  metadata: Record<string, unknown>;
};

export type RouteSummary = {
  name: string;
  distance_miles: number;
  duration_minutes: number;
  eta: string;
  severe_miles: number;
  high_miles: number;
  no_travel_checkpoints: number;
  average_risk_score: number;
  weather_coverage_percent: number;
  has_confirmed_no_travel: boolean;
  recommended?: boolean;
  rank?: number;
  checkpoints: Checkpoint[];
  geometry: Coordinate[];
};
