# SPDX-FileCopyrightText: 2025 Cooper Dalrymple (@relic-se)
#
# SPDX-License-Identifier: GPLv3

# load included modules if we aren't installed on the root path
if len(__file__.split("/")[:-1]) > 1:
    import adafruit_pathlib as pathlib
    if (modules_directory := pathlib.Path("/".join(__file__.split("/")[:-1])) / "lib").exists():
        import sys
        sys.path.append(str(modules_directory.absolute()))

import displayio
import gc
import os
import sys
import supervisor
from terminalio import FONT
import time
import json

from adafruit_anchored_group import AnchoredGroup
from adafruit_anchored_tilegrid import AnchoredTileGrid
from adafruit_button import Button
from adafruit_display_text.label import Label
from adafruit_display_text.text_box import TextBox
from adafruit_displayio_layout.layouts.grid_layout import GridLayout
import adafruit_fruitjam
import adafruit_fruitjam.network
import adafruit_fruitjam.peripherals
import adafruit_imageload
import adafruit_usb_host_mouse
import asyncio

# program constants
APPLICATIONS_URL = "https://raw.githubusercontent.com/relic-se/Fruit_Jam_Store/refs/heads/main/database/applications.json"
METADATA_URL = "https://raw.githubusercontent.com/{:s}/refs/heads/main/metadata.json"
REPO_URL = "https://api.github.com/repos/{:s}"
ICON_URL = "https://raw.githubusercontent.com/{:s}/{:s}/{:s}"

# get Fruit Jam OS config if available
try:
    import launcher_config
    config = launcher_config.LauncherConfig()
except ImportError:
    config = None

# setup display
displayio.release_displays()
try:
    adafruit_fruitjam.peripherals.request_display_config()  # user display configuration
except ValueError:  # invalid user config or no user config provided
    adafruit_fruitjam.peripherals.request_display_config(720, 400)  # default display size
display = supervisor.runtime.display

# setup FruitJam peripherals and networking
fj = adafruit_fruitjam.FruitJam()

# display constants
SCALE = 2 if display.width > 360 else 1

DISPLAY_WIDTH = display.width // SCALE
DISPLAY_HEIGHT = display.height // SCALE

TITLE_HEIGHT = 16

STATUS_HEIGHT = 16
STATUS_PADDING = 4

MENU_HEIGHT = 24
MENU_GAP = 8

PAGE_SIZE = 3
ITEM_MARGIN = 16
ITEM_FULL_WIDTH = DISPLAY_WIDTH - ITEM_MARGIN * 2
ITEM_WIDTH = ITEM_FULL_WIDTH // PAGE_SIZE
ITEM_HEIGHT = DISPLAY_HEIGHT - TITLE_HEIGHT - MENU_HEIGHT - ITEM_MARGIN * 2 - STATUS_HEIGHT // SCALE

# create groups
root_group = displayio.Group()
display.root_group = root_group

scaled_group = displayio.Group(scale=SCALE)
root_group.append(scaled_group)

bg_palette = displayio.Palette(1)
bg_palette[0] = config.palette_bg if config is not None else 0x222222
bg_tg = displayio.TileGrid(
    bitmap=displayio.Bitmap(DISPLAY_WIDTH, DISPLAY_HEIGHT, 1),
    pixel_shader=bg_palette,
)
scaled_group.append(bg_tg)

