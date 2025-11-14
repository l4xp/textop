# TextTop v0.5

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)]()
[![Textual](https://img.shields.io/badge/Textual-v0.6.5-6E56CF.svg)]()
[![Status](https://img.shields.io/badge/status-Alpha-yellow.svg)]()

> A **desktop environment simulator inside your terminal**, built with [Textual](https://github.com/Textualize/textual).  
> Simulates a full GUI experience — windows, taskbar, start menu, and apps inside a terminal

---

## Table of Contents
- [Overview](#-overview)
- [Features](#-features)
- [Screenshots](#-screenshots)
- [Installation](#-installation)
- [Usage](#-usage)
- [Applications](#-applications)
- [Architecture](#-architecture)
- [Roadmap](#-roadmap)
- [License](#-license)

---

## Overview

**TextTop** is a text-based desktop environment (?) built for the terminal.
It provides a simulated OS experience — a window manager, start menu, apps, and dynamic layouts.

### Highlights
- Windowed GUI in the terminal
- Windows OS / Linux WM Layout Styles
- Mouse & keyboard navigation
- Virtual File System (VFS) for sandbox access
- Extensible modular architecture

---

## Features

### Window Manager
- Floating and tiling layouts (`vstack`, `hstack`, `bsp`, `bsp_alt`, `ultra_wide`, `ultra_tall`)
- Window actions: **move**, **resize**, **minimize**, **maximize**, **close**
- Focus cycling and directional navigation

### System Components
- **Taskbar** with clock, active window list, and app launchers
- **Start Menu** populated from the virtual `/bin` directory
- **Notifications system**
- **Flyouts**
- **Desktop environment manager** (`WindowManager` + `Desktop`)

### Included Applications
- **Clock** — digital clock widget
- **Notepad** — minimalist text editor
- **Snake** — classic terminal snake game
- **Terminal** — sandboxed prompt with VFS commands (`ls`, `cd`, `cat`, `touch`, etc.)

---

## Screenshots

<p align="center">
  <img src="etc/TextTop_1.svg" width="48%" alt="TextTop float layout with nord theme">
  <img src="etc/TextTop_2.svg" width="48%" alt="TextTop bsp layout with nord theme">
</p>

<p align="center">
  <img src="etc/TextTop_3.svg" width="80%" alt="TextTop ultra wide layout with darcula theme">
</p>

---

## Installation

### Prerequisites
- Python **3.11+**
- [Textual v6.5.0](https://github.com/Textualize/textual)
- Unix-like terminal (Linux, macOS, or WSL)

### Clone & Install
```bash
git clone https://github.com/yourusername/textop.git
cd textop
pip install -r requirements.txt
````

---

## 🚀 Usage

To start the simulated desktop environment:

```bash
python boot.py
```

### Keyboard Shortcuts (to be updated)

| Key                      | Action                    |
| ------------------------ | ------------------------- |
| `Alt + Tab`              | Switch active window      |
| `Ctrl + ↑/↓/←/→`         | Move window directionally |
| `Ctrl + p`               | Toggle Command Palette    |

---

## Built-in Applications

| App         | Path              | Description                 |
| ----------- | ----------------- | --------------------------- |
| Clock       | `bin/clock.py`    | Simple live clock           |
| Notepad     | `bin/notepad.py`  | Minimal text editor         |
| Snake       | `bin/snake.py`    | Classic snake game          |
| Terminal    | `bin/terminal.py` | Virtual filesystem terminal |

---

## Architecture

```
textop/
├── bin/          # Built-in applications
├── lib/          # Core window manager, display, layout, widgets
├── etc/          # Assets
├── home/         # Simulated user directories
├── notes/        # Notes, prototypes
├── boot.py       # Main entry point (TextTop v0.5)
├── main.css      # UI theme and styling
└── requirements.txt
```

---

## Roadmap

| Area                      | Status         |
| ------------------------- | -------------- |
| Window Basics             | ✅ Done         |
| Dynamic Layouts           | ✅ Done         |
| Taskbar Widgets           | ✅ Done         |
| Start Menu                | ⚙️ In Progress |
| Virtual File System       | ⚙️ In Progress |
| User System               | ⏳ Planned      |
| Workspaces                | ⏳ Planned      |
| Settings UI               | ⏳ Planned      |
| Persistence / Save States | ⏳ Planned      |

---

## License

This project is licensed under the **`?` License** — see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

* Built with [Textual](https://github.com/Textualize/textual)
* Inspired by windows, komorebi, linux, sway, vtm, dvtm, desqview

---
