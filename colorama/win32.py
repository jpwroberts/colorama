# Copyright Jonathan Hartley 2013. BSD 3-Clause license, see LICENSE file.
import platform

# from winbase.h
STDOUT = -11
STDERR = -12
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

try:
    import ctypes
    from ctypes import LibraryLoader
    windll = LibraryLoader(ctypes.WinDLL)
    from ctypes import wintypes
except (AttributeError, ImportError):
    windll = None
    SetConsoleTextAttribute = lambda *_: None
    winapi_test = lambda *_: None
    vt_available = lambda *_: None
    reset_enable_vt = lambda *_: None
else:
    from ctypes import byref, Structure, c_char, POINTER

    COORD = wintypes._COORD

    # Track whether we've enabled Win 10 virtual terminal,
    # and what the original mode was set to.
    we_enabled_windows_vt = False
    old_mode_value = None


    class CONSOLE_SCREEN_BUFFER_INFO(Structure):
        """struct in wincon.h."""
        _fields_ = [
            ("dwSize", COORD),
            ("dwCursorPosition", COORD),
            ("wAttributes", wintypes.WORD),
            ("srWindow", wintypes.SMALL_RECT),
            ("dwMaximumWindowSize", COORD),
        ]
        def __str__(self):
            return '(%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d)' % (
                self.dwSize.Y, self.dwSize.X
                , self.dwCursorPosition.Y, self.dwCursorPosition.X
                , self.wAttributes
                , self.srWindow.Top, self.srWindow.Left, self.srWindow.Bottom, self.srWindow.Right
                , self.dwMaximumWindowSize.Y, self.dwMaximumWindowSize.X
            )

    _GetStdHandle = windll.kernel32.GetStdHandle
    _GetStdHandle.argtypes = [
        wintypes.DWORD,
    ]
    _GetStdHandle.restype = wintypes.HANDLE

    _GetConsoleScreenBufferInfo = windll.kernel32.GetConsoleScreenBufferInfo
    _GetConsoleScreenBufferInfo.argtypes = [
        wintypes.HANDLE,
        POINTER(CONSOLE_SCREEN_BUFFER_INFO),
    ]
    _GetConsoleScreenBufferInfo.restype = wintypes.BOOL

    _SetConsoleTextAttribute = windll.kernel32.SetConsoleTextAttribute
    _SetConsoleTextAttribute.argtypes = [
        wintypes.HANDLE,
        wintypes.WORD,
    ]
    _SetConsoleTextAttribute.restype = wintypes.BOOL

    _SetConsoleCursorPosition = windll.kernel32.SetConsoleCursorPosition
    _SetConsoleCursorPosition.argtypes = [
        wintypes.HANDLE,
        COORD,
    ]
    _SetConsoleCursorPosition.restype = wintypes.BOOL

    _GetConsoleMode = windll.kernel32.GetConsoleMode
    _SetConsoleMode = windll.kernel32.SetConsoleMode

    _FillConsoleOutputCharacterA = windll.kernel32.FillConsoleOutputCharacterA
    _FillConsoleOutputCharacterA.argtypes = [
        wintypes.HANDLE,
        c_char,
        wintypes.DWORD,
        COORD,
        POINTER(wintypes.DWORD),
    ]
    _FillConsoleOutputCharacterA.restype = wintypes.BOOL

    _FillConsoleOutputAttribute = windll.kernel32.FillConsoleOutputAttribute
    _FillConsoleOutputAttribute.argtypes = [
        wintypes.HANDLE,
        wintypes.WORD,
        wintypes.DWORD,
        COORD,
        POINTER(wintypes.DWORD),
    ]
    _FillConsoleOutputAttribute.restype = wintypes.BOOL

    _SetConsoleTitleW = windll.kernel32.SetConsoleTitleW
    _SetConsoleTitleW.argtypes = [
        wintypes.LPCWSTR
    ]
    _SetConsoleTitleW.restype = wintypes.BOOL

    def _winapi_test(handle):
        csbi = CONSOLE_SCREEN_BUFFER_INFO()
        success = _GetConsoleScreenBufferInfo(
            handle, byref(csbi))
        return bool(success)

    def winapi_test():
        return any(_winapi_test(h) for h in
                   (_GetStdHandle(STDOUT), _GetStdHandle(STDERR)))

    def GetConsoleScreenBufferInfo(stream_id=STDOUT):
        handle = _GetStdHandle(stream_id)
        csbi = CONSOLE_SCREEN_BUFFER_INFO()
        success = _GetConsoleScreenBufferInfo(
            handle, byref(csbi))
        return csbi

    def SetConsoleTextAttribute(stream_id, attrs):
        handle = _GetStdHandle(stream_id)
        return _SetConsoleTextAttribute(handle, attrs)

    def SetConsoleCursorPosition(stream_id, position, adjust=True):
        position = COORD(*position)
        # If the position is out of range, do nothing.
        if position.Y <= 0 or position.X <= 0:
            return
        # Adjust for Windows' SetConsoleCursorPosition:
        #    1. being 0-based, while ANSI is 1-based.
        #    2. expecting (x,y), while ANSI uses (y,x).
        adjusted_position = COORD(position.Y - 1, position.X - 1)
        if adjust:
            # Adjust for viewport's scroll position
            sr = GetConsoleScreenBufferInfo(STDOUT).srWindow
            adjusted_position.Y += sr.Top
            adjusted_position.X += sr.Left
        # Resume normal processing
        handle = _GetStdHandle(stream_id)
        return _SetConsoleCursorPosition(handle, adjusted_position)

    def GetConsoleMode():
        '''
        Note: Returns None if STDOUT has been re-directed to a
        file (and therefore has no Console mode).
        '''
        mode = wintypes.DWORD()
        success = _GetConsoleMode(_GetStdHandle(STDOUT), byref(mode))
        if success:
            return mode.value
        else:
            return None


    def SetConsoleMode(mode):
        return _SetConsoleMode(_GetStdHandle(STDOUT), mode)

    def FillConsoleOutputCharacter(stream_id, char, length, start):
        handle = _GetStdHandle(stream_id)
        char = c_char(char.encode())
        length = wintypes.DWORD(length)
        num_written = wintypes.DWORD(0)
        # Note that this is hard-coded for ANSI (vs wide) bytes.
        success = _FillConsoleOutputCharacterA(
            handle, char, length, start, byref(num_written))
        return num_written.value

    def FillConsoleOutputAttribute(stream_id, attr, length, start):
        ''' FillConsoleOutputAttribute( hConsole, csbi.wAttributes, dwConSize, coordScreen, &cCharsWritten )'''
        handle = _GetStdHandle(stream_id)
        attribute = wintypes.WORD(attr)
        length = wintypes.DWORD(length)
        num_written = wintypes.DWORD(0)
        # Note that this is hard-coded for ANSI (vs wide) bytes.
        return _FillConsoleOutputAttribute(
            handle, attribute, length, start, byref(num_written))

    def SetConsoleTitle(title):
        return _SetConsoleTitleW(title)

    def vt_available():
        '''Ensure Windows 10 virtual terminal is enabled, if possible.

        This function has side effects:
            It will enable the virtual terminal if it's possible to do so.
            global variables `old_mode_value` and `we_enabled_windows_vt` are modified.

        Return: True if virtual terminal is enabled (which it may already have been),
                False otherwise.
        '''
        global old_mode_value
        global we_enabled_windows_vt

        vt_enabled = False

        if (platform.system().lower() == 'windows') and platform.release().startswith('10'):
            ''' "Recent" Windows 10 versions supports ANSI sequences using virtual terminal mode.
            However, this has been turned off by default in some Windows 10 versions (1511 to 1903 ?).
            We turn virtual terminal support back on, if possible.
            '''
            old_mode = GetConsoleMode()
            already_enabled = old_mode & ENABLE_VIRTUAL_TERMINAL_PROCESSING
            if already_enabled:
                return True

            if old_mode is not None:  # and (not already_enabled):
                if old_mode_value is None:
                    # Don't set this again. We get called twice, for stdout and stderr.
                    old_mode_value = old_mode

                # Not all Windows 10 versions support virtual terminal.
                if SetConsoleMode(old_mode_value | ENABLE_VIRTUAL_TERMINAL_PROCESSING):
                    we_enabled_windows_vt = True

            # Check if we managed to enable the virtual terminal
            current_mode = GetConsoleMode()
            if (current_mode is not None) and (current_mode & ENABLE_VIRTUAL_TERMINAL_PROCESSING):
                vt_enabled = True

            return vt_enabled

    def reset_enable_vt():
        global we_enabled_windows_vt

        if we_enabled_windows_vt:
            # We enabled it, so turn it off again.
            SetConsoleMode(old_mode_value)
            we_enabled_windows_vt = False
