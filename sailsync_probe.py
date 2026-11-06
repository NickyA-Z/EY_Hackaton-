#!/usr/bin/env python3
"""Discover SailSync event tracks and export full-resolution boat GPS.

The default search targets the July 2026 San Pedro Olympic Classes Regatta
and the ILCA 7 fleet. Authentication is read from SAILSYNC_API_TOKEN.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterator

import requests


DEFAULT_BASE_URL = "https://www.sailsync.io"
API_PREFIX = "/api/integrations/v1"
SAN_PEDRO = (33.7361, -118.2922)
LA_RADIUS_KM = 100.0
TIMEOUT_SECONDS = 30
MAX_RETRIES = 3


class SailSyncError(RuntimeError):
    """A safe, user-facing SailSync API error."""


class SailSyncClient:
    def __init__(self, token: str, base_url: str = DEFAULT_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "EY-Hackathon-SailSync-Probe/1.0",
            }
        )

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        if not path.startswith("/"):
            raise ValueError(f"SailSync path must be relative: {path!r}")

        url = f"{self.base_url}{path}"
        clean_params = {
            key: value
            for key, value in params.items()
            if value is not None and value != ""
        }

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self.session.get(
                    url,
                    params=clean_params,
                    timeout=TIMEOUT_SECONDS,
                )
            except requests.RequestException as error:
                raise SailSyncError(f"Request failed for {path}: {error}") from error

            if response.status_code != 429 or attempt == MAX_RETRIES:
                break

            retry_after = response.headers.get("Retry-After", "1")
            try:
                delay = max(float(retry_after), 1.0)
            except ValueError:
                delay = 1.0
            if delay > 60:
                try:
                    detail = response.json()
                except ValueError:
                    detail = response.text[:500]
                raise SailSyncError(
                    f"SailSync rate limit reached; retry after {delay:g} seconds. "
                    f"Server detail: {detail}"
                )
            print(f"Rate limited; retrying in {delay:g}s...", file=sys.stderr)
            time.sleep(delay)

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if not response.ok:
            detail = payload if isinstance(payload, dict) else response.text[:500]
            raise SailSyncError(
                f"SailSync returned HTTP {response.status_code} for {path}: {detail}"
            )
        if not isinstance(payload, dict):
            raise SailSyncError(f"SailSync returned a non-object response for {path}")
        return payload

    def account(self) -> dict[str, Any]:
        return self.get(f"{API_PREFIX}/me")

    def events(
        self,
        query: str,
        boat_class: str,
        date_from: str,
        date_to: str,
    ) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        page = 1
        while page:
            payload = self.get(
                f"{API_PREFIX}/events",
                q=query,
                boat_class=boat_class,
                date_from=date_from,
                date_to=date_to,
                page=page,
            )
            found.extend(item for item in payload.get("events", []) if isinstance(item, dict))
            page = payload.get("next_page")
        return found

    def event_sessions(self, event_id: int) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        after: int | None = None
        while True:
            payload = self.get(
                f"{API_PREFIX}/events/{event_id}",
                limit=100,
                after_assignment_id=after,
            )
            sessions.extend(
                item for item in payload.get("sessions", []) if isinstance(item, dict)
            )
            after = payload.get("next_after_assignment_id")
            if after is None:
                return sessions

    def resolve_day(self, event_id: int, assignment_id: int) -> dict[str, Any]:
        return self.get(
            f"{API_PREFIX}/events/{event_id}/days/{assignment_id}/access"
        )

    def tracks(self, session_id: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        tracks: list[dict[str, Any]] = []
        after: int | None = None
        session: dict[str, Any] = {}
        while True:
            payload = self.get(
                f"{API_PREFIX}/sessions/{session_id}/data",
                limit=100,
                after_track_id=after,
            )
            if isinstance(payload.get("session"), dict):
                session = payload["session"]
            tracks.extend(
                item for item in payload.get("tracks", []) if isinstance(item, dict)
            )
            after = payload.get("next_after_track_id")
            if after is None:
                return session, tracks

    def gps_pages(
        self,
        session_id: int,
        track_id: int,
        limit: int = 5000,
    ) -> Iterator[dict[str, Any]]:
        cursor: str | None = None
        while True:
            page = self.get(
                f"{API_PREFIX}/sessions/{session_id}/data/tracks/{track_id}/points",
                limit=limit,
                cursor=cursor,
            )
            yield page
            cursor = page.get("next_cursor")
            if not cursor:
                return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe SailSync for ILCA 7 event GPS and optionally export tracks."
    )
    parser.add_argument(
        "--query",
        default="San Pedro Olympic Classes Regatta",
        help="event search text",
    )
    parser.add_argument("--boat-class", default="ILCA 7")
    parser.add_argument("--date-from", default="2026-07-01")
    parser.add_argument("--date-to", default="2026-07-31")
    parser.add_argument(
        "--base-url",
        default=os.getenv("SAILSYNC_API_BASE_URL", DEFAULT_BASE_URL),
        help="override only for SailSync staging or local tests",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("sailsync_api_results"),
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="download every accessible boat track (default: probe one boat/session)",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="list matching event IDs without requesting sessions or GPS",
    )
    parser.add_argument(
        "--max-tracks-per-session",
        type=int,
        default=1,
        help="boat tracks to probe per session (default: 1; ignored by --download)",
    )
    parser.add_argument(
        "--event-id",
        type=int,
        help="skip discovery and inspect one known SailSync event ID",
    )
    parser.add_argument(
        "--session-id",
        type=int,
        help="inspect one known session directly (useful with --course-only)",
    )
    parser.add_argument(
        "--course-only",
        action="store_true",
        help="export mark/pin/start-boat metadata and any exposed GPS",
    )
    return parser.parse_args()


def haversine_km(lat: float, lng: float, target: tuple[float, float] = SAN_PEDRO) -> float:
    lat1, lng1, lat2, lng2 = map(
        math.radians,
        (lat, lng, target[0], target[1]),
    )
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(math.sqrt(value))


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned[:100] or "track"


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def write_track_csv(path: Path, points: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["time_epoch", "lat", "lng"])
        writer.writeheader()
        writer.writerows(
            {
                "time_epoch": point.get("time_epoch"),
                "lat": point.get("lat"),
                "lng": point.get("lng"),
            }
            for point in points
        )


def geojson_geometry(points: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Create lines while preserving gaps represented by null coordinates."""
    segments: list[list[list[float]]] = []
    segment: list[list[float]] = []
    for point in points:
        lat, lng = point.get("lat"), point.get("lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            segment.append([float(lng), float(lat)])
        else:
            if len(segment) >= 2:
                segments.append(segment)
            segment = []
    if len(segment) >= 2:
        segments.append(segment)
    if not segments:
        return None
    if len(segments) == 1:
        return {"type": "LineString", "coordinates": segments[0]}
    return {"type": "MultiLineString", "coordinates": segments}


def summarize_points(points: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [
        point
        for point in points
        if isinstance(point.get("lat"), (int, float))
        and isinstance(point.get("lng"), (int, float))
    ]
    if not valid:
        return {
            "downloaded_points": len(points),
            "valid_positions": 0,
            "minimum_distance_to_san_pedro_km": None,
            "near_los_angeles": False,
        }
    distances = [haversine_km(point["lat"], point["lng"]) for point in valid]
    return {
        "downloaded_points": len(points),
        "valid_positions": len(valid),
        "minimum_distance_to_san_pedro_km": round(min(distances), 3),
        "near_los_angeles": min(distances) <= LA_RADIUS_KM,
        "start_time_epoch": valid[0].get("time_epoch"),
        "end_time_epoch": valid[-1].get("time_epoch"),
    }


def matching_sessions(sessions: list[dict[str, Any]], boat_class: str) -> list[dict[str, Any]]:
    if not boat_class.strip():
        return sessions
    wanted = re.sub(r"[^a-z0-9]", "", boat_class.casefold())
    aliases = {wanted}
    if wanted == "ilca7":
        aliases.add("laserstandard")
    return [
        session
        for session in sessions
        if re.sub(r"[^a-z0-9]", "", str(session.get("boat_class", "")).casefold())
        in aliases
    ]


def export_course_objects(
    client: SailSyncClient,
    session_id: int,
    output_dir: Path,
) -> int:
    session, tracks = client.tracks(session_id)
    course_tracks = [track for track in tracks if track.get("type") != "boat"]
    objects: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []

    for track in course_tracks:
        track_id = int(track["session_track_id"])
        item = dict(track)
        item["coordinate_access"] = "metadata_only"
        item["downloaded_points"] = 0

        if track.get("gps_path"):
            points: list[dict[str, Any]] = []
            try:
                for page in client.gps_pages(session_id, track_id):
                    points.extend(
                        point
                        for point in page.get("points", [])
                        if isinstance(point, dict)
                    )
                item["coordinate_access"] = "gps_available"
                item["downloaded_points"] = len(points)
                stem = safe_name(
                    f"course_{session_id}_{track_id}_{track.get('name', 'object')}"
                )
                write_track_csv(output_dir / f"{stem}.csv", points)
                geometry = geojson_geometry(points)
                if geometry:
                    features.append(
                        {
                            "type": "Feature",
                            "geometry": geometry,
                            "properties": {
                                "session_id": session_id,
                                "track_id": track_id,
                                "name": track.get("name"),
                                "object_type": track.get("type"),
                            },
                        }
                    )
            except SailSyncError as error:
                item["coordinate_access"] = "gps_error"
                item["error"] = str(error)
        objects.append(item)

    result = {"session": session, "course_objects": objects}
    json_path = output_dir / f"course_objects_{session_id}.json"
    write_json(json_path, result)
    write_json(
        output_dir / f"course_objects_{session_id}.geojson",
        {"type": "FeatureCollection", "features": features},
    )

    gps_count = sum(item["coordinate_access"] == "gps_available" for item in objects)
    print(f"Found {len(objects)} course object(s) in session {session_id}.")
    print(f"Objects with API-accessible GPS: {gps_count}")
    print(f"Course metadata: {json_path}")
    return 0 if objects else 1


def main() -> int:
    args = parse_args()
    token = os.getenv("SAILSYNC_API_TOKEN")
    if not token:
        print(
            "Missing SAILSYNC_API_TOKEN. Export it in your shell or secret manager; "
            "do not add it to source control.",
            file=sys.stderr,
        )
        return 2

    client = SailSyncClient(token, args.base_url)
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        account = client.account()
        write_json(output_dir / "account_capabilities.json", account)

        if args.session_id:
            if not args.course_only:
                raise SailSyncError("--session-id currently requires --course-only")
            return export_course_objects(client, args.session_id, output_dir)

        if args.course_only:
            raise SailSyncError("--course-only requires --session-id")

        if args.event_id:
            events = [{"id": args.event_id, "title": f"Event {args.event_id}"}]
        else:
            events = client.events(
                args.query,
                args.boat_class,
                args.date_from,
                args.date_to,
            )
        write_json(output_dir / "events.json", events)

        if not events:
            print(
                "No matching SailSync event was found. This means the catalog search "
                "returned no event; it does not prove that the regatta had no trackers."
            )
            return 1

        if args.discover_only:
            print(f"Found {len(events)} matching event(s):")
            for event in events:
                print(
                    f"  {event.get('id')}: {event.get('title', 'Untitled')} "
                    f"({event.get('starts_on', '?')} to {event.get('ends_on', '?')})"
                )
            print(f"Saved catalog response: {output_dir / 'events.json'}")
            return 0

        report: dict[str, Any] = {
            "query": vars(args) | {"output_dir": str(output_dir)},
            "events": [],
        }
        geojson_features: list[dict[str, Any]] = []

        for event in events:
            event_id = int(event["id"])
            sessions = matching_sessions(
                client.event_sessions(event_id),
                args.boat_class,
            )
            event_report: dict[str, Any] = {
                "event": event,
                "matching_sessions": [],
            }
            report["events"].append(event_report)

            for assignment in sessions:
                assignment_id = int(assignment["assignment_id"])
                access = client.resolve_day(event_id, assignment_id)
                session_report: dict[str, Any] = {
                    "assignment": assignment,
                    "access": access,
                    "tracks": [],
                }
                event_report["matching_sessions"].append(session_report)
                if not access.get("allowed"):
                    continue

                session_id = int(access.get("session_id") or assignment["session_id"])
                session_meta, tracks = client.tracks(session_id)
                session_report["session"] = session_meta
                boat_tracks = [
                    track
                    for track in tracks
                    if track.get("type") == "boat" and track.get("gps_path")
                ]
                if not args.download:
                    boat_tracks = boat_tracks[: max(args.max_tracks_per_session, 0)]

                for track in boat_tracks:
                    track_id = int(track["session_track_id"])
                    points: list[dict[str, Any]] = []
                    first_page: dict[str, Any] | None = None
                    track_error: str | None = None
                    try:
                        for page in client.gps_pages(
                            session_id,
                            track_id,
                            limit=5000 if args.download else 1,
                        ):
                            first_page = first_page or page
                            points.extend(
                                point
                                for point in page.get("points", [])
                                if isinstance(point, dict)
                            )
                            if not args.download:
                                break
                    except SailSyncError as error:
                        # A live, changed, or unsupported source can be unavailable
                        # while other tracks in the same session remain readable.
                        track_error = str(error)

                    track_report = {
                        "session_track_id": track_id,
                        "name": track.get("name"),
                        "available": first_page.get("available") if first_page else False,
                        "error": track_error,
                        "reported_point_count": (
                            first_page.get("point_count") if first_page else None
                        ),
                        **summarize_points(points),
                    }
                    session_report["tracks"].append(track_report)

                    if args.download and points:
                        stem = safe_name(f"{session_id}_{track_id}_{track.get('name', 'boat')}")
                        write_track_csv(output_dir / f"{stem}.csv", points)
                        geometry = geojson_geometry(points)
                        if geometry:
                            geojson_features.append(
                                {
                                    "type": "Feature",
                                    "geometry": geometry,
                                    "properties": {
                                        "event_id": event_id,
                                        "session_id": session_id,
                                        "track_id": track_id,
                                        "name": track.get("name"),
                                        **track_report,
                                    },
                                }
                            )

        write_json(output_dir / "probe_report.json", report)
        if args.download:
            write_json(
                output_dir / "trajectories.geojson",
                {"type": "FeatureCollection", "features": geojson_features},
            )

        track_reports = [
            track
            for event in report["events"]
            for session in event["matching_sessions"]
            for track in session["tracks"]
        ]
        near_la = sum(bool(track["near_los_angeles"]) for track in track_reports)
        print(f"Found {len(events)} event(s) and probed {len(track_reports)} boat track(s).")
        print(f"Tracks with a sampled/full position within {LA_RADIUS_KM:g} km of San Pedro: {near_la}")
        print(f"Report: {output_dir / 'probe_report.json'}")
        if args.download:
            print(f"GeoJSON: {output_dir / 'trajectories.geojson'}")
        return 0 if track_reports else 1
    except SailSyncError as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
