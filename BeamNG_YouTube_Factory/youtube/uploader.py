"""Загрузка на YouTube через официальный YouTube Data API v3 (OAuth 2.0, после авторизации пользователя).

Нужен client_secret.json из Google Cloud Console (проект с включённым YouTube Data API v3, тип OAuth «Приложение для ПК»).
Квота API: загрузка видео стоит ~1600 единиц из 10 000 в сутки. Непроверенные API-проекты могут публиковать
только приватные видео — это ограничение YouTube, а не программы.
"""
from pathlib import Path

from core.logger import get_logger

log = get_logger("youtube")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeError(Exception):
    pass


def build_body(meta: dict, privacy="private", category="20", language="ru") -> dict:
    return {
        "snippet": {"title": meta["title"][:100], "description": meta["description"][:5000],
                    "tags": [t.lstrip("#") for t in (meta.get("tags", []) + meta.get("hashtags", []))][:30],
                    "categoryId": str(category), "defaultLanguage": language},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }


def get_credentials(client_secret: Path, token: Path):
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise YouTubeError("Не установлены пакеты Google: pip install google-api-python-client google-auth-oauthlib")
    creds = None
    if token.exists():
        creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not client_secret.exists():
            raise YouTubeError(f"Нет файла {client_secret}. Создайте OAuth-клиент в Google Cloud Console и сохраните JSON сюда.")
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
        creds = flow.run_local_server(port=0)     # откроется браузер: пользователь входит и разрешает доступ
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(creds.to_json(), encoding="utf-8")
    return creds


def upload(video: Path, meta: dict, settings, progress=None) -> str:
    root = Path(__file__).resolve().parent.parent
    cs = Path(settings.get("youtube.client_secret"))
    tk = Path(settings.get("youtube.token"))
    cs = cs if cs.is_absolute() else root / cs
    tk = tk if tk.is_absolute() else root / tk
    creds = get_credentials(cs, tk)
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    body = build_body(meta, settings.get("youtube.privacy", "private"), settings.get("youtube.category_id", "20"),
                      settings.get("youtube.language", "ru"))
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status and progress:
            progress(status.progress())
    vid = resp["id"]
    log.info("загружено на YouTube: https://youtu.be/%s (приватность: %s)", vid, body["status"]["privacyStatus"])
    return vid
