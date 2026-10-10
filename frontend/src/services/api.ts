import axios from 'axios'
import type { ErrorResponse, Itinerary, SessionEditResponse, SessionConstraints, TripEditResponse, TripListResponse, TripRequest, TripSaveRequest, TripSession } from '@/types'

// MoMA may retry up to three times and optional map/weather enrichment runs afterwards.
const api = axios.create({ baseURL: '/api', timeout: 300000, headers: { 'Content-Type': 'application/json' } })

function rethrow(error: unknown): never {
  if (axios.isAxiosError<ErrorResponse>(error)) {
    const detail = error.response?.data
    throw new Error(detail?.message || error.message || '请求失败')
  }
  throw error instanceof Error ? error : new Error('请求失败')
}

export async function generateTrip(request: TripRequest) { try { return (await api.post<Itinerary>('/trip/generate', request)).data } catch (e) { return rethrow(e) } }
export async function saveTrip(itinerary: Itinerary, expected_version: number | null) { try { const body: TripSaveRequest = { itinerary, expected_version }; return (await api.post<Itinerary>('/trip/save', body)).data } catch (e) { return rethrow(e) } }
export async function listTrips(cursor?: string | null) { try { return (await api.get<TripListResponse>('/trip', { params: { limit: 20, cursor: cursor || undefined } })).data } catch (e) { return rethrow(e) } }
export async function getTrip(tripId: string) { try { return (await api.get<Itinerary>(`/trip/${tripId}`)).data } catch (e) { return rethrow(e) } }
export async function deleteTrip(tripId: string) { try { await api.delete(`/trip/${tripId}`) } catch (e) { return rethrow(e) } }
export async function editTrip(tripId: string, expected_version: number, date: string, instruction: string) { try { return (await api.post<TripEditResponse>(`/trip/${tripId}/edit`, { expected_version, date, instruction })).data } catch (e) { return rethrow(e) } }
export async function createSession(tripId: string, version: number, constraints: SessionConstraints = {}) { try { return (await api.post<TripSession>(`/trip/${tripId}/sessions`, { version, constraints })).data } catch (e) { return rethrow(e) } }
export async function editSession(tripId: string, sessionId: string, date: string, instruction: string) { try { return (await api.post<SessionEditResponse>(`/trip/${tripId}/sessions/${sessionId}/edit`, { date, instruction })).data } catch (e) { return rethrow(e) } }
export async function exportTrip(tripId: string, version: number, format: 'markdown' | 'pdf') { try { return (await api.get(`/trip/${tripId}/export`, { params: { version, format }, responseType: 'blob' })).data as Blob } catch (e) { return rethrow(e) } }
