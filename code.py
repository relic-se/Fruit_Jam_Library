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
import math
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
from adafruit_portalbase.network import HttpError
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

bg_palette = displayio.Palette(1)
bg_palette[0] = config.palette_bg if config is not None else 0x222222

fg_palette = displayio.Palette(1)
fg_palette[0] = config.palette_fg if config is not None else 0xffffff

# setup display
displayio.release_displays()
try:
    adafruit_fruitjam.peripherals.request_display_config()  # user display configuration
except ValueError:  # invalid user config or no user config provided
    adafruit_fruitjam.peripherals.request_display_config(720, 400)  # default display size
display = supervisor.runtime.display

# setup FruitJam peripherals and networking
fj = adafruit_fruitjam.FruitJam()

# load images
default_icon_bmp, default_icon_palette = adafruit_imageload.load("bitmaps/default_icon.bmp")
default_icon_palette.make_transparent(0)

installed_bmp, installed_palette = adafruit_imageload.load("bitmaps/installed.bmp")
installed_palette.make_transparent(1)
installed_palette[0] = config.palette_bg if config is not None else 0x222222
installed_palette[2] = config.palette_fg if config is not None else 0xffffff

left_bmp, left_palette = adafruit_imageload.load("bitmaps/arrow_left.bmp")
left_palette.make_transparent(0)
right_bmp, right_palette = adafruit_imageload.load("bitmaps/arrow_right.bmp")
right_palette.make_transparent(0)
left_palette[2] = right_palette[2] = (config.palette_arrow if config is not None else 0x004abe)

# display constants
SCALE = 2 if display.width > 360 else 1

DISPLAY_WIDTH = display.width // SCALE
DISPLAY_HEIGHT = display.height // SCALE

TITLE_HEIGHT = 16

STATUS_HEIGHT = 16
STATUS_PADDING = 4

MENU_HEIGHT = 24
MENU_GAP = 8

PAGE_COLUMNS = SCALE
PAGE_ROWS = 3
PAGE_SIZE = PAGE_COLUMNS * PAGE_ROWS

ARROW_MARGIN = 2

GRID_MARGIN = 8 * SCALE
GRID_WIDTH = display.width - GRID_MARGIN * 2 - (ARROW_MARGIN + left_bmp.width) * SCALE * 2
GRID_HEIGHT = display.height - TITLE_HEIGHT * SCALE - MENU_HEIGHT * SCALE - GRID_MARGIN * 2 - STATUS_HEIGHT

ITEM_WIDTH = GRID_WIDTH // PAGE_COLUMNS
ITEM_HEIGHT = GRID_HEIGHT // PAGE_ROWS

DIALOG_MARGIN = 16
DIALOG_BORDER = 2
DIALOG_WIDTH = DISPLAY_WIDTH - DIALOG_MARGIN * 2 - (ARROW_MARGIN + left_bmp.width) * 2
DIALOG_HEIGHT = DISPLAY_HEIGHT - TITLE_HEIGHT - DIALOG_MARGIN * 2 - STATUS_HEIGHT // SCALE
DIALOG_BUTTON_WIDTH = DIALOG_WIDTH // 4

BUTTON_PROPS = {
    "height": MENU_HEIGHT,
    "label_font": FONT,
    "style": Button.ROUNDRECT,
    "fill_color": (config.palette_bg if config is not None else 0x222222),
    "label_color": (config.palette_fg if config is not None else 0xffffff),
    "outline_color": (config.palette_fg if config is not None else 0xffffff),
    "selected_fill": (config.palette_fg if config is not None else 0xffffff),
    "selected_label": (config.palette_bg if config is not None else 0x222222),
}

# create groups
root_group = displayio.Group()
display.root_group = root_group

bg_tg = displayio.TileGrid(
    bitmap=displayio.Bitmap(display.width, display.height, 1),
    pixel_shader=bg_palette,
)
root_group.append(bg_tg)

