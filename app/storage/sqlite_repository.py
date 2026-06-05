from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from app.context.meeting_context import GeneratedQuestions, MeetingContext


class SQLiteRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_meeting(self, topic: str | None) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "insert into meetings (topic, started_at, status) values (?, ?, ?)",
                (topic or "", _now_iso(), "running"),
            )
            return int(cursor.lastrowid)

    def finish_meeting(self, meeting_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "update meetings set ended_at = ?, status = ? where id = ?",
                (_now_iso(), "finished", meeting_id),
            )

    def add_transcription(self, meeting_id: int, text: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "insert into transcriptions (meeting_id, created_at, text) values (?, ?, ?)",
                (meeting_id, _now_iso(), text),
            )

    def save_context_snapshot(self, meeting_id: int, context: MeetingContext) -> None:
        with self._connect() as connection:
            connection.execute(
                "insert into context_snapshots (meeting_id, created_at, context_json) values (?, ?, ?)",
                (meeting_id, _now_iso(), context.model_dump_json()),
            )

    def get_recent_context_snapshots(self, meeting_id: int, limit: int) -> list[MeetingContext]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                select context_json
                from context_snapshots
                where meeting_id = ?
                order by id desc
                limit ?
                """,
                (meeting_id, limit),
            ).fetchall()

        contexts: list[MeetingContext] = []
        for (context_json,) in reversed(rows):
            contexts.append(MeetingContext.model_validate_json(context_json))
        return contexts

    def save_generated_questions(self, meeting_id: int, questions: GeneratedQuestions) -> None:
        with self._connect() as connection:
            connection.execute(
                "insert into generated_questions (meeting_id, created_at, questions_json) values (?, ?, ?)",
                (meeting_id, _now_iso(), questions.model_dump_json()),
            )

    def save_summary(self, meeting_id: int, markdown: str, file_path: Path) -> None:
        with self._connect() as connection:
            connection.execute(
                "insert into summaries (meeting_id, created_at, markdown, file_path) values (?, ?, ?, ?)",
                (meeting_id, _now_iso(), markdown, str(file_path)),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path)
        try:
            connection.execute("pragma foreign_keys = on")
            connection.execute("pragma journal_mode = memory")
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                create table if not exists meetings (
                    id integer primary key autoincrement,
                    topic text not null default '',
                    started_at text not null,
                    ended_at text,
                    status text not null
                );

                create table if not exists transcriptions (
                    id integer primary key autoincrement,
                    meeting_id integer not null,
                    created_at text not null,
                    text text not null,
                    foreign key (meeting_id) references meetings(id)
                );

                create table if not exists context_snapshots (
                    id integer primary key autoincrement,
                    meeting_id integer not null,
                    created_at text not null,
                    context_json text not null,
                    foreign key (meeting_id) references meetings(id)
                );

                create table if not exists generated_questions (
                    id integer primary key autoincrement,
                    meeting_id integer not null,
                    created_at text not null,
                    questions_json text not null,
                    foreign key (meeting_id) references meetings(id)
                );

                create table if not exists summaries (
                    id integer primary key autoincrement,
                    meeting_id integer not null,
                    created_at text not null,
                    markdown text not null,
                    file_path text not null,
                    foreign key (meeting_id) references meetings(id)
                );
                """
            )


def write_summary_file(summaries_dir: Path, meeting_id: int, markdown: str) -> Path:
    summaries_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = summaries_dir / f"meeting_{meeting_id}_{timestamp}.md"
    summary_path.write_text(markdown, encoding="utf-8")
    return summary_path


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
