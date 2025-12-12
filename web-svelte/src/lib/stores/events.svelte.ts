/**
 * Events store for Argus dashboard
 *
 * Manages event state with deduplication and real-time updates via WebSocket.
 */

import websocket, { type ServerMessage } from "./websocket.svelte";

// Event type matching backend schema
export interface Event {
  id: number;
  source: string;
  event_type: "tool" | "session" | "agent" | "response" | "prompt";
  timestamp: string;
  message?: string;
  level?: "debug" | "info" | "warn" | "error";
  session_id?: string;
  agent_id?: string;
  data?: Record<string, unknown>;
  // Additional fields from backend
  hook?: string;
  tool_name?: string;
  tool_use_id?: string;
  status?: string;
  is_background?: boolean;
}

// Module-level state using Svelte 5 runes
let events: Event[] = $state([]);
let knownEventIds: Set<number> = new Set();
let eventCount: number = $state(0);

// Add event with deduplication
function addEvent(event: Event): boolean {
  if (knownEventIds.has(event.id)) {
    return false; // Duplicate, skip
  }

  knownEventIds.add(event.id);
  events = [event, ...events]; // Newest first
  eventCount = events.length;
  return true;
}

// Add multiple events (for historical fetch)
function addEvents(newEvents: Event[]): void {
  for (const event of newEvents) {
    if (!knownEventIds.has(event.id)) {
      knownEventIds.add(event.id);
    }
  }
  // For historical, append in order (already sorted by API)
  events = [...newEvents.filter((e) => !knownEventIds.has(e.id)), ...events];
  eventCount = events.length;
}

// Clear all events (for refresh)
function clearEvents(): void {
  events = [];
  knownEventIds.clear();
  eventCount = 0;
}

// Get events (reactive getter)
function getEvents(): Event[] {
  return events;
}

// Get event count
function getEventCount(): number {
  return eventCount;
}

// Handle incoming event message from WebSocket
function handleEventMessage(message: ServerMessage): void {
  const event = message.event as Event;
  if (event) {
    const added = addEvent(event);
    if (added) {
      console.log(
        `[events] Added event ${event.id}: ${event.event_type} - ${event.message?.slice(0, 50)}`,
      );
    }
  }
}

// Initialize WebSocket handler registration
function initializeHandlers(): () => void {
  const unsubscribe = websocket.onMessage("event", handleEventMessage);
  console.log("[events] Registered WebSocket handler for 'event' messages");
  return unsubscribe;
}

// Export store interface
export const eventsStore = {
  getEvents,
  getEventCount,
  addEvent,
  addEvents,
  clearEvents,
  initializeHandlers,
};

export default eventsStore;
