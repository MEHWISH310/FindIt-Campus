// Singleton Socket.IO connection -- imported anywhere that needs live
// updates (right now: NotificationToast). One shared connection for the
// whole app rather than reconnecting per-component.
//
// Matches the backend: app/realtime.py mounts python-socketio at the
// default "/socket.io" path on the SAME port as the REST API (see
// backend/app/main.py's `app = socketio.ASGIApp(sio, other_asgi_app=...)`),
// so this reuses API_BASE rather than a separate URL/port.

import { io } from 'socket.io-client';
import { API_BASE } from './client';

export const socket = io(API_BASE, {
  path: '/socket.io',
  transports: ['websocket', 'polling'],
  autoConnect: true,
});