from __future__ import annotations

import json
import os
import uuid
from fractions import Fraction
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import hmac
from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError
from flask import Flask, flash, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
THUMBNAIL_DIR = BASE_DIR / "thumbnails"
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "photos.json"
VISITORS_FILE = DATA_DIR / "visitors.json"
FONT_DIR = Path(os.environ.get("PHOTO_FONT_DIR", "/root/resource/font"))
LOGO_DIR = Path("/root/resource/logo")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_SESSION_KEY = "admin_authenticated"
ADMIN_LOGIN_METHOD_KEY = "admin_login_method"
ADMIN_GITHUB_LOGIN_KEY = "admin_github_login"
ADMIN_GITHUB_NAME_KEY = "admin_github_name"
ADMIN_GITHUB_AVATAR_KEY = "admin_github_avatar"
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "").strip()
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "").strip()
GITHUB_ALLOWED_USERS = {
    user.strip().lower()
    for user in os.environ.get("GITHUB_ALLOWED_USERS", "").split(",")
    if user.strip()
}
GITHUB_CALLBACK_URL = os.environ.get("GITHUB_CALLBACK_URL", "").strip()
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_USER_URL = "https://api.github.com/user"
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "avif", "bmp"}
THUMBNAIL_MAX_SIZE = (1200, 1200)
THUMBNAIL_QUALITY = 82
THUMBNAIL_VERSION = 2
EXIF_MAKE_TAG = 271
EXIF_CREATE_DATE_TAG = 36868
EXIF_DATE_TIME_ORIGINAL_TAG = 36867
EXIF_CAMERA_MODEL_TAG = 272
EXIF_LENS_MAKE_TAG = 42035
EXIF_LENS_MODEL_TAG = 42036
EXIF_FOCAL_LENGTH_35MM_TAG = 41989
EXIF_F_NUMBER_TAG = 33437
EXIF_EXPOSURE_TIME_TAG = 33434
EXIF_SHUTTER_SPEED_VALUE_TAG = 37377
EXIF_ISO_TAGS = (34855, 34864)
MAX_CONTENT_LENGTH = 30 * 1024 * 1024

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "photo-timeline-dev")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def ensure_storage() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        DATA_FILE.write_text("[]", encoding="utf-8")


ensure_storage()


def load_visitors() -> dict[str, list[str]]:
    try:
        data = json.loads(VISITORS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_visitors(data: dict[str, list[str]]) -> None:
    VISITORS_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def get_today_visitors() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    data = load_visitors()
    return len(data.get(today, []))


def record_visitor(ip_address: str) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    data = load_visitors()
    today_ips = data.get(today, [])
    if ip_address not in today_ips:
        today_ips.append(ip_address)
        data[today] = today_ips
        save_visitors(data)


def safe_next_url(raw_value: str | None, fallback: str) -> str:
    if raw_value and raw_value.startswith("/") and not raw_value.startswith("//"):
        return raw_value

    return fallback


def is_admin_authenticated() -> bool:
    return bool(session.get(ADMIN_SESSION_KEY))


def authenticate_admin(
    login_method: str = "password",
    github_login: str | None = None,
    github_name: str | None = None,
    github_avatar: str | None = None,
) -> None:
    session[ADMIN_SESSION_KEY] = True
    session.permanent = True
    session[ADMIN_LOGIN_METHOD_KEY] = login_method

    if github_login:
        session[ADMIN_GITHUB_LOGIN_KEY] = github_login
    else:
        session.pop(ADMIN_GITHUB_LOGIN_KEY, None)

    if github_name:
        session[ADMIN_GITHUB_NAME_KEY] = github_name
    else:
        session.pop(ADMIN_GITHUB_NAME_KEY, None)

    if github_avatar:
        session[ADMIN_GITHUB_AVATAR_KEY] = github_avatar
    else:
        session.pop(ADMIN_GITHUB_AVATAR_KEY, None)


def logout_admin() -> None:
    session.pop(ADMIN_SESSION_KEY, None)
    session.pop(ADMIN_LOGIN_METHOD_KEY, None)
    session.pop(ADMIN_GITHUB_LOGIN_KEY, None)
    session.pop(ADMIN_GITHUB_NAME_KEY, None)
    session.pop(ADMIN_GITHUB_AVATAR_KEY, None)


def is_github_login_configured() -> bool:
    return bool(GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET and GITHUB_ALLOWED_USERS)


def get_github_callback_url() -> str:
    if GITHUB_CALLBACK_URL:
        return GITHUB_CALLBACK_URL

    return url_for("admin_github_callback", _external=True)


def build_github_authorize_url(state: str) -> str:
    query = urlencode(
        {
            "client_id": GITHUB_CLIENT_ID,
            "redirect_uri": get_github_callback_url(),
            "scope": "read:user",
            "state": state,
            "allow_signup": "false",
        }
    )
    return f"{GITHUB_AUTHORIZE_URL}?{query}"


def github_request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
) -> dict[str, Any] | None:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "photo-timeline-site",
    }
    if headers:
        request_headers.update(headers)

    request = Request(url, data=data, headers=request_headers, method=method)

    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None

    if isinstance(payload, dict):
        return payload

    return None


