import bpy, math, sys
from mathutils import Vector

OUT = sys.argv[-1] if sys.argv[-1].endswith('/') else '/tmp/'
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
root = bpy.data.objects.new('root', None); sc.collection.objects.link(root)

def mat(name, col, rough=.5, emit=None, glass=False, metal=0.):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*col, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if emit:
        b.inputs['Emission Color'].default_value = (*emit, 1); b.inputs['Emission Strength'].default_value = 4
    if glass:
        b.inputs['Transmission Weight'].default_value = 1.; b.inputs['IOR'].default_value = 1.02
        b.inputs['Roughness'].default_value = .03
    return m

def hexc(h):
    h = h.lstrip('#'); c = [int(h[i:i+2], 16)/255 for i in (0, 2, 4)]
    return tuple(((x+0.055)/1.055)**2.4 if x > 0.04045 else x/12.92 for x in c)

M = {k: mat(k, hexc(v[0]), *v[1:]) for k, v in {
    'white': ('#f3f5f9', .45), 'orange': ('#f2741c', .45), 'blue': ('#3f7fe0', .4), 'teal': ('#3aa6a0', .3),
    'grey': ('#6c7480', .5), 'skin': ('#f2c09a', .6), 'hair': ('#18161e', .55), 'black': ('#0c0c10', .3),
    'red': ('#d83434', .45), 'pink': ('#ff8f9a', .8), 'mouth': ('#7a1f2b', .5), 'silver': ('#c9ced6', .3)}.items()}
M['glass'] = mat('glass', hexc('#dff1ff'), glass=True)
M['eyew'] = mat('eyew', hexc('#ffffff'), .3)
M['cyan'] = mat('cyan', hexc('#4ff4ff'), .2, emit=hexc('#29e8ff'))
M['spec'] = mat('spec', hexc('#ffffff'), .2, emit=hexc('#ffffff'))

def link(o, m, smooth=True):
    o.data.materials.append(m); o.parent = root
    if smooth and hasattr(o.data, 'polygons'):
        for p in o.data.polygons: p.use_smooth = True
    return o

def sphere(loc, r, m, scale=(1, 1, 1), rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=48, ring_count=24, rotation=rot)
    o = bpy.context.object; o.scale = scale; return link(o, m)

def box(loc, size, m, bevel=.04, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object; o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        md = o.modifiers.new('b', 'BEVEL'); md.width = bevel; md.segments = 5
    return link(o, m)

def cyl(loc, r, depth, m, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, location=loc, rotation=rot, vertices=48)
    return link(bpy.context.object, m)

def capsule(a, b, r, m):
    a, b = Vector(a), Vector(b); d = b - a
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=d.length, location=(a+b)/2, vertices=48)
    o = bpy.context.object; o.rotation_mode = 'QUATERNION'; o.rotation_quaternion = d.to_track_quat('Z', 'Y')
    link(o, m); sphere(a, r, m); sphere(b, r, m); return o

def ring(loc, r, minor, m, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(location=loc, major_radius=r, minor_radius=minor, rotation=rot, major_segments=64, minor_segments=16)
    return link(bpy.context.object, m)

def band(a, b, t, r, m):  # ring around a limb at fraction t
    a, b = Vector(a), Vector(b); p = a.lerp(b, t); d = (b - a).normalized()
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=.05, location=p, vertices=48)
    o = bpy.context.object; o.rotation_mode = 'QUATERNION'; o.rotation_quaternion = d.to_track_quat('Z', 'Y'); return link(o, m)

def cone(loc, r, depth, m, rot):
    bpy.ops.mesh.primitive_cone_add(radius1=r, depth=depth, location=loc, rotation=rot, vertices=24)
    return link(bpy.context.object, m)

