"""HQ-рендер Тимура на видеокарте: EEVEE, 1080x1920.

Модель берётся из timur.py (часть до блока "render setup"), здесь только свет/камера/рендер.
Запуск:  blender -b --factory-startup --python out/blender/render_hq.py
"""
import bpy, gpu, math, os
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
# Необязательные переменные окружения: TIMUR_OUT (папка), TIMUR_VIEWS (front,side,...), TIMUR_SAMPLES, TIMUR_GLASS_RIM
OUT = os.environ.get('TIMUR_OUT') or os.path.join(HERE, 'hq')
os.makedirs(OUT, exist_ok=True)
SAMPLES = int(os.environ.get('TIMUR_SAMPLES', 256))
GLASS_RIM = float(os.environ.get('TIMUR_GLASS_RIM', .45))
ONLY = [v for v in os.environ.get('TIMUR_VIEWS', '').split(',') if v]

# --- модель: исполняем timur.py до блока рендера ---
src = open(os.path.join(HERE, 'timur.py'), encoding='utf-8').read()
model_src = src.split('# ---------------- render setup')[0]
ns = {'__name__': 'timur_model'}
exec(compile(model_src, 'timur.py', 'exec'), ns)
sc, root, M = bpy.context.scene, ns['root'], ns['M']

# --- стекло шлема: преломление через рейтрейсинг EEVEE ---
#     В EEVEE преломляющая сфера скрывает голову, поэтому стекло — полупрозрачный alpha-blend с бликом.
g = M['glass']
#     Оттенок умножающий (Transparent BSDF), чтобы стекло не высветляло чёрные волосы; блик — только у края сферы.
nt = g.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
n_out = nt.nodes.new('ShaderNodeOutputMaterial')
n_tr = nt.nodes.new('ShaderNodeBsdfTransparent'); n_tr.inputs['Color'].default_value = (.80, .90, 1., 1)
n_gl = nt.nodes.new('ShaderNodeBsdfGlossy'); n_gl.inputs['Roughness'].default_value = .05
n_lw = nt.nodes.new('ShaderNodeLayerWeight'); n_lw.inputs['Blend'].default_value = .12
n_mul = nt.nodes.new('ShaderNodeMath'); n_mul.operation = 'MULTIPLY'; n_mul.inputs[1].default_value = GLASS_RIM
n_mix = nt.nodes.new('ShaderNodeMixShader')
nt.links.new(n_lw.outputs['Facing'], n_mul.inputs[0])
nt.links.new(n_mul.outputs[0], n_mix.inputs['Fac'])
nt.links.new(n_tr.outputs[0], n_mix.inputs[1])
nt.links.new(n_gl.outputs[0], n_mix.inputs[2])
nt.links.new(n_mix.outputs[0], n_out.inputs['Surface'])
if hasattr(g, 'surface_render_method'):
    g.surface_render_method = 'BLENDED'
else:
    g.blend_method = 'BLEND'
for attr, val in [('use_transparency_overlap', False), ('show_transparent_back', False), ('use_backface_culling', True)]:
    if hasattr(g, attr):
        setattr(g, attr, val)

# --- мягкая тень-пятно под ногами (диск с радиальным затуханием; в контур Freestyle не попадает) ---
sm = bpy.data.materials.new('blob_shadow'); sm.use_nodes = True
st = sm.node_tree
for n in list(st.nodes):
    st.nodes.remove(n)
s_out = st.nodes.new('ShaderNodeOutputMaterial')
s_tr = st.nodes.new('ShaderNodeBsdfTransparent')
s_em = st.nodes.new('ShaderNodeEmission'); s_em.inputs['Color'].default_value = (.10, .11, .16, 1)
s_mix = st.nodes.new('ShaderNodeMixShader')
s_tc = st.nodes.new('ShaderNodeTexCoord')
s_gr = st.nodes.new('ShaderNodeTexGradient'); s_gr.gradient_type = 'SPHERICAL'
s_pow = st.nodes.new('ShaderNodeMath'); s_pow.operation = 'POWER'; s_pow.inputs[1].default_value = 1.6
s_mul = st.nodes.new('ShaderNodeMath'); s_mul.operation = 'MULTIPLY'; s_mul.inputs[1].default_value = .55
st.links.new(s_tc.outputs['Object'], s_gr.inputs['Vector'])
st.links.new(s_gr.outputs['Fac'], s_pow.inputs[0])
st.links.new(s_pow.outputs[0], s_mul.inputs[0])
st.links.new(s_mul.outputs[0], s_mix.inputs['Fac'])
st.links.new(s_tr.outputs[0], s_mix.inputs[1])
st.links.new(s_em.outputs[0], s_mix.inputs[2])
st.links.new(s_mix.outputs[0], s_out.inputs['Surface'])
if hasattr(sm, 'surface_render_method'):
    sm.surface_render_method = 'BLENDED'
