import type {
  HealthResponse,
  MetricsPayload,
  PatientsResponse,
  Scenario,
  Snapshot,
} from './types';

export class ApiRequestError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(message: string, status: number, payload?: unknown) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
    this.payload = payload;
  }
}

function messageFromPayload(payload: unknown, fallback: string): string {
  if (typeof payload === 'object' && payload !== null) {
    const record = payload as Record<string, unknown>;
    for (const key of ['message', 'detail', 'error']) {
      if (typeof record[key] === 'string' && record[key].trim()) {
        return record[key];
      }
    }
  }
  return fallback;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error;
    }
    throw new ApiRequestError(
      'The local API could not be reached. Start the backend on 127.0.0.1:8000.',
      0,
      error,
    );
  }

  const contentType = response.headers.get('content-type') ?? '';
  let payload: unknown = null;
  if (contentType.includes('json')) {
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
  } else {
    try {
      const text = await response.text();
      payload = text || null;
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    throw new ApiRequestError(
      messageFromPayload(payload, `API request failed (${response.status}).`),
      response.status,
      payload,
    );
  }
  return payload as T;
}

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return requestJson<HealthResponse>('/api/health', { signal });
}

export function getPatients(signal?: AbortSignal): Promise<PatientsResponse> {
  return requestJson<PatientsResponse>('/api/patients', { signal });
}

export function getSnapshot(
  patientId: string,
  step: number,
  sensorDropout: boolean,
  signal?: AbortSignal,
): Promise<Snapshot> {
  const params = new URLSearchParams({
    step: String(step),
    sensor_dropout: String(sensorDropout),
  });
  return requestJson<Snapshot>(`/api/twin/${encodeURIComponent(patientId)}?${params}`, {
    signal,
  });
}

export function simulate(
  patientId: string,
  input: {
    step: number;
    activity_minutes: number;
    meal_carbs: number;
    sensor_dropout: boolean;
  },
  signal?: AbortSignal,
): Promise<Scenario> {
  return requestJson<Scenario>(`/api/twin/${encodeURIComponent(patientId)}/simulate`, {
    method: 'POST',
    body: JSON.stringify(input),
    signal,
  });
}

export function getMetrics(signal?: AbortSignal): Promise<MetricsPayload> {
  return requestJson<MetricsPayload>('/api/metrics', { signal });
}
