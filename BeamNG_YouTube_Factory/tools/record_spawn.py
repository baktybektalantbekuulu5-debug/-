"""Запись точки старта для карты из РЕАЛЬНОЙ игры (калибровка).

Использование:
  python tools/record_spawn.py west_coast_usa
1. Скрипт запускает BeamNG.drive (или подключается к уже запущенной под управлением beamngpy).
2. В игре загрузите нужную карту в режиме «Свободная езда», поставьте машину в нужное место
   (для трюков — ровная площадка ≥ 400 м, для езды по дороге — на дороге) и разверните её в нужную сторону.
3. Вернитесь в консоль и нажмите Enter — позиция и направление сохранятся в config/user_maps.json.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_director.catalog import Catalog  # noqa: E402
from core.settings import Settings  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    level = sys.argv[1]
    s = Settings()
    from beamngpy import BeamNGpy
    bng = BeamNGpy(s.get("beamng.host"), int(s.get("beamng.port")), home=s.get("paths.beamng_home") or None,
                   user=s.get("paths.beamng_user") or None)
    bng.open(launch=True)
    try:
        input(f"\nЗагрузите карту «{level}» (Свободная езда), поставьте машину на место и нажмите Enter… ")
        vehicles = bng.vehicles.get_current()
        if not vehicles:
            print("В игре нет машин. Заспавните машину и повторите.")
            return 1
        vid, veh = next(iter(vehicles.items()))
        veh.connect(bng)
        veh.sensors.poll("state")
        st = veh.sensors["state"]
        pos, d = [round(x, 3) for x in st["pos"]], st["dir"]
        spawn = {"pos": pos, "dir": [round(d[0], 4), round(d[1], 4)], "source": "record_spawn.py", "verified": True}
        Catalog().save_user_spawn(level, spawn)
        print(f"Сохранено для «{level}»: {spawn}")
    finally:
        bng.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
