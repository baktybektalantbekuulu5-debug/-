"""Звук: музыка (из assets/music или синтезируется локально) и эффекты (assets/sfx или синтез FFmpeg)."""
import random
import subprocess
from pathlib import Path

from core.logger import get_logger

log = get_logger("audio")
ROOT = Path(__file__).resolve().parent.parent
AUDIO_EXT = (".mp3", ".wav", ".ogg", ".flac", ".m4a")

SFX_FILTERS = {   # синтез эффектов через lavfi (без внешних файлов и лицензий)
    "impact": ("aevalsrc='0.95*sin(2*PI*(70-45*t)*t)*exp(-5*t)+0.5*(random(0)-0.5)*exp(-14*t)':d=1.2:s=48000"),
    "whoosh": ("anoisesrc=d=1.1:c=pink:a=0.6:r=48000,highpass=f=500,lowpass=f=4500,"
               "afade=t=in:st=0:d=0.45,afade=t=out:st=0.45:d=0.65"),
    "landing": ("aevalsrc='0.9*sin(2*PI*(90-50*t)*t)*exp(-9*t)+0.3*(random(0)-0.5)*exp(-25*t)':d=0.7:s=48000"),
    "screech": ("anoisesrc=d=1.4:c=white:a=0.35:r=48000,highpass=f=2200,lowpass=f=7000,tremolo=f=16:d=0.7,"
                "afade=t=in:st=0:d=0.2,afade=t=out:st=0.9:d=0.5"),
}
EVENT_SFX = {"crash": "impact", "jump": "whoosh", "landing": "landing", "loss_of_control": "screech"}


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg: " + r.stderr[-500:])


def sfx_file(name: str, ffmpeg: str, cache_dir: Path) -> Path:
    user = sorted((ROOT / "assets" / "sfx").glob(f"{name}*"))
    user = [p for p in user if p.suffix.lower() in AUDIO_EXT]
    if user:
        return random.choice(user)
    out = cache_dir / f"sfx_{name}.wav"
    if not out.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        _run([ffmpeg, "-y", "-f", "lavfi", "-i", SFX_FILTERS[name], "-ar", "48000", "-ac", "2", str(out)])
    return out


def music_file(ffmpeg: str, cache_dir: Path, length: float) -> Path:
    user = [p for p in sorted((ROOT / "assets" / "music").glob("*")) if p.suffix.lower() in AUDIO_EXT]
    if user:
        return random.choice(user)
    out = cache_dir / "music_synth.wav"
    if out.exists():
        return out
    cache_dir.mkdir(parents=True, exist_ok=True)
    # 128 BPM: кик + хэт + бас + арпеджио (Am pentatonic). Генерируется локально.
    beat = 60 / 128
    q = beat / 2
    arp = "+".join(f"0.07*sin(2*PI*{f}*t)*eq(mod(floor(t/{q:.6f}),4),{i})" for i, f in enumerate((220.0, 261.63, 329.63, 392.0)))
    expr = (f"0.55*sin(2*PI*(48+110*exp(-35*mod(t,{beat:.6f})))*mod(t,{beat:.6f}))*exp(-6*mod(t,{beat:.6f}))"
            f"+0.10*(random(0)-0.5)*exp(-45*mod(t+{q:.6f},{beat:.6f}))"
            f"+0.16*sin(2*PI*55*t)*(0.6+0.4*sin(2*PI*t/{beat*2:.6f}))"
            f"+({arp})*exp(-4*mod(t,{q:.6f}))")
    _run([ffmpeg, "-y", "-f", "lavfi", "-i", f"aevalsrc='{expr}':d=32:s=48000", "-ac", "2", str(out)])
    log.info("синтезирована фоновая музыка (положите свои треки в assets/music для лучшего результата)")
    return out
