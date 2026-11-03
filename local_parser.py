# noqa: SIZE_OK
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from strict_json import loads


class LocalImportError(ValueError):
    pass


def validate_manifest(manifest: Any, manifest_path: Path, source_id: str) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict) or manifest.get("status") != "PASS":
        raise LocalImportError(f"invalid local manifest: {manifest_path}")
    if manifest.get("instance_id") != source_id:
        raise LocalImportError(f"manifest instance does not match source directory: {manifest_path}")
    if not isinstance(manifest.get("run_id"), str) or not manifest["run_id"]:
        raise LocalImportError(f"manifest run_id is missing or invalid: {manifest_path}")
    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        raise LocalImportError(f"manifest counts are missing: {manifest_path}")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise LocalImportError(f"manifest artifacts are missing: {manifest_path}")
    expected_counts = {"artifacts": len(artifacts), "jsonl": 0, "sqlite": 0}
    for artifact in artifacts:
        if not isinstance(artifact, dict) or artifact.get("kind") not in {"jsonl", "sqlite"}:
            raise LocalImportError(f"invalid artifact entry: {manifest_path}")
        kind = artifact["kind"]
        expected_counts[kind] += 1
        if not isinstance(artifact.get("source_relative_path"), str) or not artifact["source_relative_path"]:
            raise LocalImportError(f"artifact source path is missing: {manifest_path}")
        if not isinstance(artifact.get("destination_relative_path"), str) or not artifact["destination_relative_path"]:
            raise LocalImportError(f"artifact archive path is missing: {manifest_path}")
        if not isinstance(artifact.get("captured_bytes"), int) or artifact["captured_bytes"] < 0:
            raise LocalImportError(f"artifact byte count is invalid: {manifest_path}")
        digest = artifact.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise LocalImportError(f"artifact hash is invalid: {manifest_path}")
        if "records" in artifact and (not isinstance(artifact["records"], int) or artifact["records"] < 0):
            raise LocalImportError(f"artifact record count is invalid: {manifest_path}")
    for key, expected in expected_counts.items():
        if not isinstance(counts.get(key), int) or counts[key] != expected:
            raise LocalImportError(f"manifest {key} count is invalid: {manifest_path}")
    return artifacts


@dataclass(frozen=True, slots=True)
class SessionOccurrence:
    session_id: str
    line_number: int
    cwd: str | None
    origin: str | None


@dataclass(frozen=True, slots=True)
class MessageOccurrence:
    session_id: str
    message_key: str
    explicit_id: bool
    role: str
    text: str
    timestamp_utc: str
    line_number: int
    text_sha256: str
    variant_sha256: str


@dataclass(frozen=True, slots=True)
class ParsedArtifact:
    parser_status: str
    admission_status: str
    reason_code: str | None
    observed_record_count: int | None
    sessions: tuple[SessionOccurrence, ...]
    messages: tuple[MessageOccurrence, ...]
    skipped_content_parts: int = 0


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise LocalImportError(f"missing {field}")
    return value


def _message_text(payload: dict[str, Any], content_profile: str = "legacy") -> str:
    content = payload.get("content")
    if not isinstance(content, list):
        if content_profile == "codex":
            raise LocalImportError("typed message content must be an array")
        return ""
    text: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            if content_profile == "codex":
                raise LocalImportError("typed content item must be an object")
            continue
        if content_profile == "codex" and item.get("type") not in ("input_text", "output_text"):
            continue
        value = item.get("text")
        if content_profile == "codex" and not isinstance(value, str):
            raise LocalImportError("typed text content requires a string")
        if isinstance(value, str):
            text.append(value)
    joined = "\n".join(text)
    return joined if content_profile == "codex" and joined.strip() else joined.strip()


