"""SQLite: проекты, сцены/дубли, готовые видео, журнал."""
import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects(
  id TEXT PRIMARY KEY, title TEXT, script TEXT, status TEXT, created REAL, updated REAL,
  request TEXT, plan TEXT, folder TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS takes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, scene_id INTEGER, idx INTEGER,
  video TEXT, ok INTEGER, data TEXT);
CREATE TABLE IF NOT EXISTS videos(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, path TEXT, kind TEXT, duration REAL,
  created REAL, meta TEXT, youtube_id TEXT);
CREATE TABLE IF NOT EXISTS log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, ts REAL, level TEXT, message TEXT);
"""


class Database:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def _x(self, sql, args=()):
        with self._lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur

    def create_project(self, pid, title, script, request: dict, folder):
        now = time.time()
        self._x("INSERT OR REPLACE INTO projects(id,title,script,status,created,updated,request,folder) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (pid, title, script, "created", now, now, json.dumps(request, ensure_ascii=False), str(folder)))

    def update_project(self, pid, **fields):
        if not fields:
            return
        if "plan" in fields and not isinstance(fields["plan"], str):
            fields["plan"] = json.dumps(fields["plan"], ensure_ascii=False)
        fields["updated"] = time.time()
        cols = ", ".join(f"{k}=?" for k in fields)
        self._x(f"UPDATE projects SET {cols} WHERE id=?", (*fields.values(), pid))

    def get_project(self, pid):
        r = self._x("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None

    def list_projects(self, limit=200):
        return [dict(r) for r in self._x("SELECT * FROM projects ORDER BY created DESC LIMIT ?", (limit,))]

    def save_take(self, pid, take):
        self._x("DELETE FROM takes WHERE project_id=? AND scene_id=? AND idx=?", (pid, take.scene_id, take.index))
        self._x("INSERT INTO takes(project_id,scene_id,idx,video,ok,data) VALUES(?,?,?,?,?,?)",
                (pid, take.scene_id, take.index, take.video, int(take.ok), json.dumps(take.to_dict(), ensure_ascii=False)))

    def list_takes(self, pid):
        return [json.loads(r["data"]) for r in
                self._x("SELECT data FROM takes WHERE project_id=? ORDER BY scene_id, idx", (pid,))]

    def add_video(self, pid, path, kind, duration=0.0, meta=None):
        cur = self._x("INSERT INTO videos(project_id,path,kind,duration,created,meta) VALUES(?,?,?,?,?,?)",
                      (pid, str(path), kind, duration, time.time(), json.dumps(meta or {}, ensure_ascii=False)))
        return cur.lastrowid

    def list_videos(self, pid=None):
        if pid:
            rows = self._x("SELECT * FROM videos WHERE project_id=? ORDER BY created DESC", (pid,))
        else:
            rows = self._x("SELECT * FROM videos ORDER BY created DESC")
        return [dict(r) for r in rows]

    def set_youtube_id(self, video_id, yt):
        self._x("UPDATE videos SET youtube_id=? WHERE id=?", (yt, video_id))

    def log(self, pid, level, message):
        self._x("INSERT INTO log(project_id,ts,level,message) VALUES(?,?,?,?)", (pid, time.time(), level, message))

    def get_log(self, pid):
        return [dict(r) for r in self._x("SELECT * FROM log WHERE project_id=? ORDER BY id", (pid,))]
