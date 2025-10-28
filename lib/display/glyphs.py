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
    global icons, _defaults

    if style == "compatible":
        icons = {
            # title bar
            "minimize": "m",
            "maximize": "M",
            "restore": "~",
            "exit": "X",
            # taskbar
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
            # apps
            "debug": "\\[!]",
            "notepad": "\\[&]",
            "terminal": "\\[>]",
            "file_manager": "\\[.]",
            "settings": "\\[#]",
            "folder": "\\[F]"
        }

    elif style == "standard":
        icons = {
            "minimize": "–",
            "maximize": "⟎",
            "restore": "⟏",
            "exit": "✕",

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
            "debug": "\\[D]",

            "notepad": "\\[I]",
            "terminal": "\\[>]",
            "file_manager": "\\[.]"
        }

    elif style == "nerdfont":
        icons = {
            "minimize": "󰖰",
            "maximize": "󰖯",
            "restore": "󰖲",
            "exit": "󰖭",

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
        "icons": icons
    }