# ---------------- body ----------------
# legs: hip -> knee -> ankle
for s in (-1, 1):
    hip, knee, ank = (s*.11, 0, .56), (s*.12, -.01, .33), (s*.12, 0, .13)
    capsule(hip, knee, .085, M['white']); capsule(knee, ank, .08, M['white'])
    band(hip, knee, .45, .087, M['orange'])
    sphere((s*.12, -.07, .34), .07, M['grey'], scale=(1.15, .7, 1))           # knee pad
    box((s*.12, -.03, .08), (.17, .26, .16), M['white'], .05)                  # boot
    box((s*.12, -.03, .1), (.175, .265, .03), M['red'], .01)                   # red stripe
    box((s*.12, -.03, .01), (.18, .28, .04), M['grey'], .015)                  # sole
# torso
box((0, 0, .79), (.46, .3, .5), M['white'], .11)
for s in (-1, 1):
    box((s*.19, -.005, .8), (.09, .305, .46), M['orange'], .04)               # orange side panels
box((0, 0, .56), (.42, .29, .07), M['blue'], .03)                              # belt
sphere((0, -.155, .86), .07, M['eyew'], scale=(1, .25, 1))
ring((0, -.17, .86), .05, .016, M['teal'], rot=(math.pi/2, 0, 0)); sphere((0, -.17, .86), .02, M['teal'], scale=(1, .4, 1))
for s in (-1, 1):                                                               # blue hoses
    bpy.ops.curve.primitive_bezier_curve_add(location=(0, 0, 0)); c = bpy.context.object
    sp = c.data.splines[0]; p0, p1 = sp.bezier_points
    p0.co = (s*.06, -.16, .76); p0.handle_left = (s*.06, -.16, .8); p0.handle_right = (s*.12, -.2, .7)
    p1.co = (s*.12, -.15, .6); p1.handle_left = (s*.16, -.2, .66); p1.handle_right = (s*.1, -.12, .56)
    c.data.bevel_depth = .024; c.data.bevel_resolution = 4; link(c, M['blue'], False)
# air tank on back
cyl((0, .2, .86), .1, .42, M['teal']); sphere((0, .2, 1.07), .1, M['teal']); sphere((0, .2, .65), .1, M['teal'])
cyl((0, .2, 1.18), .035, .08, M['silver'])
for s in (-1, 1): box((s*.1, .16, .9), (.03, .06, .34), M['grey'], .01)
# arms: shoulder -> elbow -> wrist
for s in (-1, 1):
    sh, el, wr = (s*.29, 0, .98), (s*.36, -.02, .77), (s*.38, -.05, .58)
    sphere(sh, .095, M['white']); capsule(sh, el, .075, M['white']); capsule(el, wr, .07, M['white'])
    band(sh, el, .25, .078, M['orange']); band(el, wr, .85, .075, M['blue'])
    sphere((s*.385, -.06, .5), .075, M['grey'], scale=(1, .85, 1.1))           # glove
    if s == -1: band(el, wr, .7, .077, M['cyan'])                              # cyan bracelet (his right wrist)
# neck ring
ring((0, 0, 1.06), .2, .045, M['blue'])
# ---------------- head ----------------
H = Vector((0, 0, 1.37))
sphere(H, .3, M['skin'], scale=(1, .95, 1))
sphere(H + Vector((0, .05, .07)), .31, M['hair'], scale=(1.02, 1, .9))         # hair cap
def spike(dirv, r, depth, off=.22):
    d = Vector(dirv).normalized(); p = H + Vector((0, .05, .07)) + d*off
    bpy.ops.mesh.primitive_cone_add(radius1=r, depth=depth, location=p + d*depth*.35, vertices=24)
    o = bpy.context.object; o.rotation_mode = 'QUATERNION'; o.rotation_quaternion = d.to_track_quat('Z', 'Y'); link(o, M['hair'])