# add title
title_label = Label(
    font=FONT,
    text="Fruit Jam Store",
    color=(config.palette_fg if config is not None else 0xffffff),
    anchor_point=(0.5, 0.5),
    anchored_position=(DISPLAY_WIDTH // 2, TITLE_HEIGHT // 2),
)
scaled_group.append(title_label)

# add status bar
status_group = displayio.Group()
root_group.append(status_group)

status_bg_palette = displayio.Palette(1)
status_bg_palette[0] = config.palette_fg if config is not None else 0xffffff
status_bg_tg = displayio.TileGrid(
    bitmap=displayio.Bitmap(DISPLAY_WIDTH, DISPLAY_HEIGHT, 1),
    pixel_shader=bg_palette,
)
status_group.append(status_bg_tg)

status_text = TextBox(
    font=FONT,
    text="Loading...",
    width=display.width - STATUS_PADDING * 2,
    height=STATUS_HEIGHT,
    align=TextBox.ALIGN_LEFT,
    color=(config.palette_bg if config is not None else 0x222222),
    x=STATUS_PADDING,
    y=display.height - STATUS_HEIGHT,
)
status_group.append(status_text)

# check that sd card is mounted
def reset(timeout:int = 0) -> None:
    if timeout > 0:
        time.sleep(timeout)
    fj.peripherals.deinit()
    supervisor.reload()

if not fj.sd_check():
    status_text.text = "SD card not mounted! SD card installation required for this application."
    reset(3)

# create apps directory on sd card if it doesn't exist
try:
    os.stat("/sd/apps")
except OSError:
    os.mkdir("/sd/apps")

# create cache directory (used for saving images) if it doesn't already exist
try:
    os.stat("/sd/.cache")
except OSError:
    os.mkdir("/sd/.cache")

# download applications database
try:
    applications = json.loads(fj.fetch(
        APPLICATIONS_URL,
        force_content_type=adafruit_fruitjam.network.CONTENT_JSON,
        timeout=10,
    ))
except (OSError, ValueError, AttributeError) as e:
    status_text.text = "Unable to fetch applications database! {:s}".format(e)
    reset(3)

categories = list(applications.keys())
selected_category = None

# load images
default_icon_bmp, default_icon_palette = adafruit_imageload.load("launcher_assets/default_icon.bmp")
default_icon_palette.make_transparent(0)
left_bmp, left_palette = adafruit_imageload.load("launcher_assets/arrow_left.bmp")
left_palette.make_transparent(0)
right_bmp, right_palette = adafruit_imageload.load("launcher_assets/arrow_right.bmp")
right_palette.make_transparent(0)
left_palette[2] = right_palette[2] = (config.palette_arrow if config is not None else 0x004abe)

# setup menu
category_group = displayio.Group()
scaled_group.append(category_group)
MENU_WIDTH = (DISPLAY_WIDTH - MENU_GAP * (len(categories) + 1)) // len(categories)
for index, category in enumerate(categories):
    category_button = Button(
        x=(MENU_WIDTH + MENU_GAP) * index,
        y=TITLE_HEIGHT,
        width=MENU_WIDTH,
        height=MENU_HEIGHT,
        label=category,
        label_font=FONT,
        style=Button.ROUNDRECT,
        fill_color=(config.palette_bg if config is not None else 0x222222),
        label_color=(config.palette_fg if config is not None else 0xffffff),
        outline_color=(config.palette_fg if config is not None else 0xffffff),
        selected_fill=(config.palette_fg if config is not None else 0xffffff),
        selected_label=(config.palette_bg if config is not None else 0x222222),
    )
    category_button.selected = category == select_category
    category_group.append(category_button)

# setup items
item_grid = GridLayout(
    x=(DISPLAY_WIDTH - ITEM_FULL_WIDTH) // 2,
    y=(DISPLAY_HEIGHT - ITEM_HEIGHT) // 2,
    width=ITEM_WIDTH,
    height=ITEM_HEIGHT,
    grid_size=(PAGE_SIZE, 1),
    divider_lines=False,
)
scaled_group.append(item_grid)

for i in range(PAGE_SIZE):
    item_group = AnchoredGroup()
    item_group.hidden = True
    item_grid.add_content(
        cell_content=item_group,
        grid_position=(0, i),
        cell_size=(1, 1),
    )

    item_tg = displayio.TileGrid(
        bitmap=default_icon_bmp,
        pixel_shader=default_icon_palette,
        x=ITEM_WIDTH // 2,
        y=(ITEM_HEIGHT - default_icon_bmp.height) // 2,
    )
    item_group.append(item_tg)

    item_title = Label(
        font=FONT,
        text="[title]",
        color=(config.palette_fg if config is not None else 0xffffff),
        x=ITEM_HEIGHT,
        y=(ITEM_HEIGHT - item_tg.tile_height) // 2,
    )
    item_group.append(item_title)

    item_author = Label(
        font=FONT,
        text="[author]",
        width=ITEM_WIDTH,
        color=(config.palette_fg if config is not None else 0xffffff),
        x=ITEM_HEIGHT,
        y=item_title.y + item_title.height,
    )
    item_group.append(item_author)

    item_description = TextBox(
        font=FONT,
        text="[description]",
        width=ITEM_WIDTH - ITEM_HEIGHT,
        height=item_tg.tile_height - item_title.height - item_author.height,
        align=TextBox.ALIGN_LEFT,
        color=(config.palette_fg if config is not None else 0xffffff),
        x=ITEM_HEIGHT,
        y=item_author.y + item_author.height,
    )
    item_group.append(item_description)

# setup arrows
original_arrow_btn_color = left_palette[2]

left_tg = AnchoredTileGrid(bitmap=left_bmp, pixel_shader=left_palette)
left_tg.anchor_point = (0, 0.5)
left_tg.anchored_position = (0, (DISPLAY_HEIGHT // 2) - 2)

right_tg = AnchoredTileGrid(bitmap=right_bmp, pixel_shader=right_palette)
right_tg.anchor_point = (1.0, 0.5)
right_tg.anchored_position = (DISPLAY_WIDTH, (DISPLAY_HEIGHT // 2) - 2)

def select_category(name: str) -> None:
    global categories, item_grid, selected_category
    if name not in categories or name == selected_category:
        return
    selected_category = name
    
    # hide all items
    for i in range(PAGE_SIZE):
        item_grid.get_content((0, i)).hidden = True

    # load first page of items
    show_page()

def _download_image(url: str, name: str|None = None) -> str:
    if url[-4:] != ".bmp":
        raise ValueError("Only bitmap files supported")

    if name is None:
        name = url.split("/")[-1][:-4]
    elif name.endswith(".bmp"):
        name = name[:-4]
    path = "/sd/.cache/{:s}.bmp".format(name)

    # check if file already exists
    try:
        os.stat(path)
    except OSError:
        # download image file (hopefully a bitmap!)
        fj.network.wget(url, path)
    return path

def show_page(index: int = 0) -> None:
    global selected_category
    # hide all items
    for i in range(PAGE_SIZE):
        item_grid.get_content((0, i)).hidden = True

    # determine indices
    start = index * PAGE_SIZE
    end = min((index + 1) * PAGE_SIZE, len(applications[selected_category]))
    if start >= len(applications[selected_category]):
        return
    
    for index in range(start, end):
        item_group = item_grid.get_content((0, i))
        item_tg, item_title, item_author, item_description = item_group

        full_name = applications[selected_category][index]
        status_text.text = "Reading repository data from {:s}".format(full_name)

        # get repository info
        try:
            repository = json.loads(fj.fetch(
                REPO_URL.format(full_name),
                force_content_type=adafruit_fruitjam.network.CONTENT_JSON,
                timeout=10,
            ))
        except (OSError, ValueError) as e:
            status_text.text = "Unable to read repository data from {:s}! {:s}".format(full_name, e)
            time.sleep(1)
            continue
        else:
            item_author.text = repository["owner"]["login"]
            item_description.text = repository["description"]

        # read metadata from repository
        status_text.text = "Reading metadata from {:s}".format(full_name)
        title = repository["name"]
        icon = None
        try:
            metadata = json.loads(fj.fetch(
                METADATA_URL.format(full_name),
                force_content_type=adafruit_fruitjam.network.CONTENT_JSON,
                timeout=10,
            ))
        except (OSError, ValueError) as e:
            status_text.text = "Unable to read metadata from {:s}! {:s}".format(full_name, e)
        else:
            title = metadata["title"]
            if "icon" in metadata:
                icon = metadata["icon"]
        finally:
            item_title.text = title
        
        if icon is not None:
            # download icon
            status_text.text = "Downloading icon from {:s}".format(full_name)
            try:
                icon_path = _download_image(
                    ICON_URL.format(full_name, repository["default_branch"], icon),
                    repository["name"] + "_" + icon,
                )
            except (OSError, ValueError) as e:
                status_text.text = "Unable to download icon image from {:s}! {:s}".format(full_name, e)
                item_tg.bitmap = default_icon_bmp
                item_tg.pixel_shader = default_icon_palette
            else:
                icon_bmp, icon_palette = adafruit_imageload.load(icon_path)
                item_tg.bitmap = icon_bmp
                item_tg.pixel_shader = icon_palette

        else:
            item_tg.bitmap = default_icon_bmp
            item_tg.pixel_shader = default_icon_palette

        item_group.hidden = False

        # cleanup before loading next item
        gc.collect()

# select first category and show page items
select_category(categories[0])

# mouse control
async def mouse_task() -> None:
    global selected_category
    while True:
        if (mouse := adafruit_usb_host_mouse.find_and_init_boot_mouse()) is not None:
            mouse.x = display.width // 2
            mouse.y = display.height // 2
            root_group.append(mouse.tilegrid)

            while mouse.update() is not None:
                for index, button in enumerate(category_group):
                    if categories[index] != selected_category:
                        if button.selected and "left" not in mouse.pressed_btns:
                            if button.contains((mouse.x, mouse.y)):
                                select_category(category)
                            else:
                                button.selected = False
                        elif not button.selected and "left" in mouse.pressed_btns and button.contains((mouse.x, mouse.y)):
                            button.selected = True
                await asyncio.sleep(1/30)

            root_group.remove(mouse.tilegrid)
        await asyncio.sleep(1)

async def keyboard_task() -> None:
    # flush input buffer
    while supervisor.runtime.serial_bytes_available:
        sys.stdin.read(1)

    while True:
        while (c := supervisor.runtime.serial_bytes_available) > 0:
            key = sys.stdin.read(c)
            if key == "\x1b":  # escape
                reset()
        await asyncio.sleep(1/30)

async def main() -> None:
    await asyncio.gather(
        asyncio.create_task(mouse_task()),
        asyncio.create_task(keyboard_task()),
    )

try:
    asyncio.run(main())
except KeyboardInterrupt:
    reset()
