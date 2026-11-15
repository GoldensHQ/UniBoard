"""Протокол обмена между главным процессом UniBoard и процессом-перехватчиком.

Перехват клавиатуры живёт в ОТДЕЛЬНОМ мини-процессе (см. hook_helper.py), чтобы
любые проблемы главного приложения (tkinter, вставка, ресурсы) не могли
заморозить ввод всей системы. Обмен — через общий mmap-файл:

  * главный процесс пишет: флаги состояния (что «поглощать»), горячие клавиши,
    heartbeat; читает события клавиш из кольцевого буфера;
  * перехватчик читает флаги/горячие клавиши, пишет события в кольцевой буфер;
    его колбэк не делает НИКАКИХ блокирующих вызовов.

Все числа — little-endian uint32, если не указано иное.
"""
import mmap
import os
import struct

MAGIC = 0x55424F4B          # "UBOK"
SIZE = 262144               # 256 КБ

OFF_MAGIC = 0
OFF_FLAGS = 4               # биты FLAG_*: что перехватчик должен поглощать
OFF_HEARTBEAT = 8           # главный процесс тикает; 0 изменений ~4 с => выход
OFF_SHUTDOWN = 12           # 0xFFFFFFFF — команда завершиться
OFF_STATUS = 16             # 1 = хуки установлены, 2 = ошибка установки
OFF_HK = 24                 # 2 слота по 8 байт: (vk, mask_mods); vk=0 — пусто
OFF_WIDX = 40               # индекс записи (пишет перехватчик)
OFF_RIDX = 44               # индекс чтения (пишет главный)
RING_OFF = 64               # кольцевой буфер записей
REC = 16                    # размер записи: kind, vk, scan, bits
CAP = (SIZE - RING_OFF) // REC

# Флаги поглощения (OFF_FLAGS)
FLAG_POPUP = 1              # окно подсказки открыто: Esc/↑/↓ поглощать
FLAG_TAB = 2                # Tab разрешено использовать как «вставить»
FLAG_ENTER = 4              # Enter тоже вставляет подсказку
FLAG_CANDS = 8              # есть кандидаты (Tab/Enter имеют смысл)

# Биты модификаторов
MOD_SHIFT = 1
MOD_CTRL = 2
MOD_ALT = 4
MOD_WIN = 8
MOD_CAPS = 16
MOD_DOWN = 256              # в записи события: клавиша нажата (down)


def map_file(path, size=SIZE):
    """Открыть/создать mmap-файл протокола (чтение-запись)."""
    if not os.path.exists(path) or os.path.getsize(path) != size:
        with open(path, "wb") as f:
            f.write(b"\x00" * size)
            f.flush()
    f = open(path, "r+b")
    return mmap.mmap(f.fileno(), size, access=mmap.ACCESS_WRITE), f


def write_u32(mm, off, value):
    struct.pack_into("<I", mm, off, int(value) & 0xFFFFFFFF)


def read_u32(mm, off):
    return struct.unpack_from("<I", mm, off)[0]


def record_offset(index):
    return RING_OFF + (index % CAP) * REC