def _records(path: Path) -> list[tuple[int, dict[str, Any]]]:
    records: list[tuple[int, dict[str, Any]]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        if line.endswith("\r"):
            line = line[:-1]
        if not line.strip():
            continue
        try:
            value = loads(line)
        except ValueError as error:
            raise LocalImportError(f"invalid JSONL record: {path}:{line_number}") from error
        if not isinstance(value, dict):
            raise LocalImportError(f"JSONL record is not an object: {path}:{line_number}")
        records.append((line_number, value))
    return records


def parse_artifact(path: Path, source_relative_path: str, artifact_kind: str = "jsonl",
                   content_profile: str = "legacy") -> ParsedArtifact:
    if content_profile not in ("legacy", "codex"):
        raise LocalImportError("unsupported local content profile")
    if artifact_kind == "sqlite":
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                f"{path.resolve().as_uri()}?mode=ro&immutable=1", uri=True,
            )
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise LocalImportError(f"SQLite integrity check failed: {path}")
            if list(connection.execute("PRAGMA foreign_key_check")):
                raise LocalImportError(f"SQLite foreign-key check failed: {path}")
        except sqlite3.Error as error:
            raise LocalImportError(f"invalid SQLite artifact: {path}") from error
        finally:
            if connection is not None:
                connection.close()
        return ParsedArtifact("not_applicable", "accepted_metadata_only", "sqlite_backup", None, (), ())
    if artifact_kind != "jsonl":
        raise LocalImportError(f"unsupported local artifact kind: {artifact_kind}")
    records = _records(path)
    if re.fullmatch(r"agents/(claude|antigravity|opencode)/raw/.+", source_relative_path):
        return ParsedArtifact("parsed", "accepted_metadata_only", "agent_raw_evidence", len(records), (), ())
    if source_relative_path == "session_index.jsonl":
        for line_number, value in records:
            if not all(isinstance(value.get(key), str) and value[key] for key in ("id", "thread_name", "updated_at")):
                raise LocalImportError(f"invalid session index metadata: {path}:{line_number}")
        return ParsedArtifact("parsed", "accepted_metadata_only", "session_index_metadata", len(records), (), ())

    sessions: list[SessionOccurrence] = []
    messages: list[MessageOccurrence] = []
    current_session = ""
    skipped_content_parts = 0
    for line_number, value in records:
        record_type = value.get("type")
        payload = value.get("payload")
        if record_type == "session_meta" and isinstance(payload, dict):
            session_id = _text(payload.get("id") or payload.get("session_id"), "session id")
            sessions.append(SessionOccurrence(session_id, line_number, payload.get("cwd"), payload.get("originator")))
            current_session = session_id
            continue
        if record_type != "response_item" or not isinstance(payload, dict) or payload.get("type") != "message":
            continue
        role = payload.get("role")
        if role not in {"user", "assistant"}:
            continue
        text = _message_text(payload, content_profile)
        if content_profile == "codex":
            skipped_content_parts += sum(item.get("type") not in ("input_text", "output_text")
                                         for item in payload["content"])
        if not text:
            continue
        if not current_session:
            raise LocalImportError(f"JSONL message has no session metadata: {path}:{line_number}")
        raw_key = payload.get("id")
        explicit_id = isinstance(raw_key, str) and bool(raw_key)
        message_key = raw_key if explicit_id else f"{source_relative_path}:{line_number}"
        variant_sha256 = hashlib.sha256(json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        ).encode("ascii")).hexdigest()
        messages.append(MessageOccurrence(
            current_session, str(message_key), explicit_id, role, text,
            str(value.get("timestamp") or ""), line_number,
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
            variant_sha256,
        ))
    if not sessions:
        raise LocalImportError(f"JSONL has no session metadata: {path}")
    status = "imported" if messages else "accepted_zero_message"
    reason = None if messages else "no_response_messages"
    return ParsedArtifact("parsed", status, reason, len(records), tuple(sessions), tuple(messages), skipped_content_parts)


def message_decisions(
    artifact_rows: list[tuple[str, dict[str, Any], Path, ParsedArtifact]],
) -> list[tuple[MessageOccurrence, str, dict[str, Any], Path, str]]:
    groups: dict[tuple[str, str], list[tuple[MessageOccurrence, dict[str, Any], Path, str]]] = {}
    decisions: list[tuple[MessageOccurrence, str, dict[str, Any], Path, str]] = []
    for source_id, artifact, path, parsed in artifact_rows:
        relative = str(artifact["source_relative_path"])
        for message in parsed.messages:
            key = (message.session_id, message.message_key) if message.explicit_id else (message.session_id, f"{relative}:{message.line_number}")
            groups.setdefault(key, []).append((message, artifact, path, relative))
    for (session_id, message_key), rows in groups.items():
        signatures = {(row.role, row.text_sha256) for row, _, _, _ in rows}
        if len(signatures) > 1:
            raise LocalImportError(f"conflicting explicit message identity: {session_id}:{message_key}")
        variants: dict[str, list[tuple[MessageOccurrence, dict[str, Any], Path, str]]] = {}
        for row in rows:
            variants.setdefault(row[0].variant_sha256, []).append(row)
        multi_variant = len(variants) > 1 and rows[0][0].explicit_id
        for variant, variant_rows in sorted(variants.items()):
            variant_rows.sort(key=lambda item: (item[3], item[0].line_number, str(item[1]["sha256"])))
            canonical_key = message_key if not multi_variant else f"{message_key}@{variant}"
            for index, row in enumerate(variant_rows):
                status = "selected" if index == 0 else "duplicate"
                decisions.append((row[0], status, row[1], row[2], canonical_key))
    return decisions