scaled_group = displayio.Group(scale=SCALE)
root_group.append(scaled_group)

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

status_bg_tg = displayio.TileGrid(
    bitmap=displayio.Bitmap(display.width, STATUS_HEIGHT, 1),
    pixel_shader=fg_palette,
    y=display.height - STATUS_HEIGHT,
)
status_group.append(status_bg_tg)

status_label = Label(
    font=FONT,
    text="Loading...",
    color=(config.palette_bg if config is not None else 0x222222),
    anchor_point=(0, 0.5),
    anchored_position=(STATUS_PADDING, display.height - STATUS_HEIGHT // 2)
)
status_group.append(status_label)

page_label = Label(
    font=FONT,
    text="0/0",
    color=(config.palette_bg if config is not None else 0x222222),
    anchor_point=(1, 0.5),
    anchored_position=(display.width - STATUS_PADDING, display.height - STATUS_HEIGHT // 2)
)
status_group.append(page_label)

# check that sd card is mounted
def reset(timeout:int = 0) -> None:
    if timeout > 0:
        time.sleep(timeout)
    fj.peripherals.deinit()
    supervisor.reload()

if not fj.sd_check():
    status_label.text = "SD card not mounted! SD card installation required for this application."
    display.refresh()
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
    if type(applications) is int:
        raise ValueError("{:d} response".format(applications))
except (OSError, ValueError, AttributeError) as e:
    status_label.text = "Unable to fetch applications database! {:s}".format(str(e))
    display.refresh()
    reset(3)

categories = list(applications.keys())
selected_category = None

# setup menu
category_group = displayio.Group()
scaled_group.append(category_group)
MENU_WIDTH = (DISPLAY_WIDTH - MENU_GAP * (len(categories) + 1)) // len(categories)
for index, category in enumerate(categories):
    category_button = Button(
        x=(MENU_WIDTH + MENU_GAP) * index + MENU_GAP,
        y=TITLE_HEIGHT,
        width=MENU_WIDTH,
        label=category,
        **BUTTON_PROPS,
    )
    category_group.append(category_button)

# setup items
item_grid = GridLayout(
    x=(display.width - GRID_WIDTH) // 2,
    y=TITLE_HEIGHT * SCALE + MENU_HEIGHT * SCALE + GRID_MARGIN,
    width=GRID_WIDTH,
    height=GRID_HEIGHT,
    grid_size=(PAGE_COLUMNS, PAGE_ROWS),
    divider_lines=False,
)
root_group.append(item_grid)

for index in range(PAGE_SIZE):
    item_group = AnchoredGroup()
    item_group.hidden = True

    item_icon = displayio.TileGrid(
        bitmap=default_icon_bmp,
        pixel_shader=default_icon_palette,
        x=(ITEM_HEIGHT - default_icon_bmp.height) // 2,
        y=(ITEM_HEIGHT - default_icon_bmp.height) // 2,
    )
    item_group.append(item_icon)

    item_installed = displayio.TileGrid(
        bitmap=installed_bmp,
        pixel_shader=installed_palette,
        x=item_icon.x + 2, y=item_icon.y + 2,
    )
    item_group.append(item_installed)

    item_title = Label(
        font=FONT,
        text="[title]",
        color=(config.palette_fg if config is not None else 0xffffff),
        anchor_point=(0, 0),
        anchored_position=(ITEM_HEIGHT, (ITEM_HEIGHT - item_icon.tile_height) // 2),
        scale=SCALE,
    )
    item_group.append(item_title)

    item_author = Label(
        font=FONT,
        text="[author]",
        color=(config.palette_fg if config is not None else 0xffffff),
        anchor_point=(0, 0),
        anchored_position=(ITEM_HEIGHT, item_title.y + item_title.height),
    )
    item_group.append(item_author)

    item_description = TextBox(
        font=FONT,
        text="[description]",
        width=ITEM_WIDTH - ITEM_HEIGHT,
        height=item_icon.tile_height - item_title.height - item_author.height,
        align=TextBox.ALIGN_LEFT,
        color=(config.palette_fg if config is not None else 0xffffff),
        anchor_point=(0, 0),
        anchored_position=(ITEM_HEIGHT, item_author.y + item_author.height),
    )
    item_group.append(item_description)

    item_grid.add_content(
        cell_content=item_group,
        grid_position=(index % PAGE_COLUMNS, index // PAGE_COLUMNS),
        cell_size=(1, 1),
    )

# setup arrows
original_arrow_btn_color = left_palette[2]

left_tg = AnchoredTileGrid(bitmap=left_bmp, pixel_shader=left_palette)
left_tg.anchor_point = (0, 0.5)
left_tg.anchored_position = (0, (DISPLAY_HEIGHT // 2) - 2)
scaled_group.append(left_tg)

right_tg = AnchoredTileGrid(bitmap=right_bmp, pixel_shader=right_palette)
right_tg.anchor_point = (1.0, 0.5)
right_tg.anchored_position = (DISPLAY_WIDTH, (DISPLAY_HEIGHT // 2) - 2)
scaled_group.append(right_tg)

# setup dialog
dialog_group = displayio.Group()
dialog_group.hidden = True
scaled_group.append(dialog_group)

dialog_border = displayio.TileGrid(
    bitmap=displayio.Bitmap(DIALOG_WIDTH, DIALOG_HEIGHT, 1),
    pixel_shader=fg_palette,
    x=(DISPLAY_WIDTH - DIALOG_WIDTH) // 2,
    y=TITLE_HEIGHT + DIALOG_MARGIN,
)
dialog_group.append(dialog_border)

dialog_bg = displayio.TileGrid(
    bitmap=displayio.Bitmap(DIALOG_WIDTH - DIALOG_BORDER * 2, DIALOG_HEIGHT - DIALOG_BORDER * 2, 1),
    pixel_shader=bg_palette,
    x=dialog_border.x + DIALOG_BORDER,
    y=dialog_border.y + DIALOG_BORDER,
)
dialog_group.append(dialog_bg)

dialog_content = TextBox(
    font=FONT,
    text="[content]",
    width=DIALOG_WIDTH - DIALOG_BORDER * 2 - DIALOG_MARGIN * 2,
    height=DIALOG_HEIGHT - DIALOG_BORDER * 2 - DIALOG_MARGIN * 3 - MENU_HEIGHT,
    align=TextBox.ALIGN_CENTER,
    color=(config.palette_fg if config is not None else 0xffffff),
    x=dialog_bg.x + DIALOG_MARGIN,
    y=dialog_bg.y + DIALOG_MARGIN,
)
dialog_group.append(dialog_content)

dialog_no = Button(
    x=dialog_border.x + (DIALOG_WIDTH - DIALOG_MARGIN) // 2 - DIALOG_BUTTON_WIDTH,
    y=dialog_border.y + DIALOG_HEIGHT - DIALOG_BORDER - DIALOG_MARGIN - MENU_HEIGHT,
    width=DIALOG_BUTTON_WIDTH,
    label="No",
    **BUTTON_PROPS,
)
dialog_group.append(dialog_no)

dialog_yes = Button(
    x=dialog_border.x + (DIALOG_WIDTH + DIALOG_MARGIN) // 2,
    y=dialog_no.y,
    width=DIALOG_BUTTON_WIDTH,
    label="Yes",
    **BUTTON_PROPS,
)
dialog_group.append(dialog_yes)

# file download + caching

def _download_file(url: str, extension: str, name: str|None = None) -> str:
    if not extension.startswith("."):
        extension = "." + extension

    if name is None:
        name = url.split("/")[-1][:-len(extension)]
    elif name.endswith(extension):
        name = name[:-len(extension)]
    path = "/sd/.cache/{:s}{:s}".format(name, extension)

    # check if file already exists
    try:
        os.stat(path)
    except OSError:
        # download file
        fj.network.wget(url, path)
    return path

def download_image(url: str, name: str|None = None) -> str:
    return _download_file(
        url=url,
        extension=".bmp",
        name=name,
    )

def download_json(url: str, name: str|None = None) -> str:
    path = _download_file(
        url=url,
        extension=".json",
        name=name,
    )
    with open(path, "r") as f:
        data = json.loads(f.read())
    return data

# item navigation

def select_category(name: str) -> None:
    global categories, item_grid, selected_category
    if name not in categories or name == selected_category:
        return
    selected_category = name

    # update button states
    for category_button in category_group:
        category_button.selected = category_button.label == name
    
    # hide all items
    for index in range(PAGE_SIZE):
        item_grid.get_content((index % PAGE_COLUMNS, index // PAGE_COLUMNS)).hidden = True

    # load first page of items
    show_page()

current_page = 0
def show_page(page: int = 0) -> None:
    global selected_category, item_grid, page_label, applications, current_page

    # determine indices
    start = page * PAGE_SIZE
    end = min((page + 1) * PAGE_SIZE, len(applications[selected_category]))
    if start < 0 or start >= len(applications[selected_category]):
        return

    # hide all items
    for index in range(PAGE_SIZE):
        item_grid.get_content((index % PAGE_COLUMNS, index // PAGE_COLUMNS)).hidden = True
    
    # update page label
    current_page = page
    page_label.text = "{:d}/{:d}".format(page + 1, math.ceil(len(applications[selected_category]) / PAGE_SIZE))
    
    for index in range(start, end):
        item_group = item_grid.get_content((index % PAGE_COLUMNS, index // PAGE_COLUMNS))
        item_icon, item_installed, item_title, item_author, item_description = item_group

        full_name = applications[selected_category][index]
        repo_owner, repo_name = full_name.split("/")

        # format title from repository name
        title = repo_name.replace("-", " ").replace("_", " ").strip()
        title = " ".join(map(lambda word: word[0].upper() + word[1:].lower(), title.split(" ")))
        if title.startswith("Fruit Jam"):
            title = title[len("Fruit Jam"):].strip()
        
        # set default details
        item_icon.bitmap = default_icon_bmp
        item_icon.pixel_shader = default_icon_palette
        item_title.text = title
        item_author.text = repo_owner
        item_description.text = "Loading..."
        item_group.hidden = False

        # check if application is installed
        try:
            os.stat("/sd/apps/{:s}".format(repo_name))
        except:
            item_installed.hidden = True
        else:
            item_installed.hidden = False

        status_label.text = "Reading repository data from {:s}".format(full_name)
        display.refresh()

        # get repository info
        try:
            repository = download_json(
                url=REPO_URL.format(full_name),
                name=full_name.replace("/", "_"),
            )
        except (OSError, ValueError, HttpError) as e:
            item_description.text = ""
            status_label.text = "Unable to read repository data from {:s}! {:s}".format(full_name, str(e))
            display.refresh()
            time.sleep(1)
            continue
        else:
            item_author.text = repository["owner"]["login"]
            item_description.text = repository["description"]

        # read metadata from repository
        status_label.text = "Reading metadata from {:s}".format(full_name)
        display.refresh()
        try:
            metadata = download_json(
                url=METADATA_URL.format(full_name),
                name=full_name.replace("/", "_") + "_metadata",
            )
        except (OSError, ValueError, HttpError) as e:
            status_label.text = "Unable to read metadata from {:s}! {:s}".format(full_name, str(e))
            display.refresh()
        else:
            item_title.text = metadata["title"]

            if "description" in metadata:
                item_description.text = metadata["description"]

            if "icon" in metadata:
                status_label.text = "Downloading icon from {:s}".format(full_name)
                display.refresh()
                try:
                    icon_path = download_image(
                        ICON_URL.format(full_name, repository["default_branch"], metadata["icon"]),
                        repository["name"] + "_" + metadata["icon"],
                    )
                except (OSError, ValueError, HttpError) as e:
                    status_label.text = "Unable to download icon image from {:s}! {:s}".format(full_name, str(e))
                    display.refresh()
                else:
                    icon_bmp, icon_palette = adafruit_imageload.load(icon_path)
                    item_icon.bitmap = icon_bmp
                    item_icon.pixel_shader = icon_palette

        # cleanup before loading next item
        gc.collect()

    status_label.text = "Page loaded!"
    display.refresh()

def next_page() -> None:
    global current_page
    show_page(current_page + 1)

def previous_page() -> None:
    global current_page
    show_page(current_page - 1)

# select first category and show page items
select_category(categories[0])

# application download

selected_application = None
def select_application(index: int) -> None:
    global categories, selected_category, current_page, selected_application, dialog_content, dialog_group

    index += current_page * PAGE_SIZE
    if index < 0 or index >= len(applications[selected_category]):
        return
    
    selected_application = applications[selected_category][index]
    repo_owner, repo_name = selected_application.split("/")
    
    # hide other UI elements
    category_group.hidden = True
    item_grid.hidden = True
    left_tg.hidden = True
    right_tg.hidden = True
    
    # populate dialog info
    page_index = index % PAGE_SIZE
    item_group = item_grid.get_content((page_index % PAGE_COLUMNS, page_index // PAGE_COLUMNS))
    item_icon, item_title, item_author, item_description = item_group

    dialog_content.text = "Would you like to download and install \"{:s}\" by {:s} to your SD card at /sd/apps/{:s}?".format(
        item_title.text,
        item_author.text,
        repo_name
    )

    dialog_group.hidden = False

def deselect_application() -> None:
    # invalidate selection
    global selected_application
    selected_application = None

    # hide dialog
    dialog_group.hidden = True

    # show other UI elements
    category_group.hidden = False
    item_grid.hidden = False
    left_tg.hidden = False
    right_tg.hidden = False

def download_application() -> None:
    global selected_application
    if selected_application is None:
        return
    
    print("Downloading?")

# mouse control
async def mouse_task() -> None:
    global selected_category, categories, category_group, root_group, right_tg, left_tg, selected_application
    while True:
        if (mouse := adafruit_usb_host_mouse.find_and_init_boot_mouse()) is not None:
            mouse.x = DISPLAY_WIDTH // 2
            mouse.y = DISPLAY_HEIGHT // 2
            scaled_group.append(mouse.tilegrid)

            timeouts = 0
            previous_mouse_state = False
            while timeouts < 60:
                if mouse.update() is not None:
                    timeouts = 0
                    mouse_state = "left" in mouse.pressed_btns
                    if mouse_state and not previous_mouse_state:
                        if dialog_group.hidden:
                            if (clicked_cell := item_grid.which_cell_contains((mouse.x * SCALE, mouse.y * SCALE))) is not None:
                                select_application(clicked_cell[1] * PAGE_COLUMNS + clicked_cell[0])
                            elif right_tg.contains((mouse.x, mouse.y, 0)):
                                next_page()
                            elif left_tg.contains((mouse.x, mouse.y, 0)):
                                previous_page()
                            else:
                                for button in category_group:
                                    if button.contains((mouse.x, mouse.y)):
                                        select_category(button.label)
                                        break
                        elif dialog_yes.contains((mouse.x, mouse.y, 0)):
                            download_application()
                        elif dialog_no.contains((mouse.x, mouse.y, 0)):
                            deselect_application()
                    previous_mouse_state = mouse_state
                else:
                    timeouts += 1
                await asyncio.sleep(1/30)

            scaled_group.remove(mouse.tilegrid)
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
