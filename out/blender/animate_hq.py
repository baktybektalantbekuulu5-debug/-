"""Анимированный клип Тимура: EEVEE (GPU), 1080x1920, 24 кадра/с, 10 секунд, зациклен.

Сцена (модель, свет, камера, стекло, контур) берётся из render_hq.py. У модели нет скелета,
поэтому детали группируются по положению и вешаются на пустышки-шарниры: шея, плечи, локти.

Шаг 1 — кадры (можно прервать и запустить снова, готовые кадры пропускаются):
    blender -b --factory-startup --python out/blender/animate_hq.py
Шаг 2 — сборка MP4 из кадров:
    blender -b --factory-startup --python out/blender/animate_hq.py -- encode

Переменные окружения: TIMUR_FRAMES_DIR (папка кадров), TIMUR_SAMPLES (по умолчанию 64),
TIMUR_FRAME_RANGE ("1-240"), TIMUR_FRAME_STEP, TIMUR_VIDEO (путь к mp4).
"""
import bpy, math, os, sys, time
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
FPS, SECONDS = 24, 10
N = FPS * SECONDS
FRAMES = os.environ.get('TIMUR_FRAMES_DIR') or os.path.join(HERE, 'hq', 'frames')
VIDEO = os.environ.get('TIMUR_VIDEO') or os.path.join(HERE, 'hq', 'timur_wave_1080x1920.mp4')
ENCODE = 'encode' in sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else False


def frame_path(f):
    return os.path.join(FRAMES, f'timur_{f:04d}.png')


# ======================= сборка видео =======================
if ENCODE:
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1080, 1920, 100
    sc.render.fps = FPS; sc.frame_start = 1; sc.frame_end = N
    sc.view_settings.view_transform = 'Standard'
    missing = [f for f in range(1, N + 1) if not os.path.exists(frame_path(f))]
    if missing:
        raise SystemExit(f'нет кадров: {missing[:10]} (всего {len(missing)})')
    se = sc.sequence_editor_create()
    strips = se.strips if hasattr(se, 'strips') else se.sequences
    st = strips.new_image('timur', frame_path(1), 1, 1)
    for f in range(2, N + 1):
        st.elements.append(os.path.basename(frame_path(f)))
    ims = sc.render.image_settings
    if hasattr(ims, 'media_type'):
        ims.media_type = 'VIDEO'
    ims.file_format = 'FFMPEG'
    ff = sc.render.ffmpeg
    ff.format = 'MPEG4'; ff.codec = 'H264'; ff.constant_rate_factor = 'HIGH'; ff.ffmpeg_preset = 'GOOD'
    ff.gopsize = FPS; ff.audio_codec = 'NONE'
    sc.render.filepath = VIDEO
    sc.render.use_file_extension = False
    bpy.ops.render.render(animation=True)
    print('encoded', VIDEO, os.path.getsize(VIDEO), flush=True)
    raise SystemExit(0)

# ======================= сцена =======================
os.environ.setdefault('TIMUR_SAMPLES', '64')
sys.path.insert(0, HERE)
import render_hq as R   # noqa: E402  (строит сцену при импорте)

sc, root, M, blob = R.sc, R.root, R.M, R.blob
bpy.context.view_layer.update()


def center(o):
    return sum((o.matrix_world @ Vector(c) for c in o.bound_box), Vector()) / 8


def pivot(name, loc, parent):
    e = bpy.data.objects.new(name, None); sc.collection.objects.link(e)
    e.parent = parent; e.location = loc
    return e


neck = pivot('neck', (0, 0, 1.08), root)
sh = {s: pivot(f'shoulder{s}', (s * .29, 0, .98), root) for s in (-1, 1)}
bpy.context.view_layer.update()
el = {}
for s in (-1, 1):
    el[s] = pivot(f'elbow{s}', (0, 0, 0), sh[s])
    bpy.context.view_layer.update()
    el[s].matrix_world.translation = Vector((s * .36, -.02, .77))
    el[s].location = sh[s].matrix_world.inverted() @ Vector((s * .36, -.02, .77))
bpy.context.view_layer.update()

