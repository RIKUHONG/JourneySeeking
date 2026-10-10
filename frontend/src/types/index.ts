export type Pace = 'relaxed' | 'normal' | 'intensive'
export type HotelLevel = 'budget' | 'three_star' | 'four_star' | 'five_star' | '不指定'

export interface TripRequest {
  destination: string
  start_date: string
  end_date: string
  travelers: number
  budget: number | null
  preferences: string[]
  pace: Pace | null
  dietary_preferences: string[]
  hotel_level: HotelLevel | null
  special_notes: string | null
}

export interface RouteInfo { mode: 'driving' | 'walking'; distance_meters: number; duration_seconds: number; source: string }
export interface WeatherInfo { status: 'available' | 'unknown'; condition: string | null; low_celsius: number | null; high_celsius: number | null; source: string | null; fetched_at: string | null }
export interface Activity {
  time: string; name: string; description: string; location: string | null; duration_minutes: number | null; estimated_cost: number
  poi_id: string | null; poi_category: 'spot' | 'meal' | 'hotel' | null; address: string | null; latitude: number | null; longitude: number | null
  poi_status: 'not_attempted' | 'verified' | 'not_found' | 'ambiguous' | 'unavailable'; map_source: string | null; route_from_previous: RouteInfo | null
  route_status: 'not_attempted' | 'verified' | 'missing_coordinates' | 'unavailable'
}
export interface DayPlan { date: string; title: string; activities: Activity[]; weather: WeatherInfo | null; weather_advice: string[] }
export interface Itinerary { trip_id: string | null; version: number | null; destination: string; start_date: string; end_date: string; summary: string; days: DayPlan[]; total_estimated_cost: number; map_enrichment_status: 'not_attempted' | 'completed' | 'partial' | 'unavailable' }
export interface TripSaveRequest { itinerary: Itinerary; expected_version: number | null }
export interface TripSummary { trip_id: string; version: number; destination: string; summary: string; start_date: string; end_date: string }
export interface TripListResponse { items: TripSummary[]; next_cursor: string | null }
export interface TripEditResponse { trip_id: string; version: number; itinerary: Itinerary; change_summary: string[] }
export interface SessionConstraints { travelers?: number; budget?: number | null; preferences?: string[]; pace?: Pace | null; dietary_preferences?: string[]; hotel_level?: HotelLevel | null; special_notes?: string | null }
export interface SessionTurn { turn_id: string; instruction: string; target_date: string; base_version: number; result_version: number | null; status: string; change_summary: string[]; created_at: string }
export interface TripSession { session_id: string; trip_id: string; current_version: number; initial_version: number; constraints: SessionConstraints; summary: string; recent_turns: SessionTurn[]; created_at: string; updated_at: string; expires_at: string }
export interface SessionEditResponse { session_id: string; trip_id: string; version: number; itinerary: Itinerary; change_summary: string[]; session: TripSession }
export interface ErrorResponse { code: string; message: string; request_id: string }

/** Fill fields omitted by FastAPI response_model_exclude_defaults. */
export function normalizeItinerary(value: Itinerary): Itinerary {
  return {
    ...value,
    trip_id: value.trip_id ?? null,
    version: value.version ?? null,
    days: Array.isArray(value.days) ? value.days.map((day) => ({
      ...day,
      activities: Array.isArray(day.activities) ? day.activities.map((activity) => ({
        ...activity,
        location: activity.location ?? null,
        duration_minutes: activity.duration_minutes ?? null,
        estimated_cost: activity.estimated_cost ?? 0,
        poi_id: activity.poi_id ?? null,
        poi_category: activity.poi_category ?? null,
        address: activity.address ?? null,
        latitude: activity.latitude ?? null,
        longitude: activity.longitude ?? null,
        poi_status: activity.poi_status ?? 'not_attempted',
        map_source: activity.map_source ?? null,
        route_from_previous: activity.route_from_previous ?? null,
        route_status: activity.route_status ?? 'not_attempted'
      })) : [],
      weather: day.weather ?? null,
      weather_advice: Array.isArray(day.weather_advice) ? day.weather_advice : []
    })) : []
  }
}
