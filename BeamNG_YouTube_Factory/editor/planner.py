"""Планировщик монтажа: выбор интересных фрагментов, замедление, подгонка под длительность. Чистая логика (тестируется)."""
from dataclasses import dataclass, field

EVENT_WEIGHT = {"crash": 3.0, "jump": 2.5, "loss_of_control": 2.0, "landing": 0.5, "top_speed": 0.3}
PRE = {"crash": 2.5, "jump": 3.0, "loss_of_control": 2.0, "landing": 0.5, "top_speed": 1.0}
POST = {"crash": 3.5, "jump": 3.0, "loss_of_control": 2.5, "landing": 1.5, "top_speed": 1.0}


@dataclass
class Segment:
    src: str
    start: float
    end: float
    speed: float = 1.0
    priority: float = 1.0
    label: str = ""
    scene_id: int = 0
    take: int = 0
    core: bool = False
    min_len: float = 1.0

    @property
    def out_len(self):
        return (self.end - self.start) / self.speed


def _merge(wins):
    wins = sorted(wins)
    out = []
    for a, b, w in wins:
        if out and a <= out[-1][1] + 0.3:
            out[-1][1] = max(out[-1][1], b)
            out[-1][2] += w
        else:
            out.append([a, b, w])
    return out


def best_window(profile, a, b, length):
    """Окно длиной length внутри [a,b] с максимальной суммой энергии движения."""
    if b - a <= length or not profile:
        return a, b
    best, best_s = a, -1.0
    t = a
    while t + length <= b + 1e-6:
        sc = sum(m.energy for m in profile if t <= m.t < t + length)
        if sc > best_s:
            best, best_s = t, sc
        t += 0.5
    return best, best + length


def plan_scene(take, active, duration, profile_energy, slowmo=0.4, budget=None):
    """take: объект Take (video, events, scene_id, index). active: (a,b) по движению. Возвращает сегменты."""
    a, b = active
    evs = [e for e in take.events if e.type in EVENT_WEIGHT and e.type != "top_speed"]
    segs: list[Segment] = []
    if not evs:
        # без событий: окно с максимальной динамикой движения
        if budget:
            a, b = best_window(profile_energy, a, b, budget)
        segs.append(Segment(take.video, a, b, 1.0, 1.0, "сцена", take.scene_id, take.index, core=True, min_len=3.0))
        return segs
    wins = [(max(a, e.t - PRE[e.type]), min(b, e.t + POST[e.type]), EVENT_WEIGHT[e.type]) for e in evs]
    merged = _merge(wins)
    # открывающий кадр: начало движения (разгон) — коротко
    first = merged[0][0]
    if first - a > 2.0:
        segs.append(Segment(take.video, a, min(first, a + 2.5), 1.0, 0.8, "разгон", take.scene_id, take.index, min_len=1.2))
    for s, e, w in merged:
        segs.append(Segment(take.video, s, e, 1.0, 2.0 + w, "действие", take.scene_id, take.index, core=True, min_len=2.5))
    # замедление в самых сильных моментах: разбиваем сегмент и замедляем окно вокруг события
    result = []
    for sg in segs:
        key = [e for e in evs if sg.start <= e.t <= sg.end and e.type in ("crash", "jump")]
        if sg.label != "действие" or not key:
            result.append(sg)
            continue
        k = max(key, key=lambda e: EVENT_WEIGHT[e.type])
        s1, s2 = max(sg.start, k.t - 0.8), min(sg.end, k.t + 1.2)
        if s1 > sg.start:
            result.append(Segment(sg.src, sg.start, s1, 1.0, sg.priority, "действие", sg.scene_id, sg.take, True, 1.0))
        result.append(Segment(sg.src, s1, s2, slowmo, sg.priority + 1, "слоу-мо", sg.scene_id, sg.take, True, (s2 - s1) * 0.7 / slowmo))
        if s2 < sg.end:
            result.append(Segment(sg.src, s2, sg.end, 1.0, sg.priority, "действие", sg.scene_id, sg.take, True, 1.0))
    return result


def plan_replays(takes_for_scene, main, slowmo=0.4):
    """Дополнительные дубли с другим ракурсом → короткие повторы ключевого момента."""
    segs = []
    for tk in takes_for_scene:
        if tk is main or not tk.ok:
            continue
        key = [e for e in tk.events if e.type in ("crash", "jump")]
        if not key:
            continue
        k = max(key, key=lambda e: EVENT_WEIGHT[e.type])
        segs.append(Segment(tk.video, max(0, k.t - 1.5), k.t + 2.0, slowmo, 0.5, "повтор", tk.scene_id, tk.index, False, 1.5))
    return segs


def _shrink(seg: Segment, new_out: float):
    """Укорачивает сегмент до new_out секунд итогового времени."""
    cut = (seg.out_len - new_out) * seg.speed
    if cut <= 0:
        return
    if seg.label == "слоу-мо":      # симметрично вокруг события
        seg.start += cut / 2
        seg.end -= cut / 2
    elif seg.label == "разгон":
        seg.end -= cut
    else:                           # «действие»: больше сохраняем конец (последствия)
        seg.start += cut * 0.6
        seg.end -= cut * 0.4


def fit(segments: list[Segment], target: float) -> list[Segment]:
    """Приводит суммарную длительность к target: ужать → убрать второстепенное → сжать ядро."""
    segs = list(segments)
    total = lambda: sum(s.out_len for s in segs)  # noqa: E731
    if total() <= target:
        return segs
    # A. ужимаем всё до min_len пропорционально
    excess = total() - target
    room = sum(max(0.0, s.out_len - s.min_len) for s in segs)
    if room > 0:
        frac = min(1.0, excess / room)
        for s in segs:
            _shrink(s, s.out_len - max(0.0, s.out_len - s.min_len) * frac)
    # B. убираем некритичные по возрастанию приоритета
    while total() > target + 0.05:
        flex = [s for s in segs if not s.core]
        if not flex:
            break
        segs.remove(min(flex, key=lambda s: s.priority))
    # C. сжимаем ядро равномерно
    if total() > target + 0.05:
        k = target / total()
        for s in segs:
            _shrink(s, s.out_len * k)
    return [s for s in segs if s.out_len > 0.2]


def map_events(segments: list[Segment], takes, xfade: float = 0.0):
    """События в таймлайне итогового видео: [(t_out, type, data)]. Берутся события дубля каждого сегмента."""
    out, offset = [], 0.0
    bytake = {(t.video, t.index): t for t in takes}
    for s in segments:
        tk = bytake.get((s.src, s.take))
        if tk:
            for e in tk.events:
                if s.start <= e.t <= s.end:
                    out.append((offset + (e.t - s.start) / s.speed, e.type, e.data))
        offset += s.out_len
    return sorted(out, key=lambda x: x[0])