def ensure_local_schema(connection: sqlite3.Connection) -> None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(local_source_files)")}
    additions = {
        "admission_status": "TEXT NOT NULL DEFAULT 'imported'",
        "parser_status": "TEXT NOT NULL DEFAULT 'parsed'",
        "manifest_record_count": "INTEGER",
        "observed_record_count": "INTEGER",
        "session_count": "INTEGER NOT NULL DEFAULT 0",
        "message_count": "INTEGER NOT NULL DEFAULT 0",
        "reason_code": "TEXT",
    }
    for name, definition in additions.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE local_source_files ADD COLUMN {name} {definition}")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS local_occurrences (
            occurrence_pk INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            snapshot_run_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            source_relative_path TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            occurrence_kind TEXT NOT NULL CHECK(occurrence_kind IN ('session', 'message')),
            message_key TEXT NOT NULL,
            variant_sha256 TEXT,
            line_number INTEGER NOT NULL,
            role TEXT,
            timestamp_utc TEXT,
            text_sha256 TEXT,
            occurrence_status TEXT NOT NULL CHECK(occurrence_status IN ('selected', 'duplicate', 'unresolved')),
            occurrence_reason TEXT,
            canonical_local_message_pk INTEGER,
            FOREIGN KEY(source_id) REFERENCES local_sources(source_id) ON DELETE CASCADE,
            FOREIGN KEY(source_id, source_relative_path)
                REFERENCES local_source_files(source_id, source_relative_path) ON DELETE CASCADE,
            FOREIGN KEY(canonical_local_message_pk)
                REFERENCES local_messages(local_message_pk) ON DELETE SET NULL,
            UNIQUE(source_id, snapshot_run_id, occurrence_kind, source_relative_path,
                   source_sha256, session_id, message_key, line_number)
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS idx_local_occurrences_session ON local_occurrences(source_id, snapshot_run_id, session_id, occurrence_kind)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_local_occurrences_message ON local_occurrences(source_id, snapshot_run_id, message_key, occurrence_status)")
    # Foreign-key children need their own index: without it every deleted local message scanned all
    # occurrences (a nightly re-ingest spent ~6 minutes there).
    connection.execute("CREATE INDEX IF NOT EXISTS idx_local_occurrences_canonical ON local_occurrences(canonical_local_message_pk)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_local_occurrences_file ON local_occurrences(source_id, source_relative_path)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_local_sessions_file ON local_sessions(source_id, source_relative_path)")


def derived_state_complete(
    connection: sqlite3.Connection,
    source_id: str,
    manifest_run: str,
    manifest_relative: str,
    manifest_sha: str,
    session_rows: list[tuple[SessionOccurrence, dict[str, Any], Path]],
    selected_sessions: dict[str, tuple[SessionOccurrence, dict[str, Any], Path]],
    message_rows: list[tuple[MessageOccurrence, str, dict[str, Any], Path, str]],
) -> bool:
    snapshot = connection.execute(
        "SELECT status,manifest_path,manifest_sha256 FROM local_snapshots WHERE source_id=? AND run_id=?",
        (source_id, manifest_run),
    ).fetchone()
    if snapshot != ("PASS", manifest_relative, manifest_sha):
        return False
    expected_sessions = set(selected_sessions)
    actual_sessions = {row[0] for row in connection.execute(
        "SELECT session_id FROM local_sessions WHERE source_id=?", (source_id,)
    )}
    if actual_sessions != expected_sessions:
        return False
    selected_messages = [row for row in message_rows if row[1] == "selected"]
    expected_message_values = {
        (message.session_id, canonical_key, str(artifact["source_relative_path"]), str(artifact["sha256"]),
         message.line_number, message.timestamp_utc, message.role, message.text)
        for message, _, artifact, _, canonical_key in selected_messages
    }
    actual_message_values = set(connection.execute(
        """SELECT session_id,message_key,source_relative_path,source_sha256,line_number,
                  timestamp_utc,role,text FROM local_messages WHERE source_id=?""", (source_id,)
    ))
    if actual_message_values != expected_message_values:
        return False
    expected_session_occurrences = len(session_rows)
    expected_message_occurrences = len(message_rows)
    session_occurrences, message_occurrences = connection.execute(
        """SELECT
             SUM(occurrence_kind='session'), SUM(occurrence_kind='message')
           FROM local_occurrences WHERE source_id=? AND snapshot_run_id=?""",
        (source_id, manifest_run),
    ).fetchone()
    if (session_occurrences or 0, message_occurrences or 0) != (expected_session_occurrences, expected_message_occurrences):
        return False
    selected_count, duplicate_count, mapped_count = connection.execute(
        """SELECT
             SUM(occurrence_status='selected' AND occurrence_kind='message'),
             SUM(occurrence_status='duplicate' AND occurrence_kind='message'),
             SUM(occurrence_kind='message' AND canonical_local_message_pk IS NOT NULL)
           FROM local_occurrences WHERE source_id=? AND snapshot_run_id=?""",
        (source_id, manifest_run),
    ).fetchone()
    expected_duplicate_count = sum(row[1] == "duplicate" for row in message_rows)
    if (selected_count or 0, duplicate_count or 0, mapped_count or 0) != (
        len(selected_messages), expected_duplicate_count, len(message_rows),
    ):
        return False
    return True