def exchange_github_code_for_token(code: str) -> str | None:
    payload = github_request_json(
        GITHUB_TOKEN_URL,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=urlencode(
            {
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": get_github_callback_url(),
            }
        ).encode("utf-8"),
    )
    if not payload:
        return None

    access_token = payload.get("access_token")
    if isinstance(access_token, str) and access_token:
        return access_token

    return None


def fetch_github_user(access_token: str) -> dict[str, Any] | None:
    return github_request_json(
        GITHUB_API_USER_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )


def is_allowed_github_user(login: str) -> bool:
    return login.strip().lower() in GITHUB_ALLOWED_USERS


def parse_datetime_input(raw_value: str | None) -> datetime:
    if not raw_value:
        return datetime.now()

    try:
        return datetime.fromisoformat(raw_value)
    except ValueError:
        return datetime.now()


def parse_optional_datetime_input(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None

    try:
        return datetime.fromisoformat(raw_value)
    except ValueError:
        return None


def format_datetime_local(value: str | None) -> str:
    if not value:
        return ""

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return ""

    return parsed.strftime("%Y-%m-%dT%H:%M")


def format_datetime(value: str | None, fallback: str = "暂无") -> str:
    if not value:
        return fallback

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return fallback

    return parsed.strftime("%Y.%m.%d %H:%M")


def sort_photos(photos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        photos,
        key=lambda item: (
            item.get("captured_at", ""),
            item.get("uploaded_at", ""),
            item.get("id", ""),
        ),
        reverse=True,
    )


def load_photos() -> list[dict[str, Any]]:
    ensure_storage()

    try:
        raw_items = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(raw_items, list):
        return []

    photos = [item for item in raw_items if isinstance(item, dict) and item.get("filename")]

    migrated = False
    for photo in photos:
        if ensure_thumbnail_asset(photo):
            migrated = True
        if ensure_photo_details(photo):
            migrated = True

    if migrated:
        save_photos(photos)

    return sort_photos(photos)


def save_photos(photos: list[dict[str, Any]]) -> None:
    ensure_storage()

    temp_file = DATA_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(sort_photos(photos), ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(DATA_FILE)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_exif_datetime(raw_value: Any) -> datetime | None:
    if raw_value is None:
        return None

    if isinstance(raw_value, bytes):
        raw_value = raw_value.decode("utf-8", errors="ignore")

    cleaned_value = str(raw_value).strip().replace("\x00", "")
    if not cleaned_value:
        return None

    for pattern in ("%Y:%m:%d %H:%M:%S", "%Y:%m:%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(cleaned_value, pattern)
        except ValueError:
            continue

    return None


def normalize_exif_text(raw_value: Any) -> str:
    if raw_value is None:
        return ""

    if isinstance(raw_value, bytes):
        raw_value = raw_value.decode("utf-8", errors="ignore")

    normalized_value = str(raw_value).replace("\x00", " ").strip()
    return " ".join(normalized_value.split())


def normalize_form_text(raw_value: Any) -> str:
    if raw_value is None:
        return ""

    if isinstance(raw_value, bytes):
        raw_value = raw_value.decode("utf-8", errors="ignore")

    return str(raw_value).replace("\x00", "").strip()


def get_exif_ifd(exif: Any) -> Any:
    try:
        exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)
    except (AttributeError, KeyError, TypeError, ValueError):
        return {}

    return exif_ifd or {}


def get_exif_value(exif: Any, exif_ifd: Any, tag: int) -> Any:
    if exif_ifd:
        try:
            value = exif_ifd.get(tag)
        except AttributeError:
            value = None
        if value is not None:
            return value

    try:
        return exif.get(tag)
    except AttributeError:
        return None


def merge_exif_text(primary_value: Any, secondary_value: Any) -> str:
    primary_text = normalize_exif_text(primary_value)
    secondary_text = normalize_exif_text(secondary_value)

    if primary_text and secondary_text:
        primary_lower = primary_text.casefold()
        secondary_lower = secondary_text.casefold()
        if primary_lower in secondary_lower:
            return secondary_text
        if secondary_lower in primary_lower:
            return primary_text
        return f"{primary_text} {secondary_text}"

    return secondary_text or primary_text


def exif_to_float(raw_value: Any) -> float | None:
    if raw_value is None:
        return None

    if isinstance(raw_value, tuple) and len(raw_value) == 2:
        numerator, denominator = raw_value
        try:
            denominator_value = float(denominator)
            if denominator_value == 0:
                return None

            return float(numerator) / denominator_value
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def format_aperture(raw_value: Any) -> str:
    numeric_value = exif_to_float(raw_value)
    if numeric_value is None:
        return ""

    formatted_value = f"{numeric_value:.1f}".rstrip("0").rstrip(".")
    return f"f/{formatted_value}"


def format_shutter_speed(raw_value: Any) -> str:
    numeric_value = exif_to_float(raw_value)
    if numeric_value is None or numeric_value <= 0:
        return ""

    if numeric_value >= 1:
        formatted_value = f"{numeric_value:.1f}".rstrip("0").rstrip(".")
        return f"{formatted_value} s"

    reciprocal_fraction = Fraction(numeric_value).limit_denominator(10000)
    if reciprocal_fraction.numerator == 1:
        return f"1/{reciprocal_fraction.denominator} s"

    formatted_value = f"{numeric_value:.2f}".rstrip("0").rstrip(".")
    return f"{formatted_value} s"


def format_iso(raw_value: Any) -> str:
    numeric_value = exif_to_float(raw_value)
    if numeric_value is None:
        return ""

    return str(int(round(numeric_value)))


def format_focal_length_35mm(raw_value: Any) -> str:
    numeric_value = exif_to_float(raw_value)
    if numeric_value is None:
        return ""

    return f"{int(round(numeric_value))} mm"


def extract_exif_metadata(image_path: Path, upload_time: datetime) -> dict[str, Any]:
    metadata = {
        "captured_at": upload_time,
        "captured_at_source": "upload",
        "camera_model": "",
        "lens_model": "",
        "focal_length_35mm": "",
        "aperture": "",
        "shutter_speed": "",
        "iso": "",
    }

    try:
        with Image.open(image_path) as image:
            exif = image.getexif()
            if not exif:
                return metadata

            exif_ifd = get_exif_ifd(exif)

            create_date = parse_exif_datetime(get_exif_value(exif, exif_ifd, EXIF_CREATE_DATE_TAG))
            if create_date is None:
                create_date = parse_exif_datetime(get_exif_value(exif, exif_ifd, EXIF_DATE_TIME_ORIGINAL_TAG))

            if create_date is not None:
                metadata["captured_at"] = create_date
                metadata["captured_at_source"] = "exif"

            metadata["camera_model"] = merge_exif_text(
                get_exif_value(exif, exif_ifd, EXIF_MAKE_TAG),
                get_exif_value(exif, exif_ifd, EXIF_CAMERA_MODEL_TAG),
            )
            metadata["lens_model"] = merge_exif_text(
                get_exif_value(exif, exif_ifd, EXIF_LENS_MAKE_TAG),
                get_exif_value(exif, exif_ifd, EXIF_LENS_MODEL_TAG),
            )
            metadata["focal_length_35mm"] = format_focal_length_35mm(
                get_exif_value(exif, exif_ifd, EXIF_FOCAL_LENGTH_35MM_TAG)
            )
            metadata["aperture"] = format_aperture(get_exif_value(exif, exif_ifd, EXIF_F_NUMBER_TAG))

            shutter_speed_raw = get_exif_value(exif, exif_ifd, EXIF_EXPOSURE_TIME_TAG)
            if shutter_speed_raw is None:
                shutter_speed_raw = get_exif_value(exif, exif_ifd, EXIF_SHUTTER_SPEED_VALUE_TAG)
            metadata["shutter_speed"] = format_shutter_speed(shutter_speed_raw)

            iso_raw = None
            for tag in EXIF_ISO_TAGS:
                iso_raw = get_exif_value(exif, exif_ifd, tag)
                if iso_raw is not None:
                    break
            metadata["iso"] = format_iso(iso_raw)
    except (OSError, UnidentifiedImageError):
        return metadata

    return metadata


def create_thumbnail(source_path: Path, thumbnail_path: Path) -> bool:
    try:
        with Image.open(source_path) as image:
            preview_image = ImageOps.exif_transpose(image)
            preview_image = ImageOps.contain(preview_image, THUMBNAIL_MAX_SIZE, method=Image.Resampling.LANCZOS)
            if preview_image.mode in {"RGBA", "LA"} or (preview_image.mode == "P" and "transparency" in preview_image.info):
                rgba_image = preview_image.convert("RGBA")
                background = Image.new("RGBA", rgba_image.size, (247, 241, 232, 255))
                preview_image = Image.alpha_composite(background, rgba_image).convert("RGB")
            elif preview_image.mode != "RGB":
                preview_image = preview_image.convert("RGB")

            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
            preview_image.save(
                thumbnail_path,
                format="JPEG",
                quality=THUMBNAIL_QUALITY,
                optimize=True,
                progressive=True,
            )
    except (OSError, UnidentifiedImageError, ValueError):
        return False

    return True


def ensure_thumbnail_asset(photo: dict[str, Any]) -> bool:
    original_filename = photo.get("filename")
    if not original_filename:
        return False

    original_path = UPLOAD_DIR / original_filename
    if not original_path.exists():
        return False

    thumbnail_filename = photo.get("thumb_filename") or photo.get("thumbnail_filename")
    expected_version = photo.get("thumbnail_version")
    if not thumbnail_filename or expected_version != THUMBNAIL_VERSION:
        thumbnail_filename = f"{Path(original_filename).stem}_thumb_v{THUMBNAIL_VERSION}.jpg"
        photo["thumb_filename"] = thumbnail_filename
        photo["thumbnail_filename"] = thumbnail_filename
        photo["thumbnail_version"] = THUMBNAIL_VERSION

    thumbnail_path = THUMBNAIL_DIR / thumbnail_filename
    if thumbnail_path.exists():
        photo["thumb_filename"] = thumbnail_filename
        photo["thumbnail_filename"] = thumbnail_filename
        photo["thumbnail_version"] = THUMBNAIL_VERSION
        return False

    if create_thumbnail(original_path, thumbnail_path):
        photo["thumb_filename"] = thumbnail_filename
        photo["thumbnail_filename"] = thumbnail_filename
        photo["thumbnail_version"] = THUMBNAIL_VERSION
        return True

    return False


def detect_image_orientation(image_path: Path) -> str:
    try:
        with Image.open(image_path) as image:
            preview_image = ImageOps.exif_transpose(image)
            width, height = preview_image.size
    except (OSError, UnidentifiedImageError):
        return "landscape"

    if width < height:
        return "portrait"

    if width == height:
        return "square"

    return "landscape"


def ensure_photo_details(photo: dict[str, Any]) -> bool:
    original_filename = photo.get("filename")
    if not original_filename:
        return False

    original_path = UPLOAD_DIR / original_filename
    if not original_path.exists():
        return False

    uploaded_at = parse_datetime_input(photo.get("uploaded_at"))
    derived_metadata = extract_exif_metadata(original_path, uploaded_at)
    changed = False

    for key in ("camera_model", "lens_model", "focal_length_35mm", "aperture", "shutter_speed", "iso"):
        if key in {"camera_model", "lens_model"} and photo.get(f"{key}_source") == "manual":
            continue

        current_value = normalize_exif_text(photo.get(key))
        derived_value = normalize_exif_text(derived_metadata.get(key))

        if not current_value and derived_value:
            photo[key] = derived_value
            changed = True
            if key in {"camera_model", "lens_model"}:
                photo[f"{key}_source"] = photo.get(f"{key}_source") or "exif"
            continue

        if key in {"camera_model", "lens_model"} and derived_value and current_value and current_value.casefold() in derived_value.casefold() and current_value != derived_value:
            photo[key] = derived_value
            changed = True
            photo[f"{key}_source"] = photo.get(f"{key}_source") or "exif"

    orientation = detect_image_orientation(original_path)
    if photo.get("orientation") != orientation:
        photo["orientation"] = orientation
        changed = True

    return changed


def render_photo_item(photo: dict[str, Any]) -> dict[str, Any]:
    captured_at = photo.get("captured_at")
    uploaded_at = photo.get("uploaded_at")

    captured_dt = parse_datetime_input(captured_at)
    uploaded_dt = parse_datetime_input(uploaded_at)
    original_path = UPLOAD_DIR / photo["filename"]
    orientation = photo.get("orientation") or detect_image_orientation(original_path)

    thumb_filename = photo.get("thumb_filename") or photo.get("thumbnail_filename")
    thumb_path = THUMBNAIL_DIR / thumb_filename if thumb_filename else None
    if thumb_filename and thumb_path and thumb_path.exists():
        thumbnail_url = url_for("thumbnail_file", filename=thumb_filename)
    else:
        thumbnail_url = url_for("uploaded_file", filename=photo["filename"])

    original_url = url_for("uploaded_file", filename=photo["filename"])

    exif_specs = []
    for label, value in (
        ("相机型号", photo.get("camera_model", "")),
        ("镜头型号", photo.get("lens_model", "")),
        ("35mm等效焦距", photo.get("focal_length_35mm", "")),
        ("光圈", photo.get("aperture", "")),
        ("快门速度", photo.get("shutter_speed", "")),
        ("ISO", photo.get("iso", "")),
    ):
        if value:
            exif_specs.append({"label": label, "value": value})

    return {
        **photo,
        "image_url": thumbnail_url,
        "thumbnail_url": thumbnail_url,
        "original_url": original_url,
        "orientation": orientation,
        "taken_label": captured_dt.strftime("%Y.%m.%d %H:%M"),
        "taken_input_value": format_datetime_local(captured_at),
        "uploaded_input_value": format_datetime_local(uploaded_at),
        "group_key": captured_dt.strftime("%Y-%m-%d"),
        "group_label": captured_dt.strftime("%Y年%m月%d日"),
        "month_key": captured_dt.strftime("%Y-%m"),
        "month_label": captured_dt.strftime("%Y年%m月"),
        "uploaded_label": uploaded_dt.strftime("%Y.%m.%d %H:%M"),
        "camera_model": photo.get("camera_model", ""),
        "lens_model": photo.get("lens_model", ""),
        "focal_length_35mm": photo.get("focal_length_35mm", ""),
        "aperture": photo.get("aperture", ""),
        "shutter_speed": photo.get("shutter_speed", ""),
        "iso": photo.get("iso", ""),
        "exif_specs": exif_specs,
    }


def build_timeline(photos: list[dict[str, Any]], view_mode: str = "day") -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    current_key: str | None = None
    current_group: dict[str, Any] | None = None
    key_field = "month_key" if view_mode == "month" else "group_key"
    label_field = "month_label" if view_mode == "month" else "group_label"

    for photo in photos:
        photo_key = photo[key_field]
        if photo_key != current_key:
            current_group = {
                "key": photo_key,
                "label": photo[label_field],
                "photos": [],
            }
            groups.append(current_group)
            current_key = photo_key

        if current_group is not None:
            current_group["photos"].append(photo)

    return groups


@app.before_request
def track_visitor() -> None:
    if request.endpoint == "index":
        ip = request.remote_addr or request.headers.get("X-Forwarded-For", "unknown")
        record_visitor(ip)


@app.get("/")
def index() -> str:
    decorated_photos = [render_photo_item(photo) for photo in load_photos()]
    latest_photo = decorated_photos[0] if decorated_photos else None
    oldest_photo = decorated_photos[-1] if decorated_photos else None
    view_mode = request.args.get("view", "day").lower()
    if view_mode not in {"day", "month"}:
        view_mode = "day"

    if view_mode == "month":
        timeline_title = "月度时间线"
        timeline_hint = "按月聚合照片，快速查看每个月的拍摄概览。"
    else:
        timeline_title = "滚动时间线"
        timeline_hint = "似水流年"

    return render_template(
        "index.html",
        timeline=build_timeline(decorated_photos, view_mode),
        total_photos=len(decorated_photos),
        latest_shot=latest_photo["taken_label"] if latest_photo else "暂无",
        latest_upload=latest_photo["uploaded_label"] if latest_photo else "暂无",
        oldest_shot=oldest_photo["taken_label"] if oldest_photo else "暂无",
        today_visitors=get_today_visitors(),
        view_mode=view_mode,
        timeline_title=timeline_title,
        timeline_hint=timeline_hint,
        admin_authenticated=is_admin_authenticated(),
        github_login_configured=is_github_login_configured(),
        github_allowed_users_label="、".join(sorted(GITHUB_ALLOWED_USERS)) if GITHUB_ALLOWED_USERS else "未配置",
        admin_password_configured=bool(ADMIN_PASSWORD),
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login() -> str:
    next_url = safe_next_url(request.values.get("next"), url_for("index"))

    if request.method == "POST":
        if not ADMIN_PASSWORD:
            flash("服务器还没有配置管理员密码，暂时无法启用上传。", "error")
            return redirect(url_for("index"))

        password = request.form.get("password", "")
        if hmac.compare_digest(password, ADMIN_PASSWORD):
            authenticate_admin()
            flash("管理员登录成功。", "success")
            return redirect(next_url)

        flash("管理员密码不正确。", "error")
        return redirect(url_for("admin_login", next=next_url))

    return render_template(
        "admin_login.html",
        next_url=next_url,
        github_login_configured=is_github_login_configured(),
        github_allowed_users_label="、".join(sorted(GITHUB_ALLOWED_USERS)) if GITHUB_ALLOWED_USERS else "未配置",
        admin_password_configured=bool(ADMIN_PASSWORD),
    )


@app.get("/admin/github/login")
def admin_github_login() -> str:
    next_url = safe_next_url(request.values.get("next"), url_for("index"))

    if not is_github_login_configured():
        flash("GitHub 登录还没有配置好，请先设置 GITHUB_CLIENT_ID、GITHUB_CLIENT_SECRET 和 GITHUB_ALLOWED_USERS。", "error")
        return redirect(url_for("admin_login", next=next_url))

    session["github_oauth_state"] = uuid.uuid4().hex
    session["github_oauth_next"] = next_url
    return redirect(build_github_authorize_url(session["github_oauth_state"]))


@app.get("/admin/github/callback")
def admin_github_callback() -> str:
    next_url = safe_next_url(session.pop("github_oauth_next", None), url_for("index"))
    expected_state = session.pop("github_oauth_state", None)
    returned_error = request.args.get("error", "")
    returned_state = request.args.get("state", "")

    if returned_error:
        flash("GitHub 登录已取消。", "error")
        return redirect(url_for("admin_login", next=next_url))

    if not expected_state or not returned_state or not hmac.compare_digest(str(expected_state), str(returned_state)):
        flash("GitHub 登录状态校验失败，请重新尝试。", "error")
        return redirect(url_for("admin_login", next=next_url))

    if not is_github_login_configured():
        flash("GitHub 登录还没有配置好，请先设置 GITHUB_CLIENT_ID、GITHUB_CLIENT_SECRET 和 GITHUB_ALLOWED_USERS。", "error")
        return redirect(url_for("admin_login", next=next_url))

    code = request.args.get("code", "")
    if not code:
        flash("GitHub 回调缺少授权码。", "error")
        return redirect(url_for("admin_login", next=next_url))

    access_token = exchange_github_code_for_token(code)
    if not access_token:
        flash("GitHub 授权失败，请确认回调地址和 OAuth 应用配置是否一致。", "error")
        return redirect(url_for("admin_login", next=next_url))

    github_user = fetch_github_user(access_token)
    if not github_user:
        flash("无法读取 GitHub 用户信息，请稍后重试。", "error")
        return redirect(url_for("admin_login", next=next_url))

    github_login = str(github_user.get("login", "")).strip().lower()
    if not github_login:
        flash("GitHub 返回的账号信息不完整。", "error")
        return redirect(url_for("admin_login", next=next_url))

    if not is_allowed_github_user(github_login):
        flash("当前 GitHub 账号没有管理员权限。", "error")
        return redirect(url_for("admin_login", next=next_url))

    github_name = str(github_user.get("name") or github_login).strip()
    github_avatar = str(github_user.get("avatar_url") or "").strip()
    authenticate_admin(
        login_method="github",
        github_login=github_login,
        github_name=github_name,
        github_avatar=github_avatar,
    )
    flash(f"GitHub 登录成功：{github_login}。", "success")
    return redirect(next_url)


@app.get("/admin/logout")
def admin_logout() -> str:
    logout_admin()
    flash("已退出管理员身份。", "success")
    return redirect(url_for("index"))


@app.post("/photos/<photo_id>/delete")
def delete_photo(photo_id: str) -> str:
    if not is_admin_authenticated():
        flash("请先以管理员身份登录，再删除照片。", "error")
        return redirect(url_for("admin_login", next=url_for("index")))

    stored_photos = load_photos()
    photo_to_delete = next((photo for photo in stored_photos if photo.get("id") == photo_id), None)

    if photo_to_delete is None:
        flash("未找到要删除的照片。", "error")
        return redirect(url_for("index"))

    photo_path = UPLOAD_DIR / photo_to_delete["filename"]
    if photo_path.exists():
        try:
            photo_path.unlink()
        except OSError:
            flash("照片文件删除失败，请稍后重试。", "error")
            return redirect(url_for("index"))

    thumbnail_filename = photo_to_delete.get("thumb_filename") or photo_to_delete.get("thumbnail_filename")
    if thumbnail_filename:
        thumbnail_path = THUMBNAIL_DIR / thumbnail_filename
        if thumbnail_path.exists():
            try:
                thumbnail_path.unlink()
            except OSError:
                pass

    remaining_photos = [photo for photo in stored_photos if photo.get("id") != photo_id]
    save_photos(remaining_photos)

    deleted_title = photo_to_delete.get("title") or photo_to_delete.get("original_name") or "照片"
    flash(f"已删除照片：{deleted_title}", "success")
    return redirect(url_for("index"))


@app.post("/upload")
def upload() -> str:
    if not is_admin_authenticated():
        flash("请先以管理员身份登录，再上传照片。", "error")
        return redirect(url_for("admin_login", next=url_for("index")))

    ensure_storage()

    photos = [item for item in request.files.getlist("photos") if item and item.filename]
    if not photos:
        flash("请选择至少一张照片。", "error")
        return redirect(url_for("index"))

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    stored_photos = load_photos()
    added_count = 0
    upload_timestamp = datetime.now()

    for file in photos:
        if not allowed_file(file.filename):
            flash(f"{file.filename} 不是支持的图片格式。", "error")
            continue

        original_name = file.filename
        safe_name = secure_filename(original_name) or "photo"
        suffix = Path(safe_name).suffix.lower()
        stem = Path(safe_name).stem or "photo"
        photo_id = uuid.uuid4().hex
        stored_name = f"{upload_timestamp.strftime('%Y%m%d%H%M%S')}_{photo_id[:12]}{suffix}"
        thumbnail_name = f"{Path(stored_name).stem}_thumb.jpg"
        destination = UPLOAD_DIR / stored_name
        file.save(destination)

        exif_metadata = extract_exif_metadata(destination, upload_timestamp)
        captured_at = exif_metadata["captured_at"]
        captured_at_source = exif_metadata["captured_at_source"]
        thumbnail_path = THUMBNAIL_DIR / thumbnail_name
        thumbnail_created = create_thumbnail(destination, thumbnail_path)

        stored_photos.append(
            {
                "id": photo_id,
                "filename": stored_name,
                "thumb_filename": thumbnail_name if thumbnail_created else "",
                "thumbnail_filename": thumbnail_name if thumbnail_created else "",
                "thumbnail_version": THUMBNAIL_VERSION,
                "original_name": original_name,
                "title": title or stem,
                "description": description,
                "captured_at": captured_at.isoformat(timespec="minutes"),
                "captured_at_source": captured_at_source,
                "uploaded_at": upload_timestamp.isoformat(timespec="minutes"),
                "size": destination.stat().st_size,
                "camera_model": exif_metadata["camera_model"],
                "lens_model": exif_metadata["lens_model"],
                "focal_length_35mm": exif_metadata["focal_length_35mm"],
                "aperture": exif_metadata["aperture"],
                "shutter_speed": exif_metadata["shutter_speed"],
                "iso": exif_metadata["iso"],
            }
        )
        added_count += 1

    if added_count:
        save_photos(stored_photos)
        flash(f"成功上传 {added_count} 张照片。", "success")
    else:
        flash("没有成功上传任何照片。", "error")

    return redirect(url_for("index"))


@app.post("/photos/<photo_id>/edit")
def edit_photo(photo_id: str) -> str:
    if not is_admin_authenticated():
        flash("请先以管理员身份登录，再修改照片信息。", "error")
        return redirect(url_for("admin_login", next=url_for("index")))

    stored_photos = load_photos()
    photo_to_edit = next((photo for photo in stored_photos if photo.get("id") == photo_id), None)

    if photo_to_edit is None:
        flash("未找到要修改的照片。", "error")
        return redirect(url_for("index"))

    new_title = normalize_form_text(request.form.get("title"))
    new_original_name = normalize_form_text(request.form.get("original_name"))
    new_uploaded_at = parse_optional_datetime_input(request.form.get("uploaded_at"))
    new_taken_at = parse_optional_datetime_input(request.form.get("taken_at"))
    new_description = normalize_form_text(request.form.get("description"))
    new_camera_model = normalize_form_text(request.form.get("camera_model"))
    new_lens_model = normalize_form_text(request.form.get("lens_model"))
    new_focal_length_35mm = normalize_form_text(request.form.get("focal_length_35mm"))
    new_aperture = normalize_form_text(request.form.get("aperture"))
    new_shutter_speed = normalize_form_text(request.form.get("shutter_speed"))
    new_iso = normalize_form_text(request.form.get("iso"))

    current_original_name = photo_to_edit.get("original_name", photo_to_edit["filename"])
    photo_to_edit["title"] = new_title or Path(new_original_name or current_original_name).stem or "photo"
    photo_to_edit["description"] = new_description

    if new_original_name:
        photo_to_edit["original_name"] = new_original_name

    if new_uploaded_at is not None:
        photo_to_edit["uploaded_at"] = new_uploaded_at.isoformat(timespec="minutes")
        photo_to_edit["uploaded_at_source"] = "manual"

    if new_taken_at is not None:
        photo_to_edit["captured_at"] = new_taken_at.isoformat(timespec="minutes")
        photo_to_edit["captured_at_source"] = "manual"

    metadata_updates = {
        "camera_model": new_camera_model,
        "lens_model": new_lens_model,
        "focal_length_35mm": new_focal_length_35mm,
        "aperture": new_aperture,
        "shutter_speed": new_shutter_speed,
        "iso": new_iso,
    }
    for key, value in metadata_updates.items():
        current_value = normalize_exif_text(photo_to_edit.get(key))
        if value != current_value:
            photo_to_edit[key] = value
            if key in {"camera_model", "lens_model"}:
                photo_to_edit[f"{key}_source"] = "manual"

    save_photos(stored_photos)
    flash("已更新照片信息。", "success")
    return redirect(url_for("index", _anchor=f"photo-{photo_id}"))


@app.get("/uploads/<path:filename>")
def uploaded_file(filename: str):
    return send_from_directory(UPLOAD_DIR, filename)


@app.get("/thumbnails/<path:filename>")
def thumbnail_file(filename: str):
    return send_from_directory(THUMBNAIL_DIR, filename)


@app.get("/fonts/<path:filename>")
def font_file(filename: str):
    return send_from_directory(FONT_DIR, filename)


@app.get("/logo/<path:filename>")
def logo_file(filename: str):
    return send_from_directory(LOGO_DIR, filename)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.errorhandler(413)
def payload_too_large(_error):
    flash("单次上传太大了，请压缩图片后重试。", "error")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=True)
