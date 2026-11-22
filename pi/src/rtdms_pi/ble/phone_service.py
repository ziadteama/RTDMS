"""Thin GATT registration and schema boundary for the phone service."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..buzzer import PatternPlayer
from ..incidents_api import IncidentSink
from ..payloads import alert_payload, physio_payload, status_payload, to_json_bytes
from ..settings import SettingsStore
from ..sources import GarminPhysioSource
from ..state import RuntimeState
from .auth import AuthGate
from .contract import validate
from .gatt import GattPort, GattWriteRejected
from .handlers_clock_auth import handle_auth, handle_clock
from .handlers_command import handle_command, log_command
from .handlers_incident import handle_incident
from .handlers_settings import handle_settings
from .notifier import Notifier
from .throttle import GarminLossMonitor
from .uuids import GARMIN_CHAR_UUID, Char


@dataclass
class ServiceStats:
    bad_writes: int = 0


class PhoneService:
    def __init__(
        self,
        port: GattPort,
        runtime_state: RuntimeState,
        player: PatternPlayer,
        settings: SettingsStore,
        incidents: IncidentSink,
        clock: Callable[[], float],
        auth: AuthGate,
        health_fn: Callable[[], dict[str, Any]],
        on_command: Callable[[str, dict[str, Any]], None] = log_command,
        garmin: GarminPhysioSource | None = None,
        start_calibration: Callable[[], None] | None = None,
        apply_phone_calibration: Callable[[dict[str, Any]], None] | None = None,
        validate_outgoing: bool = False,
    ) -> None:
        self.validate_outgoing = validate_outgoing
        self.port, self.state, self.player = port, runtime_state, player
        self.settings, self.incidents, self.clock = settings, incidents, clock
        self.auth, self.health_fn, self.on_command = auth, health_fn, on_command
        self.start_calibration = start_calibration
        self.apply_phone_calibration = apply_phone_calibration
        self.stats = ServiceStats()
        self.notifier = Notifier(runtime_state, clock, self._emit, settings.read)
        self.loss = GarminLossMonitor(self.set_throttle)
        self.garmin = garmin if garmin is not None else GarminPhysioSource()
        port.set_disconnect_handler(self.on_disconnect)
        port.add_characteristic(
            GARMIN_CHAR_UUID, frozenset({"write", "write_no_response"}), None, self._garmin_write
        )
        self._register()

    def _register(self) -> None:
        readable = {Char.ALERT, Char.STATUS, Char.PHYSIO, Char.SETTINGS, Char.HEALTH}
        writable = {Char.SETTINGS, Char.COMMAND, Char.INCIDENT, Char.CLOCK, Char.AUTH}
        notifiable = {Char.ALERT, Char.STATUS, Char.PHYSIO, Char.RESULT}
        for char in Char:
            props = frozenset(
                p
                for p, group in (("read", readable), ("write", writable), ("notify", notifiable))
                if char in group
            )
            self.port.add_characteristic(
                char.uuid,
                props,
                self._reader(char) if char in readable else None,
                self._writer(char) if char in writable else None,
            )

    def _reader(self, char: Char) -> Callable[[], bytes]:
        return lambda: self.read(char)

    def _writer(self, char: Char) -> Callable[[bytes], None]:
        return lambda raw: self.write(char, raw)

    def on_disconnect(self) -> None:
        self.auth.reset()

    def _garmin_write(self, raw: bytes) -> None:
        tracker = self.garmin.receiver.tracker
        before_lost, before_received = tracker.lost, tracker.received
        self.garmin.handle_write(raw)  # synchronous, before any phone scheduling
        for _ in range(min(60, tracker.lost - before_lost)):
            self.loss.record(lost=True)
        self.loss.record(lost=tracker.received == before_received)

    def read(self, char: Char) -> bytes:
        snapshot = self.state.snapshot()
        builders: dict[Char, Callable[[], dict[str, Any]]] = {
            Char.ALERT: lambda: alert_payload(snapshot.decision, self.clock()),
            Char.STATUS: lambda: status_payload(snapshot, self.settings.read()),
            Char.PHYSIO: lambda: physio_payload(snapshot),
            Char.SETTINGS: self.settings.read,
            Char.HEALTH: self.health_fn,
        }
        clean = validate(char.name.lower(), builders[char]())
        if clean is None:
            raise ValueError("invalid outgoing payload")
        encoded = to_json_bytes(clean)
        limit = 512 if char == Char.HEALTH else 240 if char != Char.SETTINGS else None
        if limit is not None and len(encoded) > limit:
            raise ValueError("outgoing payload exceeds budget")
        return encoded

    def write(self, char: Char, raw: bytes) -> None:
        if char == Char.AUTH and self.auth.open_mode:
            return  # dev open mode: any (or empty) token is accepted, nothing to check
        if char != Char.AUTH and not self.auth.authed:
            raise GattWriteRejected("insufficient authentication")
        try:
            obj = json.loads(raw.decode("utf-8"), parse_constant=self._reject_constant)
        except (ValueError, UnicodeError, RecursionError):
            self.stats.bad_writes += 1
            if char == Char.AUTH:
                raise GattWriteRejected("insufficient authentication") from None
            return
        # Null has the same meaning as an omitted profile for calibration.
        if (
            char == Char.COMMAND
            and isinstance(obj, dict)
            and obj.get("cmd") == "calibrate"
            and obj.get("profile") is None
        ):
            obj.pop("profile", None)
        schema = "incident_request" if char == Char.INCIDENT else char.name.lower()
        if char == Char.SETTINGS:
            with self.settings.lock:
                clean = validate(schema, obj)
                merged = (
                    validate(schema, self.settings.merged(clean)) if clean is not None else None
                )
                if merged is not None:
                    handle_settings(merged, self.settings)
                    self.auth.touch()
                    return
        else:
            clean = validate(schema, obj)
            if clean is not None:
                self._dispatch(char, clean)
                if char != Char.AUTH:
                    self.auth.touch()
                return
        self.stats.bad_writes += 1
        if char == Char.AUTH:
            raise GattWriteRejected("insufficient authentication")

    @staticmethod
    def _reject_constant(value: str) -> None:
        raise ValueError("non-finite JSON number")

    def _dispatch(self, char: Char, payload: dict[str, Any]) -> None:
        if char == Char.AUTH:
            handle_auth(payload, self.auth)
        elif char == Char.CLOCK:
            handle_clock(payload, self.state, int(self.clock() * 1000))
        elif char == Char.COMMAND:
            self._emit(
                Char.RESULT,
                "command_result",
                handle_command(
                    payload,
                    self.player,
                    self.on_command,
                    self.start_calibration,
                    self.apply_phone_calibration,
                ),
            )
        elif char == Char.INCIDENT:
            self._emit(
                Char.RESULT,
                "incident_response",
                handle_incident(payload, self.incidents, self.state.clock_offset_ms),
            )

    def _emit(self, char: Char, schema: str, payload: dict[str, Any]) -> None:
        if char == Char.RESULT or self.validate_outgoing:
            clean = validate(schema, payload)
            if clean is None:
                raise ValueError("invalid outgoing payload")
            payload = clean
        data = to_json_bytes(payload)
        if char != Char.RESULT and len(data) > 240:
            raise ValueError("notify budget exceeded")
        self.port.notify(char.uuid, data)

    def set_throttle(self, factor: float) -> None:
        self.notifier.set_throttle(factor)

    async def run(self, stop: asyncio.Event) -> None:
        await self.notifier.run(stop)