for d, r, dep in [((0,.1,1),.12,.32),((-.45,.1,.9),.11,.3),((.45,.15,.9),.11,.3),((-.2,-.25,.95),.1,.28),((.25,-.2,.95),.1,.28),
                  ((-.8,.2,.55),.1,.26),((.8,.25,.5),.1,.26),((0,.7,.7),.12,.3),((-.5,.65,.5),.11,.28),((.5,.6,.55),.11,.28),
                  ((-.9,.1,.1),.08,.2),((.9,.15,.05),.08,.2),((0,.95,.2),.11,.26)]:
    spike(d, r*.85, dep*.55)
for x, rz in [(-.13, .4), (-.03, 0), (.08, -.3), (.16, -.6)]:                  # fringe
    cone(H + Vector((x, -.23, .17)), .075, .2, M['hair'], (math.pi - .8, 0, rz))
for s in (-1, 1):
    sphere(H + Vector((s*.105, -.255, .02)), .07, M['eyew'], scale=(.95, .45, 1.2))
    sphere(H + Vector((s*.1, -.29, .015)), .036, M['black'], scale=(1, .5, 1.1))
    sphere(H + Vector((s*.09, -.31, .04)), .012, M['spec'])
    box(H + Vector((s*.11, -.265, .13)), (.09, .025, .02), M['hair'], .008, rot=(0, s*.25, 0))
    sphere(H + Vector((s*.18, -.24, -.07)), .04, M['pink'], scale=(1.2, .3, .7))
sphere(H + Vector((0, -.29, -.04)), .02, M['skin'])                            # nose
sphere(H + Vector((0, -.27, -.13)), .055, M['mouth'], scale=(1.1, .35, .45))    # smile
box(H + Vector((0, -.29, -.115)), (.09, .01, .022), M['eyew'], .005)           # teeth
# helmet
sphere(H + Vector((0, 0, .03)), .47, M['glass'])

# ---------------- render setup ----------------
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
w.node_tree.nodes['Background'].inputs[0].default_value = (1, 1, 1, 1); w.node_tree.nodes['Background'].inputs[1].default_value = .9
bpy.ops.object.light_add(type='SUN', location=(-3, -4, 6), rotation=(.9, 0, -.6)); bpy.context.object.data.energy = 3.2
bpy.ops.object.light_add(type='AREA', location=(3, -3, 2)); a = bpy.context.object; a.data.energy = 300; a.data.size = 3
a.rotation_euler = (Vector((0, 0, 1)) - a.location).to_track_quat('-Z', 'Y').to_euler()
bpy.ops.object.light_add(type='AREA', location=(0, 3, 3)); a = bpy.context.object; a.data.energy = 250; a.data.size = 2
a.rotation_euler = (Vector((0, 0, 1)) - a.location).to_track_quat('-Z', 'Y').to_euler()
bpy.ops.object.camera_add(location=(0, -7.2, 1.0)); cam = bpy.context.object; sc.camera = cam
cam.rotation_euler = (math.radians(90), 0, 0); cam.data.lens = 108
sc.render.engine = 'CYCLES'; sc.cycles.samples = 48; sc.cycles.use_denoising = True; sc.cycles.device = 'CPU'
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x, sc.render.resolution_y = 800, 1100
sc.render.use_freestyle = True; sc.render.line_thickness_mode = 'ABSOLUTE'; sc.render.line_thickness = 2.6
vl = sc.view_layers[0]; vl.use_freestyle = True
fs = vl.freestyle_settings; ls = fs.linesets[0] if len(fs.linesets) else fs.linesets.new('L')
ls.select_silhouette = True; ls.select_border = True; ls.select_crease = False
ls.linestyle = ls.linestyle or bpy.data.linestyles.new('LS')
ls.linestyle.color = (0.05, 0.05, 0.07); ls.linestyle.thickness = 3.2
for name, ang in [('front', 0), ('three_quarter', -35), ('side', -90), ('back', 180)]:
    root.rotation_euler = (0, 0, math.radians(ang))
    sc.render.filepath = OUT + f'timur_{name}.png'
    bpy.ops.render.render(write_still=True)
    print('rendered', name, flush=True)