else:
    sm.blend_method = 'BLEND'
bpy.ops.mesh.primitive_circle_add(radius=1, fill_type='NGON', vertices=64, location=(0, 0, -.012))
blob = bpy.context.object; blob.scale = (.62, .62, 1); blob.data.materials.append(sm)
no_line = bpy.data.collections.new('no_outline'); sc.collection.children.link(no_line)
for c in list(blob.users_collection):
    c.objects.unlink(blob)
no_line.objects.link(blob)

# --- мир и свет (как в timur.py) ---
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
bg = w.node_tree.nodes['Background']
bg.inputs[0].default_value = (1, 1, 1, 1); bg.inputs[1].default_value = .9
bpy.ops.object.light_add(type='SUN', location=(-3, -4, 6), rotation=(.9, 0, -.6))
sun = bpy.context.object; sun.data.energy = 3.2; sun.data.angle = math.radians(3)
for loc, energy, size in [((3, -3, 2), 300, 3), ((0, 3, 3), 250, 2)]:
    bpy.ops.object.light_add(type='AREA', location=loc); a = bpy.context.object
    a.data.energy = energy; a.data.size = size
    a.rotation_euler = (Vector((0, 0, 1)) - a.location).to_track_quat('-Z', 'Y').to_euler()

# --- камера под вертикальный кадр 9:16 ---
bpy.ops.object.camera_add(location=(0, -7.2, .95)); cam = bpy.context.object; sc.camera = cam
cam.rotation_euler = (math.radians(90), 0, 0); cam.data.lens = 104

# --- рендер: EEVEE (GPU) ---
sc.render.engine = 'BLENDER_EEVEE'
ee = sc.eevee
ee.taa_render_samples = SAMPLES
for attr, val in [('use_raytracing', True), ('use_shadows', True), ('shadow_ray_count', 3), ('shadow_step_count', 8),
                  ('use_gtao', True), ('use_fast_gi', True)]:
    if hasattr(ee, attr):
        try: setattr(ee, attr, val)
        except Exception as e: print('skip', attr, e)
if hasattr(ee, 'ray_tracing_options'):
    ee.ray_tracing_options.resolution_scale = '1'
    ee.ray_tracing_options.use_denoise = True
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x, sc.render.resolution_y = 1080, 1920
sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_depth = '16'
sc.render.filter_size = 1.5

# --- контур (Freestyle), толщина под 1920 px по высоте ---
sc.render.use_freestyle = True; sc.render.line_thickness_mode = 'ABSOLUTE'; sc.render.line_thickness = 3.0
vl = sc.view_layers[0]; vl.use_freestyle = True
fs = vl.freestyle_settings; ls = fs.linesets[0] if len(fs.linesets) else fs.linesets.new('L')
ls.select_silhouette = True; ls.select_border = True; ls.select_crease = False
ls.select_by_collection = True; ls.collection = no_line; ls.collection_negation = 'EXCLUSIVE'
ls.linestyle = ls.linestyle or bpy.data.linestyles.new('LS')
ls.linestyle.color = (0.05, 0.05, 0.07); ls.linestyle.thickness = 2.2

VIEWS = [('front', 0), ('three_quarter', -35), ('side', -90), ('back', 180)]
if __name__ != '__main__':   # импортирован из animate_hq.py: сцена готова, кадры не рендерим
    VIEWS = []
for name, ang in VIEWS:
    if ONLY and name not in ONLY:
        continue
    root.rotation_euler = (0, 0, math.radians(ang))
    sc.render.filepath = os.path.join(OUT, f'timur_{name}_1080x1920.png')
    bpy.ops.render.render(write_still=True)
    print('rendered', name, flush=True)
    try:  # GPU-контекст в фоновом режиме появляется только после первого рендера
        print('GPU:', gpu.platform.vendor_get(), '|', gpu.platform.renderer_get(), '|', gpu.platform.backend_type_get(), flush=True)
    except Exception as e:
        print('GPU info unavailable:', e, flush=True)
