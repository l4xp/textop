title_bar = {}
taskbar = {}
icons = {}

_defaults = {}


def init(style: str = "compatible"):
    """
    Initializes the glyphs used in the UI.

    :param style: Name of the style set. Options:
                  - 'compatible' (default)
                  - 'standard'
                  - 'nerdfont'
    """
    global title_bar, taskbar, icons, _defaults

    if style == "compatible":
        title_bar = {
            "minimize": "m",
            "maximize": "M",
            "restore": "~",
            "exit": "X"
        }
        taskbar = {
            "clock": "T",
            "start": ">",
            "workspaces": "W",
            "ram": "R",
            "cpu": "P",
            "storage": "S",
            "sound": "V",
            "battery": "U",
            "wifi": "I",
            "calendar": "D",
            "power": "\\[O]",
            "debug": "\\[!]",
        }
        icons = {
            "notepad": "\\[&]",
            "terminal": "\\[>]",
            "file_manager": "\\[.]",
            "settings": "\\[#]"
        }

    elif style == "standard":
        title_bar = {
            "minimize": "–",
            "maximize": "⟎",
            "restore": "⟏",
            "exit": "✕"
        }
        taskbar = {
            "clock": "🕒",
            "start": "❖",
            "workspaces": "🧩",
            "ram": "🧠",
            "cpu": "🖳",
            "storage": "💽",
            "sound": "🔊",
            "battery": "🔋",
            "wifi": "📶",
            "calendar": "📅",
            "power": "⏻",
            "debug": "[D]",
        }
        icons = {
            "notepad": "[I]",
            "terminal": "[>]",
            "file_manager": "[.]"
        }

    elif style == "nerdfont":
        title_bar = {
            "minimize": "󰖰",
            "maximize": "󰖯",
            "restore": "󰖲",
            "exit": "󰖭"
        }
        taskbar = {
            "clock": "󰥔",
            "start": "",  # 󰍲
            "workspaces": "",
            "ram": "󰍛",
            "cpu": "󰘚",
            "storage": "󰋊",
            "sound": "󰕾",
            "battery": "󰁹",
            "wifi": "󰤨",
            "calendar": "󰃭",
            "power": "⏻",
            "debug": "",
        }
        icons = {
            # 'app' icons?
            "notepad": " 󱞁 ",
            "terminal": "  ",
            "file_manager": "  ",
            "settings": "",
            # separate to file manager instead
            "image": " 󰋩 ",
            "music": " 󰝚 ",
            "file": " 󰈔 ",
            "folder": " 󰉋 ",
        }

    else:
        raise ValueError(f"Unknown style: {style}")

    _defaults = {
        "title_bar": title_bar,
        "taskbar": taskbar,
        "icons": icons
    }
