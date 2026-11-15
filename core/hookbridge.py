"""Мост между главным приложением UniBoard и процессом-перехватчиком.

  * создаёт mmap-протокол и запускает core/hook_helper.py отдельным процессом;
  * поток-читатель забирает события из кольцевого буфера и отдаёт рабочему
    потоку приложения (как раньше делал внутрипроцессный хук);
  * pump() (из цикла poll главного потока) обновляет флаги поглощения,
    горячие клавиши и heartbeat;
  * при завершении посылает команду, а при молчании перехватчика — завершает его.
"""
import ctypes
import logging
import mmap
import os
import struct
import subprocess
import sys
import threading
from pathlib import Path

from . import hookproto as P
from . import kbd
from .config import app_dir

log = logging.getLogger("uniboard")

CREATE_NO_WINDOW = 0x08000000
MOD_BITS = (("shift", P.MOD_SHIFT), ("ctrl", P.MOD_CTRL),
            ("alt", P.MOD_ALT), ("win", P.MOD_WIN))


def _bits_to_mods(bits):
    mods = set()
    for name, bit in MOD_BITS:
        if bits & bit:
            mods.add(name)
    return frozenset(mods)


class HookBridge:
    def __init__(self, app):
        self.app = app
        self.mm = None
        self._file = None
        self.path = None
        self.proc = None
        self._stop = threading.Event()
        self._reader = None
        self._last_flags = -1
        self._hb = 0
        self._spawns = 0
        self._status_seen = 0

    # --- запуск / остановка ---------------------------------------------------

    def start(self):
        self.path = str(app_dir() / ("hook_%d.mmap" % os.getpid()))
        self.mm, self._file = P.map_file(self.path)
        P.write_u32(self.mm, P.OFF_MAGIC, P.MAGIC)
        self.write_hotkeys()
        self._spawn_helper()
        self._reader = threading.Thread(target=self._read_loop,
                                        name="UniBoard-HookReader", daemon=True)
        self._reader.start()

    def _helper_script(self):
        return Path(__file__).resolve().parent / "hook_helper.py"

    def _spawn_helper(self):
        self._spawns += 1
        cmd = [sys.executable, str(self._helper_script()), self.path]
        self.proc = subprocess.Popen(cmd, cwd=str(self._helper_script().parent.parent),
                                     creationflags=CREATE_NO_WINDOW,
                                     close_fds=True)
        log.info("Перехватчик запущен (PID %s)", self.proc.pid)

    def stop(self):
        if self.mm:
            try:
                P.write_u32(self.mm, P.OFF_SHUTDOWN, 0xFFFFFFFF)
            except Exception:
                pass
        self._stop.set()
        if self.proc:
            try:
                self.proc.wait(timeout=2)
            except Exception:
                try:
                    self.proc.terminate()
                except Exception:
                    pass
        if self._reader:
            self._reader.join(timeout=1)
        try:
            if self.mm:
                self.mm.close()
            if self._file:
                self._file.close()
            if self.path:
                Path(self.path).unlink(missing_ok=True)
        except Exception:
            pass

    # --- поток-читатель ---------------------------------------------------------

    def _read_loop(self):
        unpack = struct.unpack_from
        mm = self.mm
        while not self._stop.is_set():
            try:
                wi = P.read_u32(mm, P.OFF_WIDX)
                ri = P.read_u32(mm, P.OFF_RIDX)
                n = (wi - ri) & 0xFFFFFFFF
                if n == 0:
                    self._stop.wait(0.003)
                    continue
                if n > P.CAP:  # не успевали читать — пропускаем старое
                    ri = wi - P.CAP
                    n = P.CAP
                P.write_u32(mm, P.OFF_RIDX, ri + n)  # помечаем до обработки
                for i in range(n):
                    kind, vk, scan, bits = unpack("<IIII", mm, P.record_offset(ri + i))
                    if kind == 0:
                        down = bool(bits & P.MOD_DOWN)
                        ev = kbd.KeyEv(vk, scan, down, False,
                                       _bits_to_mods(bits), bool(bits & P.MOD_CAPS))
                        self.app.worker_q.put(("key", ev))
                    else:
                        x = ctypes_int32(scan)
                        y = ctypes_int32(bits)
                        self.app.worker_q.put(("mouse_click", (x, y)))
            except Exception:
                log.exception("Ошибка чтения кольцевого буфера")
                self._stop.wait(0.2)

    # --- служебные записи (вызывается из главного потока) ------------------------

    def pump(self):
        """Обновить флаги/heartbeat; присмотреть за перехватчиком."""
        try:
            sh = self.app.shared
            flags = 0
            if sh.popup_visible:
                flags |= P.FLAG_POPUP
            if self.app.cfg.get("tab_accept", True):
                flags |= P.FLAG_TAB
            if self.app.cfg.get("enter_accept", False):
                flags |= P.FLAG_ENTER
            if sh.cand_count > 0:
                flags |= P.FLAG_CANDS
            if flags != self._last_flags:
                P.write_u32(self.mm, P.OFF_FLAGS, flags)
                self._last_flags = flags
            self._hb = (self._hb + 1) & 0x7FFFFFFF
            P.write_u32(self.mm, P.OFF_HEARTBEAT, self._hb)

            if self._status_seen == 0 and self.proc:
                st = P.read_u32(self.mm, P.OFF_STATUS)
                if st == 1:
                    self._status_seen = 1
                elif st == 2:
                    self._status_seen = 2
                    log.error("Перехватчик не смог установить LL-хуки (статус 2)")

            if self.proc and self.proc.poll() is not None and not self._stop.is_set():
                log.warning("Перехватчик завершился (код %s)", self.proc.returncode)
                if self._spawns < 3:
                    self._spawn_helper()
                else:
                    log.error("Перехватчик не запускается после 3 попыток — "
                              "подсказки и горячие клавиши отключены до перезапуска")
        except Exception:
            log.exception("Ошибка pump() моста перехватчика")

    def write_hotkeys(self):
        if not self.mm:
            return
        try:
            for i, hk in enumerate(self.app.hotkeys[:2]):
                mask = 0
                for name, bit in MOD_BITS:
                    if name in hk.mods:
                        mask |= bit
                off = P.OFF_HK + i * 8
                struct.pack_into("<II", self.mm, off, hk.vk, mask)
            for i in range(len(self.app.hotkeys[:2]), 2):
                struct.pack_into("<II", self.mm, P.OFF_HK + i * 8, 0, 0)
        except Exception:
            log.exception("Не удалось записать горячие клавиши в протокол")


def ctypes_int32(v):
    v &= 0xFFFFFFFF
    return v if v < 0x80000000 else v - 0x100000000
