"""Offline rule-based scenario parser (Russian and English).

The parser works on normalized lowercase text (``ё`` -> ``е``) and relies on
stem regexes rather than full morphology. It is deliberately heuristic: the
goal is a sensible plan for typical short crash/chase scenarios.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schema import (
    Action,
    ActionType,
    Actor,
    ActorColor,
    ActorKind,
    ActorRole,
    CameraHint,
    Environment,
    LocationType,
    Scene,
    ScriptPlan,
    Weather,
)

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

W = r"[a-zа-я0-9]*"  # word continuation after a stem

# Ordered: earlier patterns win on overlapping spans (multi-word first).
VEHICLE_PATTERNS: list[tuple[ActorKind, str]] = [
    (
        ActorKind.police,
        rf"\bполицейск{W}(?:\s+(?:машин|автомобил|авто|седан|внедорожник){W})?",
    ),
    (
        ActorKind.police,
        rf"\bполици{W}|\bпатрульн{W}(?:\s+(?:машин|автомобил){W})?|\bкопы\b|\bкопов\b",
    ),
    (
        ActorKind.police,
        r"\bpolice(?:\s+(?:car|cruiser|suv|vehicle)s?)?\b|\bcop\s+cars?\b|\bcops\b",
    ),
    (ActorKind.sports_car, rf"\bспортивн{W}\s+(?:автомобил|машин|кар|купе){W}"),
    (ActorKind.sports_car, rf"\bгоночн{W}\s+(?:автомобил|машин|болид){W}"),
    (ActorKind.sports_car, rf"\bспорткар{W}|\bсуперкар{W}|\bгиперкар{W}|\bболид{W}"),
    (
        ActorKind.sports_car,
        r"\bsports?\s+cars?\b|\bsupercars?\b|\bhypercars?\b|\brace\s+cars?\b",
    ),
    (
        ActorKind.van,
        rf"\bмикроавтобус{W}|\bфургон{W}|\bминивэн{W}|\bминивен{W}|\bгазел{W}",
    ),
    (ActorKind.van, r"\b(?:mini)?vans?\b"),
    (ActorKind.bus, rf"\bавтобус{W}"),
    (ActorKind.bus, r"\bbus(?:es)?\b"),
    (ActorKind.semi, rf"\bфур(?:а|ы|е|у|ой|ою|ам|ами|ах)\b|\bтягач{W}|\bдальнобой{W}"),
    (ActorKind.semi, r"\bsemi(?:-?trucks?)?\b|\bbig\s+rigs?\b|\btractor\s+trailers?\b"),
    (
        ActorKind.truck,
        rf"\bгрузовик{W}|\bгрузов{W}\s+(?:машин|автомобил){W}|\bсамосвал{W}|\bкамаз{W}",
    ),
    (ActorKind.truck, r"\btrucks?\b|\blorr(?:y|ies)\b|\bdump\s+trucks?\b"),
    (ActorKind.pickup, rf"\bпикап{W}"),
    (ActorKind.pickup, r"\bpick-?ups?(?:\s+trucks?)?\b"),
    (ActorKind.suv, rf"\bвнедорожник{W}|\bкроссовер{W}"),
    (ActorKind.suv, r"\bsuvs?\b|\bcrossovers?\b"),
    (ActorKind.offroad, rf"\bджип{W}|\bбагги\b|\bвездеход{W}"),
    (ActorKind.offroad, r"\bjeeps?\b|\bbugg(?:y|ies)\b|\boff-?roaders?\b"),
    (ActorKind.sedan, rf"\bседан{W}"),
    (ActorKind.sedan, r"\bsedans?\b"),
    (ActorKind.hatchback, rf"\bхэтчбек{W}|\bхетчбек{W}|\bхэтчбэк{W}"),
    (ActorKind.hatchback, r"\bhatchbacks?\b"),
    (
        ActorKind.generic,
        rf"\bмашин{W}|\bавтомобил{W}|\bтачк{W}|\bавто\b|\bлегковушк{W}",
    ),
    (ActorKind.generic, r"\bcars?\b|\bvehicles?\b|\bautomobiles?\b"),
]

# (name, rgba, regex)
COLORS: list[tuple[str, tuple[float, float, float, float], str]] = [
    ("red", (0.8, 0.05, 0.05, 1.0), rf"\bкрасн{W}|\bred\b"),
    ("light_blue", (0.4, 0.7, 1.0, 1.0), rf"\bголуб{W}|\blight\s+blue\b|\bcyan\b"),
    (
        "blue",
        (0.05, 0.15, 0.8, 1.0),
        r"\bсин(?:ий|яя|ее|его|ей|ем|ему|юю|ие|их|им|ими)\b|\bblue\b",
    ),
    ("green", (0.05, 0.6, 0.1, 1.0), rf"\bзелен{W}|\bgreen\b"),
    ("yellow", (0.95, 0.85, 0.05, 1.0), rf"\bжелт{W}|\byellow\b"),
    (
        "white",
        (0.95, 0.95, 0.95, 1.0),
        r"\bбел(?:ый|ая|ое|ого|ой|ом|ому|ую|ые|ых|ым|ыми)\b|\bwhite\b",
    ),
    ("black", (0.03, 0.03, 0.03, 1.0), rf"\bчерн{W}|\bblack\b"),
    ("silver", (0.75, 0.75, 0.78, 1.0), rf"\bсеребрист{W}|\bsilver\b"),
    (
        "gray",
        (0.45, 0.45, 0.45, 1.0),
        r"\bсер(?:ый|ая|ое|ого|ой|ом|ому|ую|ые|ых|ым|ыми)\b|\bgr[ae]y\b",
    ),
    ("orange", (1.0, 0.45, 0.0, 1.0), rf"\bоранжев{W}|\borange\b"),
    ("purple", (0.45, 0.1, 0.6, 1.0), rf"\bфиолетов{W}|\bpurple\b|\bviolet\b"),
    ("pink", (1.0, 0.45, 0.7, 1.0), rf"\bрозов{W}|\bpink\b"),
    ("brown", (0.4, 0.25, 0.1, 1.0), rf"\bкоричнев{W}|\bbrown\b"),
]

DESCRIPTORS: list[tuple[str, str]] = [
    ("old", rf"\bстар{W}|\bold\b"),
    ("rusty", rf"\bржав{W}|\brusty\b"),
    ("new", r"\bнов(?:ый|ая|ое|ого|ой|ом|ую|ые|ых)\b|\bnew\b"),
    ("heavy", rf"\bтяжел{W}|\bheavy\b"),
    ("huge", rf"\bогромн{W}|\bбольш{W}|\bhuge\b|\bbig\b|\bmassive\b"),
    ("small", rf"\bмаленьк{W}|\bнебольш{W}|\bsmall\b|\blittle\b|\btiny\b"),
    ("fast", rf"\bбыстр{W}|\bскоростн{W}|\bfast\b"),
    ("powerful", rf"\bмощн{W}|\bpowerful\b"),
    ("expensive", r"\bдорог(?:ой|ая|ое|ого|ую|ие)\b|\bexpensive\b|\bluxury\b"),
    ("damaged", rf"\bразбит{W}|\bпобит{W}|\bdamaged\b|\bwrecked\b"),
    ("lifted", rf"\bлифтован{W}|\blifted\b"),
]

NEW_ACTOR_MARKERS = re.compile(
    r"\bвтор(?:ой|ая|ое|ого|ую|ом)\b|\bдруг(?:ой|ая|ое|ого|ую|ом)\b|\bеще\s+од(?:ин|на|но|ного|ну)\b"
    r"|\banother\b|\bsecond\b|\bother\b"
)

# Ordered by priority: earlier patterns win on overlapping spans.
ACTION_PATTERNS: list[tuple[ActionType, str]] = [
    (
        ActionType.follow,
        rf"\bследу{W}\s+за\b|\bследом\s+за\b|\bедет\s+за\b|\bfollow{W}",
    ),
    (
        ActionType.lose_control,
        (
            rf"\b(?:по)?теря{W}\s+управлени{W}|\bзанос{W}|\bloses?\s+control\b"
            r"|\blost\s+control\b|\blosing\s+control\b|\bspins?\s+out\b|\bspinning\s+out\b"
        ),
    ),
    (
        ActionType.chase,
        (
            rf"\bпогон{W}|\bгонит(?:ся)?\s+за\b|\bгонится\b|\bгонятся\b|\bпресле{W}|\bдогон{W}|\bнастига{W}"
            r"|\bchas(?:e|es|ed|ing)\b|\bpursu{W}"
        ),
    ),
    (
        ActionType.flee,
        (
            rf"\bубега{W}|\bубеж{W}|\bскрыва{W}|\bскры(?:ть|лся|лась)\b|\bудира{W}|\bуходит\s+от\b"
            r"|\bотрыва{W}|\bflee{W}|\bfled\b|\bescap{W}|\bruns?\s+away\b|\bgetaway\b"
        ),
    ),
    (
        ActionType.swerve,
        (
            rf"\bувернут{W}|\bуворачива{W}|\bувернул{W}|\bобъезжа{W}|\bобъеха{W}|\bвырулива{W}"
            rf"|\bвыкручива{W}\s+руль|\bswerv{W}|\bdodg{W}|\bevad{W}"
        ),
    ),
    (
        ActionType.rollover,
        (
            rf"\bпереворачива{W}|\bперевер(?:нул|нет|тыва){W}|\bкувыр{W}|\bопрокид{W}"
            rf"|\bопрокин{W}|\broll(?:s|ed|ing)?\s+over\b|\brollover\b|\bflip(?:s|ped|ping)?\b|\btumbl{W}"
        ),
    ),
    (
        ActionType.crash_into,
        (
            rf"\bвреза{W}|\bврезал{W}|\bврежет{W}|\bстолкн{W}|\bстолкнов{W}|\b(?:про)?таран{W}"
            rf"|\bбьет{W}|\bбьют{W}|\bудар(?:яе|яет|ил|ит){W}|\bcrash{W}|\bcollid{W}|\bcollision\b"
            r"|\bslams?\s+into\b|\bhits?\b|\brams?\b|\brammed\b|\bsmash{W}"
        ),
    ),
    (
        ActionType.jump,
        rf"\bпрыга{W}|\bпрыгн{W}|\bпрыж{W}|\bтрамплин{W}|\bвзлета{W}|\bjump{W}|\bramp\b",
    ),
    (ActionType.drift, rf"\bдрифт{W}|\bdrift{W}"),
    (
        ActionType.appear,
        (
            rf"\bпоявля{W}|\bпоявил{W}|\bвозника{W}|\bвозник\b|\bвыезжа{W}|\bвыскакива{W}"
            rf"|\bвыскочи{W}|\bappear{W}|\bshows?\s+up\b|\bemerg{W}"
        ),
    ),
    (
        ActionType.overtake,
        rf"\bобгоня{W}|\bобгон{W}|\bобходит\b|\bovertak{W}|\bpass(?:es|ed)\b",
    ),
    (
        ActionType.accelerate,
        (
            rf"\bразгоня{W}|\bразогна{W}|\bразгон{W}|\bускоря{W}|\bнабира{W}\s+скорост{W}"
            rf"|\bжмет\s+(?:на\s+)?газ|\baccelerat{W}|\bspeeds?\s+up\b|\bfloors?\s+it\b"
        ),
    ),
    (ActionType.brake, rf"\b(?:за|при)?тормоз{W}|\bbrak{W}"),
    (
        ActionType.stop,
        rf"\bостанав{W}|\bостанов{W}|\bзамира{W}|\bзамер\b|\bstop{W}|\bhalt{W}",
    ),
    (
        ActionType.drive,
        (
            rf"\bед(?:ет|ут|ем|ешь)\b|\bпоеха{W}|\bеха{W}|\bмчит{W}|\bмчат{W}|\bнесет{W}|\bнесут{W}"
            rf"|\bлетит\b|\bкатит{W}|\bдвижет{W}|\bдвига{W}|\bнесется\b|\bdriv(?:e|es|ing)\b|\bdrove\b"
            rf"|\bcruis{W}|\brac(?:e|es|ing)\b|\bspeeds?\s+(?:along|down)\b|\bzooms?\b"
        ),
    ),
]

# Actions that normally have a target actor.
TRANSITIVE = {
    ActionType.overtake,
    ActionType.chase,
    ActionType.flee,
    ActionType.crash_into,
    ActionType.follow,
    ActionType.swerve,
}

PRONOUN_RE = re.compile(
    r"\b(?:него|нему|ним|нем|ней|нее|нею|ее|его|им|их|них|ними|it|him|her|them)\b"
)
ATTEMPT_RE = re.compile(
    r"пыта|попыта|старает|не успева|tries|trying|attempts?|fails? to"
)
STATIC_OBSTACLE_RE = re.compile(
    rf"\b(?:стен|отбойник|ограждени|столб|дерев|скал|бетон|барьер|wall|barrier|guardrail|pole|tree|rock){W}"
)

LOCATION_PATTERNS: list[tuple[LocationType, str]] = [
    (
        LocationType.track,
        (
            rf"\bгоночн{W}\s+трасс{W}|\bтрек{W}|\bавтодром{W}|\bкольцев{W}|\brace\s*track\b"
            r"|\bracetrack\b|\bcircuit\b|\btrack\b"
        ),
    ),
    (
        LocationType.gridmap,
        rf"\bполигон{W}|\bgrid\s*map\b|\bgridmap\b|\btest\s+(?:area|site)\b",
    ),
    (
        LocationType.mountain,
        (
            rf"\bгор(?:ы|ах|ам|ой|ами)?\b|\bгорн{W}|\bсерпантин{W}|\bперевал{W}"
            r"|\bmountain\w*|\bserpentine\b"
        ),
    ),
    (
        LocationType.offroad,
        (
            rf"\bбездорож{W}|\bгряз{W}|\bлес(?:у|а|ом|ной|ная|ные)?\b|\bполе\b|\bпол[ея]м\b"
            r"|\boff-?road\b|\bdirt\b|\bmud\w*|\bforest\b|\bwoods\b"
        ),
    ),
    (
        LocationType.city,
        (
            rf"\bгород{W}|\bулиц{W}|\bперекрест{W}|\bпроспект{W}|\bcity\b|\bstreets?\b"
            r"|\bdowntown\b|\bintersection\b|\btown\b"
        ),
    ),
    (
        LocationType.highway,
        (
            rf"\bтрасс{W}|\bшоссе\b|\bавтобан{W}|\bмагистрал{W}|\bхайвей{W}|\bhighway\b"
            r"|\bfreeway\b|\bmotorway\b|\binterstate\b"
        ),
    ),
]

WEATHER_PATTERNS: list[tuple[Weather, str]] = [
    (Weather.rain, rf"\bдожд{W}|\bдождь\b|\bливн{W}|\bливень\b|\brain{W}|\bstorm{W}"),
    (Weather.fog, rf"\bтуман{W}|\bfog{W}|\bmist{W}"),
    (Weather.snow, rf"\bснег{W}|\bснеж{W}|\bметел{W}|\bвьюг{W}|\bsnow{W}|\bblizzard\b"),
    (Weather.clear, rf"\bясн(?:ый|ая|ое|о)\b|\bсолнечн{W}|\bclear\b|\bsunny\b"),
]

# Fraction of the day: 0.0 = midnight, 0.5 = noon.
TIME_PATTERNS: list[tuple[float, str]] = [
    (0.0, rf"\bноч{W}|\bnight\w*|\bmidnight\b"),
    (0.25, rf"\bрассвет{W}|\bdawn\b|\bsunrise\b"),
    (0.78, rf"\bзакат{W}|\bsunset\b|\bdusk\b"),
    (0.83, rf"\bвечер{W}|\bevening\b"),
    (0.33, rf"\bутр{W}|\bmorning\b"),
    (0.5, r"\bдн(?:ем|ём)\b|\bдень\b|\bполдень\b|\bdaytime\b|\bnoon\b|\bday\b"),
]

SPEED_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(км\s*/\s*ч|км\s+в\s+час|кмч|km\s*/\s*h|kmh|kph|mph|миль\s+в\s+час)"
)

SCENE_HEADER_RE = re.compile(
    r"^\s*(?:#+\s*)?(?:сцена|scene|эпизод|episode|часть|part)\s*№?\s*(\d+)\s*[:.)\-—–]?\s*",
    re.IGNORECASE | re.MULTILINE,
)
TITLE_RE = re.compile(
    r"^\s*(?:название|заголовок|title)\s*[:\-—]\s*(.+)$", re.IGNORECASE | re.MULTILINE
)
SHORTS_RE = re.compile(r"шортс|\bshorts?\b|вертикальн|рилс|reels|тикток|tiktok")
LONG_RE = re.compile(
    r"длинн\w* (?:видео|ролик)|полноформатн|\blong(?:-form| video| format)\b"
)

# Highlight priority per action; 0 means "never a highlight".
HIGHLIGHT_PRIORITY: dict[ActionType, int] = {
    ActionType.crash_into: 5,
    ActionType.rollover: 5,
    ActionType.jump: 4,
    ActionType.lose_control: 2,
    ActionType.drift: 2,
    ActionType.overtake: 1,
    ActionType.chase: 1,
}
SCENE_BREAK_ACTIONS = {ActionType.crash_into, ActionType.rollover, ActionType.jump}

ACTION_DURATION_S: dict[ActionType, float] = {
    ActionType.drive: 5.0,
    ActionType.accelerate: 4.0,
    ActionType.brake: 3.0,
    ActionType.stop: 3.0,
    ActionType.overtake: 5.0,
    ActionType.chase: 8.0,
    ActionType.flee: 6.0,
    ActionType.swerve: 3.0,
    ActionType.lose_control: 3.0,
    ActionType.rollover: 4.0,
    ActionType.crash_into: 3.0,
    ActionType.jump: 4.0,
    ActionType.drift: 5.0,
    ActionType.appear: 3.0,
    ActionType.follow: 6.0,
}

CAMERA_BY_ACTION: dict[ActionType, list[CameraHint]] = {
    ActionType.crash_into: [CameraHint.cinematic, CameraHint.slowmo, CameraHint.replay],
    ActionType.rollover: [CameraHint.cinematic, CameraHint.slowmo, CameraHint.replay],
    ActionType.jump: [CameraHint.cinematic, CameraHint.slowmo],
    ActionType.chase: [CameraHint.follow, CameraHint.drone],
    ActionType.flee: [CameraHint.follow, CameraHint.drone],
    ActionType.follow: [CameraHint.follow, CameraHint.drone],
    ActionType.drift: [CameraHint.drone, CameraHint.follow],
    ActionType.drive: [CameraHint.follow, CameraHint.front],
    ActionType.accelerate: [CameraHint.follow, CameraHint.front],
    ActionType.overtake: [CameraHint.front, CameraHint.follow],
    ActionType.lose_control: [CameraHint.cinematic],
    ActionType.swerve: [CameraHint.front],
    ActionType.appear: [CameraHint.front],
}

PASSENGER_KINDS = {
    ActorKind.sports_car,
    ActorKind.sedan,
    ActorKind.suv,
    ActorKind.hatchback,
    ActorKind.pickup,
    ActorKind.police,
    ActorKind.offroad,
    ActorKind.generic,
}

RU_ADJ_ENDINGS = (
    "ый",
    "ий",
    "ой",
    "ая",
    "яя",
    "ое",
    "ее",
    "ого",
    "его",
    "ому",
    "ему",
    "ую",
    "юю",
    "ым",
    "им",
    "ом",
    "ем",
    "ей",
    "ые",
    "ие",
    "ых",
    "их",
    "ыми",
    "ими",
)
EN_SKIP_WORDS = {"a", "an", "the", "one"}

_COMPILED_VEHICLES = [(k, re.compile(p)) for k, p in VEHICLE_PATTERNS]
_COMPILED_ACTIONS = [(t, re.compile(p)) for t, p in ACTION_PATTERNS]
_COMPILED_COLORS = [(n, rgba, re.compile(p)) for n, rgba, p in COLORS]
_COMPILED_DESCRIPTORS = [(n, re.compile(p)) for n, p in DESCRIPTORS]
_WORD_RE = re.compile(r"[a-zа-я0-9\-]+")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def normalize(text: str) -> str:
    """Lowercase and unify ``ё``/``е`` for stem matching."""
    return text.replace("ё", "е").replace("Ё", "Е").lower()


def _find_spans(
    text: str, patterns: list[tuple[object, re.Pattern[str]]]
) -> list[tuple[int, int, object]]:
    """Return non-overlapping matches; earlier patterns take precedence."""
    taken: list[tuple[int, int, object]] = []
    for value, rx in patterns:
        for m in rx.finditer(text):
            s, e = m.span()
            if s == e or any(s < te and ts < e for ts, te, _ in taken):
                continue
            taken.append((s, e, value))
    taken.sort(key=lambda t: t[0])
    return taken


def _first_match(text: str, patterns: list[tuple[object, str]]) -> object | None:
    for value, pat in patterns:
        if re.search(pat, text):
            return value
    return None


def _match_color(word: str) -> tuple[str, tuple[float, float, float, float]] | None:
    for name, rgba, rx in _COMPILED_COLORS:
        if rx.fullmatch(word) or rx.match(word):
            return name, rgba
    return None


def _is_modifier_word(word: str) -> bool:
    """True for words that can sit inside a noun phrase before the vehicle noun."""
    if re.fullmatch(r"[a-z\-]+", word):
        return True  # English: bounded by the word-count limit instead
    return word.endswith(RU_ADJ_ENDINGS) or word in {"еще", "один", "одна", "одно"}


def split_sentences(text: str) -> list[str]:
    """Split a block into sentences on terminal punctuation and newlines."""
    parts = re.split(r"(?<=[.!?…])\s+|\n+", text)
    return [p.strip() for p in parts if p and p.strip(" \t.!?…-—")]


# --------------------------------------------------------------------------
# Parser state
# --------------------------------------------------------------------------


@dataclass
class _Mention:
    start: int
    end: int
    actor_id: str


@dataclass
class _SceneDraft:
    sentences: list[str] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)

    def add_actor(self, actor_id: str) -> None:
        if actor_id not in self.actors:
            self.actors.append(actor_id)


class RuleParser:
    """Stateful single-use parser; call :meth:`parse` once per script."""

    def __init__(self) -> None:
        self.actors: list[Actor] = []
        self.recency: list[str] = []  # actor ids, most recent last
        self.last_subject: str | None = None
        self.obstacle: str | None = None
        self.warnings: list[str] = []

    # ---- actors ---------------------------------------------------------

    def _get(self, actor_id: str) -> Actor:
        return next(a for a in self.actors if a.id == actor_id)

    def _touch(self, actor_id: str) -> None:
        if actor_id in self.recency:
            self.recency.remove(actor_id)
        self.recency.append(actor_id)

    def _new_actor(
        self, kind: ActorKind, color: ActorColor | None, descriptors: list[str]
    ) -> Actor:
        actor = Actor(
            id=f"car{len(self.actors) + 1}",
            kind=kind,
            color=color,
            descriptors=descriptors,
            role=ActorRole.hero if not self.actors else ActorRole.other,
        )
        if kind == ActorKind.police:
            actor.role = ActorRole.pursuer
        self.actors.append(actor)
        return actor

    def _resolve_actor(
        self,
        kind: ActorKind,
        color: ActorColor | None,
        descriptors: list[str],
        is_new: bool,
        in_sentence: set[str],
        object_position: bool = False,
    ) -> str:
        """Map a noun mention to an existing actor or create a new one.

        A specific noun never refers to an actor already named in the same
        sentence ("седан обгоняет седан" means two cars); a generic noun may,
        unless it stands right after a verb ("седан обгоняет машину").
        """
        if not is_new:
            recent = [self._get(i) for i in reversed(self.recency)]
            # Pass 1: exact kind match.
            for a in recent:
                if a.id in in_sentence:
                    continue
                if (
                    kind != ActorKind.generic
                    and a.kind == kind
                    and self._color_ok(a, color)
                ):
                    return self._merge(a, color, descriptors)
            # Pass 2: generic noun ("машина") refers back, preferring passenger cars.
            if kind == ActorKind.generic:
                for pool in ([a for a in recent if a.kind in PASSENGER_KINDS], recent):
                    for a in pool:
                        if object_position and a.id in in_sentence:
                            continue
                        if self._color_ok(a, color, strict=color is not None):
                            return self._merge(a, color, descriptors)
            # Pass 3: a specific noun refines an earlier generic actor.
            for a in recent:
                if a.id in in_sentence:
                    continue
                if a.kind == ActorKind.generic and self._color_ok(a, color):
                    a.kind = kind
                    return self._merge(a, color, descriptors)
        return self._new_actor(kind, color, descriptors).id

    @staticmethod
    def _color_ok(a: Actor, color: ActorColor | None, strict: bool = False) -> bool:
        if color is None:
            return True
        if a.color is None:
            return not strict
        return a.color.name == color.name

    @staticmethod
    def _merge(a: Actor, color: ActorColor | None, descriptors: list[str]) -> str:
        if a.color is None and color is not None:
            a.color = color
        for d in descriptors:
            if d not in a.descriptors:
                a.descriptors.append(d)
        return a.id

    def _noun_phrase_modifiers(
        self, sent: str, start: int, end: int
    ) -> tuple[ActorColor | None, list[str], bool]:
        """Collect color/descriptors/'another' markers around a vehicle noun."""
        words = _WORD_RE.findall(sent[:start])
        prefix: list[str] = []
        for w in reversed(words[-4:]):
            if w in EN_SKIP_WORDS:
                continue
            if not _is_modifier_word(w):
                break
            prefix.insert(0, w)
            if len(prefix) >= 3:
                break
        # The matched noun itself may carry adjectives ("полицейская машина").
        head = sent[start:end]
        phrase = " ".join(prefix + [head])
        color: ActorColor | None = None
        for w in prefix:
            found = _match_color(w)
            if found:
                color = ActorColor(name=found[0], rgba=found[1])
        if color is None:
            # Postfix form: "машина красного цвета".
            m = re.match(r"\s+([a-zа-я]+)\s+цвета\b", sent[end:])
            if m and (found := _match_color(m.group(1))):
                color = ActorColor(name=found[0], rgba=found[1])
        descriptors = [n for n, rx in _COMPILED_DESCRIPTORS if rx.search(phrase)]
        is_new = bool(NEW_ACTOR_MARKERS.search(" ".join(prefix)))
        return color, descriptors, is_new

    def _fallback_actor(self) -> str:
        if self.last_subject:
            return self.last_subject
        if self.recency:
            return self.recency[-1]
        aid = self._new_actor(ActorKind.generic, None, []).id
        self.warnings.append("no vehicle mentioned; created a generic car")
        return aid

    def _other_recent(self, exclude: str) -> str | None:
        for aid in reversed(self.recency):
            if aid != exclude:
                return aid
        return None

    # ---- sentences ------------------------------------------------------

    def parse_sentence(self, raw: str, draft: _SceneDraft) -> list[Action]:
        """Extract actions from one sentence and register its actors."""
        sent = normalize(raw)
        verbs = _find_spans(sent, _COMPILED_ACTIONS)  # type: ignore[arg-type]
        mentions: list[_Mention] = []
        for s, e, kind in _find_spans(sent, _COMPILED_VEHICLES):  # type: ignore[arg-type]
            color, descriptors, is_new = self._noun_phrase_modifiers(sent, s, e)
            in_sentence = {m.actor_id for m in mentions}
            object_position = any(
                0 <= s - ve <= 25 and not re.search(r"[,;]", sent[ve:s])
                for _, ve, _ in verbs
            )
            aid = self._resolve_actor(
                kind,  # type: ignore[arg-type]
                color,
                descriptors,
                is_new,
                in_sentence,
                object_position,
            )
            self._touch(aid)
            draft.add_actor(aid)
            mentions.append(_Mention(s, e, aid))

        has_pronoun = bool(PRONOUN_RE.search(sent))
        used_as_target: set[int] = set()
        sentence_subject: str | None = None
        actions: list[Action] = []
        action_spans: list[tuple[int, int]] = []
        prev_end = 0

        for vi, (vs, ve, vtype) in enumerate(verbs):
            atype: ActionType = vtype  # type: ignore[assignment]
            next_start = verbs[vi + 1][0] if vi + 1 < len(verbs) else len(sent)
            fresh_before = [
                i
                for i, m in enumerate(mentions)
                if prev_end <= m.start and m.end <= vs and i not in used_as_target
            ]
            after = [i for i, m in enumerate(mentions) if ve <= m.start < next_start]
            # A noun after "увернуться от ..." etc. is clearly a target candidate.
            subject: str | None = None
            target: str | None = None

            if fresh_before:
                subject = mentions[fresh_before[-1]].actor_id
            elif sentence_subject is not None:
                subject = sentence_subject
            elif after and (atype not in TRANSITIVE or has_pronoun):
                # Inverted order: "Впереди появляется грузовик", "За ним гонится полиция".
                subject = mentions[after.pop(0)].actor_id
            else:
                subject = self._fallback_actor()

            if atype in TRANSITIVE:
                for i in after:
                    if mentions[i].actor_id != subject:
                        target = mentions[i].actor_id
                        used_as_target.add(i)
                        break
                if target is None:
                    target = self._infer_target(atype, subject, sent, has_pronoun)

            action = Action(type=atype, actor=subject, target=target)
            clause = sent[max(prev_end, vs - 30) : vs]
            if ATTEMPT_RE.search(clause):
                action.params["attempt"] = True
            if atype == ActionType.crash_into and target is None:
                m = STATIC_OBSTACLE_RE.search(sent, ve)
                if m:
                    action.params["object"] = m.group(0)
            if atype == ActionType.jump and re.search(r"трамплин|ramp", sent):
                action.params["ramp"] = True

            # Drop exact repeats ("прыгает с трамплина" = one jump).
            if actions and actions[-1].type == atype and actions[-1].actor == subject:
                prev_end = ve
                continue

            self._apply_roles(action)
            actions.append(action)
            action_spans.append((vs, ve))
            draft.add_actor(subject)
            if target:
                draft.add_actor(target)
            sentence_subject = subject
            self.last_subject = subject
            self._touch(subject)
            prev_end = ve

        self._apply_speeds(sent, action_spans, actions)
        return actions

    def _infer_target(
        self, atype: ActionType, subject: str, sent: str, has_pronoun: bool
    ) -> str | None:
        """Pick a target when the sentence names none explicitly."""
        if atype in (ActionType.swerve, ActionType.crash_into):
            if (
                atype == ActionType.crash_into
                and STATIC_OBSTACLE_RE.search(sent)
                and not has_pronoun
            ):
                return None
            if self.obstacle and self.obstacle != subject:
                return self.obstacle
            if has_pronoun or atype == ActionType.swerve:
                return self._other_recent(subject)
            return None
        return self._other_recent(subject)

    def _apply_roles(self, action: Action) -> None:
        actor = self._get(action.actor)
        if action.type == ActionType.appear and actor.role in (
            ActorRole.other,
            ActorRole.hero,
        ):
            if len(self.actors) > 1 and self.actors[0].id != actor.id:
                actor.role = ActorRole.obstacle
                self.obstacle = actor.id
        elif action.type == ActionType.chase and action.target:
            if actor.role == ActorRole.other:
                actor.role = ActorRole.pursuer
            tgt = self._get(action.target)
            if tgt.role in (ActorRole.other, ActorRole.hero):
                tgt.role = ActorRole.fugitive
        elif action.type == ActionType.flee:
            if actor.role in (ActorRole.other, ActorRole.hero):
                actor.role = ActorRole.fugitive
            if action.target and self._get(action.target).role == ActorRole.other:
                self._get(action.target).role = ActorRole.pursuer
        elif (
            action.type in (ActionType.swerve, ActionType.crash_into) and action.target
        ):
            tgt = self._get(action.target)
            if tgt.role == ActorRole.other:
                tgt.role = ActorRole.obstacle
                self.obstacle = tgt.id

    @staticmethod
    def _apply_speeds(
        sent: str, spans: list[tuple[int, int]], actions: list[Action]
    ) -> None:
        """Attach "200 км/ч" style speeds to the nearest action."""
        if not actions:
            return
        for m in SPEED_RE.finditer(sent):
            value = float(m.group(1).replace(",", "."))
            if m.group(2).startswith(("mph", "миль")):
                value *= 1.609
            pos = m.start()
            # Prefer the verb the speed phrase follows ("мчится на скорости 180 км/ч").
            before = [i for i, (vs, _) in enumerate(spans) if vs <= pos]
            best = before[-1] if before else 0
            if actions[best].speed_kmh is None:
                actions[best].speed_kmh = round(value, 1)


# --------------------------------------------------------------------------
# Scene assembly
# --------------------------------------------------------------------------


def _split_blocks(text: str) -> tuple[list[str], bool]:
    """Split by "Сцена N" headers (explicit) or blank lines."""
    headers = list(SCENE_HEADER_RE.finditer(text))
    if headers:
        blocks = []
        for i, h in enumerate(headers):
            end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
            blocks.append(text[h.end() : end].strip())
        preface = text[: headers[0].start()].strip()
        if preface and blocks:
            blocks[0] = preface + "\n" + blocks[0]
        return [b for b in blocks if b], True
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    return blocks, False


def _scene_environment(text: str, previous: Environment | None) -> Environment:
    norm = normalize(text)
    loc = _first_match(norm, LOCATION_PATTERNS)  # type: ignore[arg-type]
    weather = _first_match(norm, WEATHER_PATTERNS)  # type: ignore[arg-type]
    tod = _first_match(norm, TIME_PATTERNS)  # type: ignore[arg-type]
    prev = previous or Environment()
    return Environment(
        location_type=loc if loc is not None else prev.location_type,  # type: ignore[arg-type]
        weather=weather if weather is not None else prev.weather,  # type: ignore[arg-type]
        time_of_day=tod if tod is not None else prev.time_of_day,  # type: ignore[arg-type]
    )


def _highlight(actions: list[Action]) -> int | None:
    best, best_prio = None, 0
    for i, a in enumerate(actions):
        prio = HIGHLIGHT_PRIORITY.get(a.type, 0)
        if prio and prio >= best_prio:
            best, best_prio = i, prio
    return best


def _camera_hints(actions: list[Action]) -> list[CameraHint]:
    hints: list[CameraHint] = []
    for a in actions:
        for h in CAMERA_BY_ACTION.get(a.type, []):
            if h not in hints:
                hints.append(h)
    return hints or [CameraHint.follow]


def _duration(actions: list[Action], highlight: int | None) -> float:
    total = sum(min(8.0, max(3.0, ACTION_DURATION_S.get(a.type, 4.0))) for a in actions)
    if highlight is not None:
        total += 2.0
    return max(4.0, total)


def _detect_language(text: str) -> str:
    cyr = len(re.findall(r"[а-яё]", text, re.IGNORECASE))
    lat = len(re.findall(r"[a-z]", text, re.IGNORECASE))
    return "ru" if cyr >= lat else "en"


def parse_rules(text: str) -> ScriptPlan:
    """Parse a scenario into a :class:`ScriptPlan` without any network access."""
    parser = RuleParser()
    body = text.strip()
    title_match = TITLE_RE.search(body)
    title = title_match.group(1).strip() if title_match else None
    if title_match:
        body = (body[: title_match.start()] + body[title_match.end() :]).strip()

    blocks, explicit = _split_blocks(body)
    drafts: list[_SceneDraft] = []
    for block in blocks:
        draft = _SceneDraft()
        for sentence in split_sentences(block):
            actions = parser.parse_sentence(sentence, draft)
            if (
                not explicit
                and draft.actions
                and actions
                and any(a.type in SCENE_BREAK_ACTIONS for a in draft.actions)
            ):
                # Previous sentences already reached a highlight: start a new scene.
                drafts.append(draft)
                carry = _SceneDraft()
                for a in actions:
                    carry.add_actor(a.actor)
                    if a.target:
                        carry.add_actor(a.target)
                draft = carry
            draft.sentences.append(sentence)
            draft.actions.extend(actions)
        if draft.sentences:
            drafts.append(draft)

    # Merge scenes that ended up without any action into a neighbour.
    merged: list[_SceneDraft] = []
    for d in drafts:
        if not d.actions and merged and not explicit:
            merged[-1].sentences.extend(d.sentences)
            for aid in d.actors:
                merged[-1].add_actor(aid)
        elif merged and not merged[-1].actions and not explicit:
            d.sentences = merged[-1].sentences + d.sentences
            for aid in merged[-1].actors:
                d.add_actor(aid)
            merged[-1] = d
        else:
            merged.append(d)

    scenes: list[Scene] = []
    env: Environment | None = None
    for i, d in enumerate(merged):
        description = " ".join(d.sentences)
        env = _scene_environment(description, env)
        hl = _highlight(d.actions)
        if not d.actions:
            parser.warnings.append(f"scene {i}: no actions recognized")
        scenes.append(
            Scene(
                index=i,
                description=description,
                environment=env,
                actors=d.actors,
                actions=d.actions,
                duration_s=_duration(d.actions, hl),
                highlight=hl,
                camera_hints=_camera_hints(d.actions),
            )
        )

    # A global environment hint in a later scene should not leave earlier scenes at "any".
    first_loc = next(
        (
            s.environment.location_type
            for s in scenes
            if s.environment.location_type != LocationType.any
        ),
        None,
    )
    if first_loc is not None:
        for s in scenes:
            if s.environment.location_type == LocationType.any:
                s.environment.location_type = first_loc

    norm = normalize(text)
    target_format = (
        "shorts" if SHORTS_RE.search(norm) else "long" if LONG_RE.search(norm) else None
    )
    if not title:
        first = split_sentences(body)[0] if body else "Untitled"
        title = first if len(first) <= 60 else first[:57].rstrip() + "..."

    return ScriptPlan(
        title=title,
        language=_detect_language(text),
        actors=parser.actors,
        scenes=scenes,
        target_format=target_format,  # type: ignore[arg-type]
        total_duration_s=round(sum(s.duration_s for s in scenes), 2),
        parser="rule",
        warnings=parser.warnings,
    )