eyes = []
for o in [o for o in bpy.data.objects if o.parent is root and o.type in {'MESH', 'CURVE'}]:
    c = center(o)
    mats = {m.name for m in o.data.materials if m}
    if c.z > 1.1 and not (c.y > .15 and c.z < 1.25) and 'glass' not in mats:
        target = neck
        if mats & {'eyew', 'black', 'spec'} and abs(c.x) > .05:
            eyes.append(o)
    elif abs(c.x) > .27 and c.z < 1.1:
        s = -1 if c.x < 0 else 1
        target = el[s] if c.z < .75 else sh[s]
    else:
        continue
    mw = o.matrix_world.copy()
    o.parent = target
    o.matrix_world = mw
bpy.context.view_layer.update()
eye_scale = {o.name: o.scale.copy() for o in eyes}
print('parts: head', len(neck.children), '| arms', {s: (len(sh[s].children), len(el[s].children)) for s in sh},
      '| eyes', len(eyes), flush=True)

sc.render.fps = FPS
sc.render.image_settings.color_depth = '8'
R.cam.data.lens = 90   # чуть шире, чем в стоп-кадрах: место для взмаха рукой и прыжка
os.makedirs(FRAMES, exist_ok=True)


# ======================= движение =======================
def ss(t, a, b):
    x = min(1., max(0., (t - a) / (b - a)))
    return x * x * (3 - 2 * x)


TAU = 2 * math.pi
BLINKS = (0.8, 3.7, 6.4, 8.8)


def pose(f):
    t = (f - 1) / FPS
    # корпус: вполоборота -> к зрителю -> обратно; дыхание; прыжок с приседом
    yaw = math.radians(-28) * (1 - ss(t, 1.5, 2.5) + ss(t, 7.9, 9.1))
    bob = .006 * math.sin(TAU * t / 2.0)
    u = (t - 7.0) / .55
    hop = .14 * 4 * u * (1 - u) if 0 < u < 1 else 0.
    sq = 1.
    if 6.78 < t <= 7.0:
        sq = 1 - .07 * math.sin(math.pi * (t - 6.78) / .22)
    elif 7.55 <= t < 7.82:
        sq = 1 - .06 * math.sin(math.pi * (t - 7.55) / .27)
    root.rotation_euler = (0, 0, yaw)
    root.location = (0, 0, bob + hop)
    root.scale = (1 / math.sqrt(sq), 1 / math.sqrt(sq), sq)
    # голова: оглядывается в начале и в конце, слегка смотрит на зрителя, кивает
    look = math.radians(16) * math.sin(TAU * t / 2.5) * (1 - ss(t, 1.25, 2.0) + ss(t, 8.0, 8.75))
    neck.rotation_euler = (math.radians(3) * math.sin(TAU * t / 2.0), 0, look - .4 * yaw)
    # правая рука (s=-1): поднять, помахать, опустить
    r = ss(t, 2.3, 3.0) - ss(t, 6.3, 7.0)
    idle = math.radians(3) * math.sin(TAU * t / 2.0)
    up = hop / .14
    sh[-1].rotation_euler = (0, r * math.radians(80) + idle + up * math.radians(22) * (1 - r), 0)
    el[-1].rotation_euler = (0, r * (math.radians(72) + math.radians(17) * math.sin(TAU * (t - 3.0) * 1.5)), 0)
    # левая рука: покачивается, взлетает в прыжке
    sh[1].rotation_euler = (0, -idle - up * math.radians(28), 0)
    el[1].rotation_euler = (0, -up * math.radians(12), 0)
    # моргание
    closed = any(0 <= t - b < 3.5 / FPS for b in BLINKS)
    for o in eyes:
        s0 = eye_scale[o.name]
        o.scale = (s0.x, s0.y, s0.z * (.12 if closed else 1.))
    # тень под ногами сжимается в прыжке
    k = .62 * (1 - .35 * up)
    blob.scale = (k, k, 1)


f0, f1 = (int(x) for x in os.environ.get('TIMUR_FRAME_RANGE', f'1-{N}').split('-'))
step = int(os.environ.get('TIMUR_FRAME_STEP', 1))
t0 = time.time(); done = 0
for f in range(f0, f1 + 1, step):
    if os.path.exists(frame_path(f)):
        continue
    sc.frame_set(f)
    pose(f)
    sc.render.filepath = frame_path(f)
    bpy.ops.render.render(write_still=True)
    done += 1
    print(f'frame {f}/{f1} done, {(time.time() - t0) / done:.1f} s/frame', flush=True)
print('frames finished', flush=True)
