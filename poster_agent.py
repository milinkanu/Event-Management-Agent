"""
poster_agent.py - Automated Event Poster Generator
=================================================

This agent:
1. Reads event rows from Google Drive Excel.
2. Filters for upcoming rows, case-insensitive.
3. Generates posters for Online/Offline and 1/2/3 speaker variants.
4. Saves posters locally and uploads to Drive destination folders.
"""

import os
import re
import sys
import time
import traceback
import copy
from collections import deque
from datetime import datetime

import pandas as pd
import numpy as np
import qrcode
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from app_constants import OAUTH_CREDENTIALS_FILE, OAUTH_TOKEN_FILE, SERVICE_ACCOUNT_FILE
from app_logging import configure_logging, get_logger
from gdrive_manager import GoogleDriveManager as GDriveManager

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

logger = get_logger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

GDRIVE_BASE_FOLDER = "Poster Automation"
GDRIVE_TEMPLATES_FOLDER = "Templates"
GDRIVE_GENERATED_FOLDER = "Generated Posters"
GDRIVE_COMMUNITY_FOLDER = "Community Partners"
GDRIVE_GIFT_FOLDER = "Gift Sponsors"
GDRIVE_VENUE_FOLDER = "Venue Sponsors"
SPEAKER_PHOTOS_FOLDER = "Speaker Photos"

TEMPLATE_SUBFOLDER_BY_SPEAKER = {
    1: "One Speaker",
    2: "Two Speakers",
    3: "Three Speakers",
}

GENERATED_SUBFOLDER_BY_SPEAKER = {
    1: "1 Speaker",
    2: "2 Speakers",
    3: "3 Speakers",
}
SPEAKER_FOLDER_BY_COUNT = {
    1: "1 Speaker",
    2: "2 Speakers",
    3: "3 Speakers",
}

MODE_FOLDER_BY_KEY = {
    "online": "Online",
    "offline": "Offline",
}

ONLINE_BACKGROUND_FILENAMES = [
    "Online Background.png",
    "Online Background.jpg",
    "Online_Background.png",
]

OFFLINE_BACKGROUND_FILENAMES = [
    "Offline Background.png",
    "Offline Background.jpg",
    "Offline_Background.png",
]

OFFLINE_ONE_FALLBACK_FILENAMES = [
    "Online Background.png",
    "Online Background.jpg",
    "Online_Background.png",
    "Sample Offline.png",
    "Sample Offline.jpg",
]

EXCEL_FILENAME = "Meetup Planning Sheet.xlsx"
FONT_FILENAME = "Helvetica-Bold.ttf"

OUTPUT_LOCAL_FOLDER = "posters_output"
LOCAL_OUTPUT_ROOT_CANDIDATES = {
    1: [os.path.join(OUTPUT_LOCAL_FOLDER, "One Speaker Posters"), os.path.join(OUTPUT_LOCAL_FOLDER, "1 Speaker")],
    2: [os.path.join(OUTPUT_LOCAL_FOLDER, "Two Speaker Posters"), os.path.join(OUTPUT_LOCAL_FOLDER, "2 Speakers")],
    3: [os.path.join(OUTPUT_LOCAL_FOLDER, "Three Speaker Posters"), os.path.join(OUTPUT_LOCAL_FOLDER, "3 Speakers")],
}

TEMP_FOLDER = "temp_downloads"
COMM_LOGOS_CACHE = os.path.join(TEMP_FOLDER, "community_logos")
GIFT_LOGOS_CACHE = os.path.join(TEMP_FOLDER, "gift_logos")
VENUE_LOGOS_CACHE = os.path.join(TEMP_FOLDER, "venue_logos")
CHECK_INTERVAL = 3600

PLATFORM_OUTPUT_ROOT = os.path.join(OUTPUT_LOCAL_FOLDER, "Platform Posters")
PLATFORM_SPECS = {
    "whatsapp": {"folder": "WhatsApp", "w": 1080, "h": 1920},
    "instagram": {"folder": "Instagram", "w": 1080, "h": 1350},
    "facebook": {"folder": "Facebook", "w": 1200, "h": 1500},
    "twitter": {"folder": "Twitter", "w": 1600, "h": 900},
    "linkedin": {"folder": "LinkedIn", "w": 1200, "h": 1500},
}


# =============================================================================
# EXCEL COLUMNS (CANONICAL NAMES)
# =============================================================================

COL_DATE = "Date"
COL_DAY = "Day"
COL_TIME = "Time"
COL_TITLE = "Title"
COL_TITLE1 = "Title1"
COL_MODE = "Mode"
COL_STATUS = "Status"
COL_NUM_SPEAKERS = "No. of Speakers"
COL_MEETUP_LINK = "Meetup link for Title/Sub Title/QR Code"
COL_VENUE_ADDR = "Venue Address"
COL_VENUE_SPONSOR_IMAGE = "Venue Sponsor Image"
COL_VENUE_SPONSOR_NAME = "Venue Sponsor Name"
COL_COMM_PART = "Community Partners"
COL_GIFT_SPONSOR = "Gift Sponsor"

COL_S1_NAME = "Speaker1"
COL_S1_ROLE = "Speaker1_Role"
COL_S1_COMPANY = "Speaker1_Company"
COL_S1_PHOTO = "Speaker1_Photo"
COL_S1_ADD_INFO = "S1_ADD_INFO"

COL_S2_NAME = "Speaker2"
COL_S2_ROLE = "Speaker2_Role"
COL_S2_COMPANY = "Speaker2_Company"
COL_S2_PHOTO = "Speaker2_Photo"
COL_S2_ADD_INFO = "S2_ADD_INFO"

COL_S3_NAME = "Speaker3"
COL_S3_ROLE = "Speaker3_Role"
COL_S3_COMPANY = "Speaker3_Company"
COL_S3_PHOTO = "Speaker3_Photo"
COL_S3_ADD_INFO = "S3_ADD_INFO"

COLUMN_ALIASES = {
    COL_DATE: ["Date"],
    COL_DAY: ["Day"],
    COL_TIME: ["Time"],
    COL_TITLE: ["Title"],
    COL_TITLE1: ["Title1"],
    COL_MODE: ["Mode"],
    COL_STATUS: ["Status"],
    COL_NUM_SPEAKERS: ["No. of Speakers"],
    COL_MEETUP_LINK: ["Meetup link for Title/Sub Title/QR Code"],
    COL_VENUE_ADDR: ["Venue Address", "Venue address"],
    COL_VENUE_SPONSOR_IMAGE: ["Venue Sponsor Image", "Venue Sponsar", "Tagging of venue"],
    COL_VENUE_SPONSOR_NAME: ["Venue Sponsor Name"],
    COL_COMM_PART: ["Community Partners", "Community partners", "Community Parterners"],
    COL_GIFT_SPONSOR: ["Gift Sponsor"],
    COL_S1_NAME: ["Speaker1"],
    COL_S1_ROLE: ["Speaker1_Role", "Speaker"],
    COL_S1_COMPANY: ["Speaker1_Company"],
    COL_S1_PHOTO: ["Speaker1_Photo"],
    COL_S1_ADD_INFO: ["S1_ADD_INFO"],
    COL_S2_NAME: ["Speaker2", "Speaker 2", "speakers"],
    COL_S2_ROLE: ["Speaker2_Role"],
    COL_S2_COMPANY: ["Speaker2_Company"],
    COL_S2_PHOTO: ["Speaker2_Photo"],
    COL_S2_ADD_INFO: ["S2_ADD_INFO"],
    COL_S3_NAME: ["Speaker3"],
    COL_S3_ROLE: ["Speaker3_Role"],
    COL_S3_COMPANY: ["Speaker3_Company"],
    COL_S3_PHOTO: ["Speaker3_Photo"],
    COL_S3_ADD_INFO: ["S3_ADD_INFO"],
}


# =============================================================================
# LAYOUTS
# =============================================================================

BASE_W = 2000
BASE_H = 1414
MM_TO_PX = 6.734
# Canva-extracted typography is specified in points. This factor is calibrated
# against the provided one-speaker online template placeholders.
POINT_TO_PIXEL_FACTOR = 2.1


def mm_to_px(mm_value):
    return round(mm_value * MM_TO_PX)


def pt_to_px(point_value):
    return max(1, int(round(float(point_value) * POINT_TO_PIXEL_FACTOR)))


ONLINE_LAYOUTS = {
    1: {
        "draw_static_labels": True,
        "qr": {"x": 9, "y": 15.30, "w": 39, "h": 39},
        "scan_to_register": {"x": 14, "y": 10, "w": 32, "h": 6.5, "size": 13, "color": "#ffffff"},
        "title": {"x": 53, "y": 14, "w": 193, "h": 37, "size": 30, "color": "#21459d"},
        "title1": {"x": 42, "y": 80, "w": 214, "h": 10, "size": 26, "color": "#004da7", "align": "center", "valign": "middle"},
        "series_text": {"x": 210, "y": 68.5, "w": 78, "h": 5, "size": 14, "color": "#ffffff", "valign": "middle", "font_family": "montserrat"},
        "day_date": {"x": 86, "y": 152, "w": 74, "h": 12.7, "size": 22, "color": "#ffffff", "align": "right", "valign": "middle"},
        "time": {"x": 168.0, "y": 152, "w": 84, "h": 12.7, "size": 22, "color": "#ffffff", "align": "left", "valign": "middle", "sync_y_with": "day_date", "sync_y_offset": -0.6},
        "mode": {"x": 133.5, "y": 164, "w": 61, "h": 12.7, "size": 22, "color": "#ffffff", "align": "center", "valign": "middle"},
        "speakers": [
            {
                "photo": {"x": 27, "y": 104, "w": 54.2, "h": 54.2, "radius": 12},
                "name": {"x": 86, "y": 120, "w": 140, "h": 12, "size": 26, "color": "#ffffff", "valign": "middle"},
                "role": {"x": 86, "y": 132, "w": 145, "h": 8, "size": 18, "color": "#ffffff", "valign": "middle"},
            }
        ],
        "free_text": {"x": 9, "y": 188, "w": 114, "h": 8, "size": 14, "color": "#ffffff", "valign": "middle", "stroke_width": 1},
        "community_heading": {"x": 200, "y": 173, "w": 88, "size": 13, "color": "#ffffff", "align": "center", "stroke_width": 1},
        "community": {
            "x": 198,
            "y": 178,
            "max_w": 90,
            "box_h": 23,
            "padding": 2,
            "corner_r": 2,
            "spacing": 1,
            "rect": {"w": 60, "h": 23},
            "square": {"w": 25, "h": 25},
        },
    },
    2: {
        "draw_static_labels": True,
        "qr": {"x": 9, "y": 15.30, "w": 39, "h": 39},
        "scan_to_register": {"x": 14, "y": 10, "w": 32, "h": 6.5, "size": 13, "color": "#ffffff"},
        "title": {"x": 53, "y": 14, "w": 193, "h": 37, "size": 30, "color": "#21459d"},
        "title1": {"x": 42, "y": 80, "w": 214, "h": 10, "size": 26, "color": "#004da7", "align": "center", "valign": "middle"},
        "series_text": {"x": 210, "y": 68.5, "w": 78, "h": 5, "size": 14, "color": "#ffffff", "valign": "middle", "font_family": "montserrat"},
        "day_date": {"x": 66, "y": 150, "w": 79, "h": 9.3, "size": 22, "color": "#ffffff", "align": "right", "valign": "middle"},
        "time": {"x": 153, "y": 150, "w": 79, "h": 9.3, "size": 22, "color": "#ffffff", "align": "left", "valign": "middle", "sync_y_with": "day_date", "sync_y_offset": -0.2},
        "mode": {"x": 116, "y": 163, "w": 66, "h": 9.3, "size": 22, "color": "#ffffff", "align": "center", "valign": "middle"},
        "speakers": [
            {
                "photo": {"x": 9.5, "y": 107.8, "w": 31, "h": 30, "radius": 8},
                "name": {"x": 44, "y": 116, "w": 78, "h": 7.6, "size": 17, "color": "#ffffff", "valign": "middle"},
                "role": {"x": 44, "y": 123, "w": 78, "h": 5.4, "size": 13, "color": "#ffffff", "valign": "middle"},
            },
            {
                "photo": {"x": 155, "y": 107.8, "w": 31, "h": 30, "radius": 8},
                "name": {"x": 189, "y": 116, "w": 78, "h": 7.6, "size": 17, "color": "#ffffff", "valign": "middle"},
                "role": {"x": 189, "y": 123, "w": 78, "h": 5.4, "size": 13, "color": "#ffffff", "valign": "middle"},
            },
        ],
        "free_text": {"x": 9, "y": 188, "w": 114, "h": 8, "size": 14, "color": "#ffffff", "valign": "middle", "stroke_width": 1},
        "community_heading": {"x": 200, "y": 173, "w": 88, "size": 13, "color": "#ffffff", "align": "center", "stroke_width": 1},
        "community": {
            "x": 198,
            "y": 178,
            "max_w": 90,
            "box_h": 23,
            "padding": 2,
            "corner_r": 2,
            "spacing": 1,
            "rect": {"w": 60, "h": 23},
            "square": {"w": 25, "h": 25},
        },
    },
    3: {
        "draw_static_labels": True,
        "qr": {"x": 9, "y": 15.30, "w": 39, "h": 39},
        "scan_to_register": {"x": 14, "y": 10, "w": 32, "h": 6.5, "size": 13, "color": "#ffffff"},
        "title": {"x": 53, "y": 14, "w": 193, "h": 37, "size": 30, "color": "#21459d"},
        "title1": {"x": 42, "y": 80, "w": 214, "h": 10, "size": 26, "color": "#004da7", "align": "center", "valign": "middle"},
        "series_text": {"x": 210, "y": 68.5, "w": 78, "h": 5, "size": 14, "color": "#ffffff", "valign": "middle", "font_family": "montserrat"},
        "day_date": {"x": 11, "y": 165.5, "w": 75, "h": 9, "size": 22, "color": "#ffffff", "align": "right", "valign": "middle"},
        "time": {"x": 94, "y": 165.5, "w": 75, "h": 9, "size": 22, "color": "#ffffff", "align": "left", "valign": "middle", "sync_y_with": "day_date", "sync_y_offset": -0.6},
        "mode": {"x": 62, "y": 179, "w": 57, "h": 9, "size": 22, "color": "#ffffff", "align": "center", "valign": "middle"},
        "speakers": [
            {
                "photo": {"x": 11.34, "y": 100, "w": 29, "h": 29, "radius": 8},
                "name": {"x": 44, "y": 108, "w": 72, "h": 7.6, "size": 14, "color": "#ffffff", "valign": "middle"},
                "role": {"x": 44, "y": 115, "w": 78, "h": 5.4, "size": 11, "color": "#ffffff", "valign": "middle"},
            },
            {
                "photo": {"x": 162, "y": 100, "w": 29, "h": 29, "radius": 8},
                "name": {"x": 194.5, "y": 108, "w": 72, "h": 7.6, "size": 14, "color": "#ffffff", "valign": "middle"},
                "role": {"x": 194.5, "y": 114.8, "w": 78, "h": 5.4, "size": 11, "color": "#ffffff", "valign": "middle"},
            },
            {
                "photo": {"x": 86.5, "y": 130, "w": 29, "h": 29, "radius": 8},
                "name": {"x": 117, "y": 138, "w": 72, "h": 7.6, "size": 14, "color": "#ffffff", "valign": "middle"},
                "role": {"x": 117, "y": 145, "w": 78, "h": 5.4, "size": 11, "color": "#ffffff", "valign": "middle"},
            },
        ],
        "free_text": {"x": 26, "y": 194, "w": 136, "h": 6.3, "size": 14, "color": "#ffffff", "valign": "middle", "stroke_width": 1},
        "community_heading": {"x": 216, "y": 173, "w": 72, "size": 13, "color": "#ffffff", "align": "center", "stroke_width": 1},
        "community": {
            "x": 216,
            "y": 178,
            "max_w": 72,
            "box_h": 23,
            "padding": 2,
            "corner_r": 2,
            "spacing": 1,
            "rect": {"w": 60, "h": 23},
            "square": {"w": 25, "h": 25},
        },
    },
}

OFFLINE_LAYOUTS = {
    1: {
        "draw_static_labels": True,
        "qr": {"x": 9, "y": 15.30, "w": 39, "h": 39},
        "scan_to_register": {"x": 14, "y": 10, "w": 32, "h": 6.5, "size": 13, "color": "#ffffff"},
        "title": {"x": 53, "y": 14, "w": 193, "h": 37, "size": 30, "color": "#21459d"},
        "title1": {"x": 42, "y": 80, "w": 214, "h": 10, "size": 26, "color": "#004da7", "align": "center", "valign": "middle"},
        "series_text": {"x": 210, "y": 68.5, "w": 78, "h": 5, "size": 14, "color": "#ffffff", "valign": "middle", "font_family": "montserrat"},
        "day_date": {"x": 199, "y": 100, "w": 89, "h": 9.06, "size": 17, "color": "#ffffff", "align": "right", "valign": "middle"},
        "time": {"x": 203, "y": 109.8, "w": 85, "h": 9.06, "size": 17, "color": "#ffffff", "align": "right", "valign": "middle"},
        "draw_mode": False,
        "speakers": [
            {
                "photo": {"x": 10.2, "y": 115, "w": 39, "h": 39, "radius": 8},
                "block": {
                    "align": "left",
                    "valign": "middle",
                    "center_to_photo": True,
                    "with_add": {"x": 52, "y": 127, "w": 107, "h": 16.25, "name_size": 14, "role_size": 13, "add_size": 10, "line_gap_mm": 1},
                    "without_add": {"x": 53, "y": 127, "w": 107, "h": 14, "name_size": 19, "role_size": 16, "line_gap_mm": 1},
                },
            }
        ],
        "free_text": {"x": 10, "y": 191, "w": 130.5, "h": 6, "size": 14, "color": "#ffffff", "valign": "middle", "stroke_width": 1},
        "venue_logo_box": {"x": 239, "y": 123, "w": 48, "h": 23, "draw_box": True, "padding": 1, "corner_r": 2},
        "venue_text_block": {"x": 130, "y": 148, "w": 158, "h": 26, "name_size": 19, "address_size": 17, "align": "right", "line_gap_mm": 1, "justify_address": True, "auto_width": True, "pad_mm": 1.5},
        "gift_heading": {"x": 169, "y": 183, "w": 45, "size": 13, "color": "#ffffff", "align": "center", "stroke_width": 1},
        "gift_heading_text": "GIFT SPONSORS",
        "gift": {
            "x": 169,
            "y": 188,
            "max_w": 45,
            "min_w": 20,
            "box_h": 16,
            "padding": 1.5,
            "corner_r": 2,
            "spacing": 1,
            "dynamic_width": True,
            "rect": {"w": 60, "h": 23},
            "square": {"w": 25, "h": 25},
        },
        "community_heading": {"x": 216, "y": 183, "w": 72, "size": 13, "color": "#ffffff", "align": "center", "stroke_width": 1},
        "community_heading_text": "COMMUNITY PARTNERS",
        "community": {
            "x": 216,
            "y": 188,
            "max_w": 72,
            "min_w": 24,
            "box_h": 16,
            "padding": 1.5,
            "corner_r": 2,
            "spacing": 1,
            "dynamic_width": True,
            "rect": {"w": 60, "h": 23},
            "square": {"w": 25, "h": 25},
        },
        "sponsor_gap_mm": 2,
        "community_follow_gift": True,
    },
    2: {
        "draw_static_labels": True,
        "qr": {"x": 9, "y": 15.30, "w": 39, "h": 39},
        "scan_to_register": {"x": 14, "y": 10, "w": 32, "h": 6.5, "size": 13, "color": "#ffffff"},
        "title": {"x": 53, "y": 14, "w": 193, "h": 37, "size": 30, "color": "#21459d"},
        "title1": {"x": 42, "y": 80, "w": 214, "h": 10, "size": 26, "color": "#004da7", "align": "center", "valign": "middle"},
        "series_text": {"x": 210, "y": 68.5, "w": 78, "h": 5, "size": 14, "color": "#ffffff", "valign": "middle", "font_family": "montserrat"},
        "day_date": {"x": 199, "y": 100, "w": 89, "h": 9.06, "size": 17, "color": "#ffffff", "align": "right", "valign": "middle"},
        "time": {"x": 203, "y": 109.8, "w": 85, "h": 9.06, "size": 17, "color": "#ffffff", "align": "right", "valign": "middle"},
        "draw_mode": False,
        "speakers": [
            {
                "photo": {"x": 8.5, "y": 99, "w": 35, "h": 35, "radius": 6},
                "block": {
                    "align": "left",
                    "valign": "middle",
                    "with_add": {"x": 47, "y": 108, "w": 89, "h": 16, "name_size": 13, "role_size": 11, "add_size": 9, "line_gap_mm": 1},
                    "without_add": {"x": 47, "y": 108, "w": 89, "h": 16, "name_size": 17, "role_size": 13, "line_gap_mm": 1},
                },
            },
            {
                "photo": {"x": 8.5, "y": 140, "w": 35, "h": 35, "radius": 6},
                "block": {
                    "align": "left",
                    "valign": "middle",
                    "with_add": {"x": 47, "y": 150, "w": 89, "h": 16, "name_size": 13, "role_size": 11, "add_size": 9, "line_gap_mm": 1},
                    "without_add": {"x": 47, "y": 150, "w": 89, "h": 16, "name_size": 17, "role_size": 13, "line_gap_mm": 1},
                },
            },
        ],
        "free_text": {"x": 10, "y": 191, "w": 130.5, "h": 6, "size": 14, "color": "#ffffff", "valign": "middle", "stroke_width": 1},
        "venue_logo_box": {"x": 239, "y": 123, "w": 48, "h": 23, "draw_box": True, "padding": 1, "corner_r": 2},
        "venue_text_block": {"x": 164, "y": 148, "w": 124, "h": 26, "name_size": 19, "address_size": 17, "align": "right", "line_gap_mm": 1, "justify_address": True, "auto_width": False},
        "gift_heading": {"x": 169, "y": 183, "w": 45, "size": 13, "color": "#ffffff", "align": "center", "stroke_width": 1},
        "gift_heading_text": "GIFT SPONSORS",
        "gift": {
            "x": 169,
            "y": 188,
            "max_w": 45,
            "min_w": 20,
            "box_h": 16,
            "padding": 1.5,
            "corner_r": 2,
            "spacing": 1,
            "dynamic_width": True,
            "rect": {"w": 60, "h": 23},
            "square": {"w": 25, "h": 25},
        },
        "community_heading": {"x": 216, "y": 183, "w": 72, "size": 13, "color": "#ffffff", "align": "center", "stroke_width": 1},
        "community_heading_text": "COMMUNITY PARTNERS",
        "community": {
            "x": 216,
            "y": 188,
            "max_w": 72,
            "min_w": 24,
            "box_h": 16,
            "padding": 1.5,
            "corner_r": 2,
            "spacing": 1,
            "dynamic_width": True,
            "rect": {"w": 60, "h": 23},
            "square": {"w": 25, "h": 25},
        },
        "sponsor_gap_mm": 2,
        "community_follow_gift": True,
    },
    3: {
        "draw_static_labels": True,
        "qr": {"x": 9, "y": 15.30, "w": 39, "h": 39},
        "scan_to_register": {"x": 14, "y": 10, "w": 32, "h": 6.5, "size": 13, "color": "#ffffff"},
        "title": {"x": 53, "y": 14, "w": 193, "h": 37, "size": 30, "color": "#21459d"},
        "title1": {"x": 42, "y": 80, "w": 214, "h": 10, "size": 26, "color": "#004da7", "align": "center", "valign": "middle"},
        "series_text": {"x": 210, "y": 68.5, "w": 78, "h": 5, "size": 14, "color": "#ffffff", "valign": "middle", "font_family": "montserrat"},
        "day_date": {"x": 199, "y": 100, "w": 89, "h": 9.06, "size": 17, "color": "#ffffff", "align": "right", "valign": "middle"},
        "time": {"x": 203, "y": 109.8, "w": 85, "h": 9.06, "size": 17, "color": "#ffffff", "align": "right", "valign": "middle"},
        "draw_mode": False,
        "speakers": [
            {
                "photo": {"x": 6.5, "y": 99, "w": 29, "h": 29, "radius": 6},
                "block": {
                    "align": "left",
                    "valign": "middle",
                    "center_to_photo_without_add": True,
                    "with_add": {"x": 39, "y": 107, "w": 75, "h": 13, "name_size": 14, "role_size": 11, "add_size": 9, "line_gap_mm": 1},
                    "without_add": {"x": 39, "y": 107, "w": 75, "h": 13, "name_size": 16, "role_size": 11, "line_gap_mm": 1},
                },
            },
            {
                "photo": {"x": 6.5, "y": 132, "w": 29, "h": 29, "radius": 6},
                "block": {
                    "align": "left",
                    "valign": "middle",
                    "center_to_photo_without_add": True,
                    "with_add": {"x": 39, "y": 139.4, "w": 75, "h": 13, "name_size": 14, "role_size": 11, "add_size": 9, "line_gap_mm": 1},
                    "without_add": {"x": 39, "y": 139.4, "w": 75, "h": 13, "name_size": 16, "role_size": 11, "line_gap_mm": 1},
                },
            },
            {
                "photo": {"x": 6.5, "y": 164, "w": 29, "h": 29, "radius": 6},
                "block": {
                    "align": "left",
                    "valign": "middle",
                    "center_to_photo_without_add": True,
                    "with_add": {"x": 39, "y": 172, "w": 75, "h": 13, "name_size": 14, "role_size": 11, "add_size": 9, "line_gap_mm": 1},
                    "without_add": {"x": 39, "y": 172, "w": 75, "h": 13, "name_size": 16, "role_size": 11, "line_gap_mm": 1},
                },
            },
        ],
        "free_text_text": "THIS IS EVENT IS FREE AND OPEN FOR ALL GENDERS",
        "free_text": {"x": 17, "y": 200, "w": 128, "h": 6, "size": 14, "color": "#ffffff", "valign": "middle", "stroke_width": 1},
        "venue_logo_box": {"x": 239, "y": 123, "w": 48, "h": 23, "draw_box": True, "padding": 1, "corner_r": 2},
        "venue_text_block": {"x": 154, "y": 148, "w": 134, "h": 26, "name_size": 19, "address_size": 17, "align": "right", "line_gap_mm": 1, "justify_address": True, "auto_width": False},
        "gift_heading": {"x": 169, "y": 183, "w": 45, "size": 13, "color": "#ffffff", "align": "center", "stroke_width": 1},
        "gift_heading_text": "GIFT SPONSORS",
        "gift": {
            "x": 169,
            "y": 188,
            "max_w": 45,
            "min_w": 20,
            "box_h": 16,
            "padding": 1.5,
            "corner_r": 2,
            "spacing": 1,
            "dynamic_width": True,
            "rect": {"w": 60, "h": 23},
            "square": {"w": 25, "h": 25},
        },
        "community_heading": {"x": 216, "y": 183, "w": 72, "size": 13, "color": "#ffffff", "align": "center", "stroke_width": 1},
        "community_heading_text": "COMMUNITY PARTNERS",
        "community": {
            "x": 216,
            "y": 188,
            "max_w": 72,
            "min_w": 24,
            "box_h": 16,
            "padding": 1.5,
            "corner_r": 2,
            "spacing": 1,
            "dynamic_width": True,
            "rect": {"w": 60, "h": 23},
            "square": {"w": 25, "h": 25},
        },
        "sponsor_gap_mm": 2,
        "community_follow_gift": True,
    },
}


os.makedirs(TEMP_FOLDER, exist_ok=True)
os.makedirs(COMM_LOGOS_CACHE, exist_ok=True)
os.makedirs(GIFT_LOGOS_CACHE, exist_ok=True)
os.makedirs(VENUE_LOGOS_CACHE, exist_ok=True)
os.makedirs(OUTPUT_LOCAL_FOLDER, exist_ok=True)

generated_posters = set()
# Focus generation to a single variant when tuning layouts.
# Set to None to process all matching upcoming rows.
FOCUS_SPEAKER_MODE = None


class GoogleDriveManager:
    def __init__(self):
        self.drive = GDriveManager(
            credentials_file=OAUTH_CREDENTIALS_FILE,
            token_file=OAUTH_TOKEN_FILE,
            service_account_file=SERVICE_ACCOUNT_FILE,
            use_service_account=False,
        )
        self.base_folder_id = None
        self.speaker_photos_folder_id = None
        self.community_logos_folder_id = None
        self.gift_sponsors_folder_id = None
        self.venue_sponsors_folder_id = None
        self._resolve_base_folder()
        self._resolve_subfolders()

    def _resolve_base_folder(self):
        self.base_folder_id = self.drive.find_folder(GDRIVE_BASE_FOLDER)
        if self.base_folder_id:
            logger.info("Found '%s' (id: %s)", GDRIVE_BASE_FOLDER, self.base_folder_id)

    def _resolve_subfolders(self):
        if not self.base_folder_id:
            return
        for attr, name in [
            ("speaker_photos_folder_id", SPEAKER_PHOTOS_FOLDER),
            ("community_logos_folder_id", GDRIVE_COMMUNITY_FOLDER),
            ("gift_sponsors_folder_id", GDRIVE_GIFT_FOLDER),
            ("venue_sponsors_folder_id", GDRIVE_VENUE_FOLDER),
        ]:
            fid = self.drive.find_folder(name, self.base_folder_id)
            if fid:
                setattr(self, attr, fid)
                logger.info("Found subfolder '%s' (id: %s)", name, fid)

    def find_file(self, name, parent_id):
        return self.drive.find_file(name, parent_id)

    def find_file_case_insensitive(self, name, parent_id):
        if not parent_id or not name:
            return None
        fid = self.drive.find_file(name, parent_id)
        if fid:
            return fid
        name_l = str(name).strip().lower()
        for item in self.drive.list_files(parent_id, max_results=200):
            if item.get("name", "").strip().lower() == name_l:
                return item.get("id")
        return None

    def find_folder(self, name, parent_id):
        return self.drive.find_folder(name, parent_id)

    def create_folder(self, name, parent_id):
        return self.drive.create_folder(name, parent_id)

    def download_file(self, file_id, save_path):
        return self.drive.download_file(file_id, save_path)

    def download_by_link(self, link, save_path):
        fid = _extract_file_id(link)
        if not fid:
            return False
        return self.download_file(fid, save_path)

    def upload_image(self, local_path, folder_id):
        return self.drive.upload_file(local_path=local_path, folder_id=folder_id, replace_existing=True)


def _txt(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() == "nan":
        return None
    return text


def _normalize_columns(df):
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    rename_map = {}
    cols = set(out.columns)
    for canonical, aliases in COLUMN_ALIASES.items():
        if canonical in cols:
            continue
        for alias in aliases:
            if alias in cols:
                rename_map[alias] = canonical
                break
    if rename_map:
        out = out.rename(columns=rename_map)
    return out


def _sanitize_filename(value):
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", str(value))
    cleaned = cleaned.replace("'", "_")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "untitled"


def _extract_file_id(link):
    if not link:
        return None
    link = str(link).strip()
    match = re.search(r"/d/([a-zA-Z0-9_-]{20,})", link)
    if match:
        return match.group(1)
    match = re.search(r"[?&]id=([a-zA-Z0-9_-]{20,})", link)
    if match:
        return match.group(1)
    if re.match(r"^[a-zA-Z0-9_-]{20,}$", link):
        return link
    return None


def _split_sources(value):
    if not value:
        return []
    return [item.strip() for item in re.split(r"[,;\n]+", str(value)) if item.strip()]


def _load_font(font_path, size, font_family=None):
    family_candidates = []
    if font_family:
        fam = str(font_family).strip().lower()
        if fam == "montserrat":
            family_candidates.extend(
                [
                    "C:/Windows/Fonts/Montserrat-Regular.ttf",
                    "C:/Windows/Fonts/Montserrat Medium.ttf",
                    "C:/Windows/Fonts/Montserrat-Medium.ttf",
                    "Montserrat-Regular.ttf",
                    "Montserrat.ttf",
                ]
            )

    for path in family_candidates + [font_path, "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf", "arialbd.ttf", "arial.ttf"]:
        try:
            return ImageFont.truetype(path, int(size))
        except (IOError, OSError):
            pass
    return ImageFont.load_default()


def _text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _hex_to_rgb(value):
    value = value.strip().lstrip("#")
    if len(value) != 6:
        return (255, 255, 255)
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _draw_title_block(draw, text, font_path, cfg):
    if not text:
        return
    base_size = pt_to_px(cfg.get("size", 30))
    x = mm_to_px(cfg["x"])
    y = mm_to_px(cfg["y"])
    w = mm_to_px(cfg["w"])
    h = mm_to_px(cfg.get("h", 20))
    color = _hex_to_rgb(cfg.get("color", "#ffffff"))
    line_gap = max(2, int(base_size * 0.22))

    best_font = _load_font(font_path, base_size)
    best_lines = [text]

    for size in range(base_size, max(12, int(base_size * 0.5)), -2):
        font = _load_font(font_path, size)
        words = text.split()
        lines = []
        current = []
        for word in words:
            trial = " ".join(current + [word])
            if current and _text_width(draw, trial, font) > w:
                lines.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            lines.append(" ".join(current))
        total_h = len(lines) * size + max(0, len(lines) - 1) * line_gap
        if total_h <= h and all(_text_width(draw, line, font) <= w for line in lines):
            best_font = font
            best_lines = lines
            break

    total_h = len(best_lines) * best_font.size + max(0, len(best_lines) - 1) * line_gap
    y0 = y + max(0, (h - total_h) // 2)
    for line in best_lines:
        tx = x + max(0, (w - _text_width(draw, line, best_font)) // 2)
        draw.text((tx, y0), line, font=best_font, fill=color)
        y0 += best_font.size + line_gap


def _draw_text_box(draw, text, font_path, cfg, default_color="#ffffff"):
    if not text or not cfg:
        return
    font = _load_font(font_path, pt_to_px(cfg.get("size", 16)), font_family=cfg.get("font_family"))
    x = mm_to_px(cfg["x"])
    y = mm_to_px(cfg["y"])
    w = mm_to_px(cfg.get("w", 10))
    align = cfg.get("align", "left")
    valign = cfg.get("valign", "top")
    color = _hex_to_rgb(cfg.get("color", default_color))
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    draw_y = y
    if "h" in cfg and valign in ("middle", "center"):
        box_h = mm_to_px(cfg["h"])
        draw_y = y + (box_h - text_h) // 2
    if align == "center":
        draw_x = x + (w - text_w) // 2
    elif align == "right":
        draw_x = x + w - text_w
    else:
        draw_x = x
    stroke_w = int(cfg.get("stroke_width", 0))
    if stroke_w > 0:
        draw.text((draw_x, draw_y), text, font=font, fill=color, stroke_width=stroke_w, stroke_fill=color)
    else:
        draw.text((draw_x, draw_y), text, font=font, fill=color)


def _draw_text_lines_box(draw, lines, sizes_pt, font_path, cfg, default_color="#ffffff"):
    if not cfg or not lines or not sizes_pt:
        return

    pairs = []
    for text, size_pt in zip(lines, sizes_pt):
        if text is None:
            continue
        clean = str(text).strip()
        if not clean:
            continue
        pairs.append((clean, float(size_pt)))
    if not pairs:
        return

    x = mm_to_px(cfg["x"])
    y = mm_to_px(cfg["y"])
    w = mm_to_px(cfg.get("w", 10))
    h = mm_to_px(cfg.get("h", 10))
    align = cfg.get("align", "left")
    valign = cfg.get("valign", "top")
    color = _hex_to_rgb(cfg.get("color", default_color))
    font_family = cfg.get("font_family")
    stroke_w = int(cfg.get("stroke_width", 0))

    prepared = []
    total_text_h = 0
    for text, size_pt in pairs:
        font = _load_font(font_path, pt_to_px(size_pt), font_family=font_family)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        prepared.append((text, font, tw, th))
        total_text_h += th

    n = len(prepared)
    if n == 1:
        gap = 0
    else:
        if "line_gap_px" in cfg:
            gap = int(cfg.get("line_gap_px", 0))
        elif "line_gap_mm" in cfg:
            gap = mm_to_px(float(cfg.get("line_gap_mm", 0)))
        else:
            auto_gap = (h - total_text_h) // (n - 1) if h > total_text_h else 0
            gap = int(max(0, auto_gap))
    content_h = total_text_h + gap * max(0, n - 1)

    draw_y = y
    if valign in ("middle", "center"):
        draw_y = y + max(0, (h - content_h) // 2)

    for text, font, text_w, text_h in prepared:
        if align == "center":
            draw_x = x + (w - text_w) // 2
        elif align == "right":
            draw_x = x + w - text_w
        else:
            draw_x = x
        if stroke_w > 0:
            draw.text((draw_x, draw_y), text, font=font, fill=color, stroke_width=stroke_w, stroke_fill=color)
        else:
            draw.text((draw_x, draw_y), text, font=font, fill=color)
        draw_y += text_h + gap


def _wrap_text_to_width(draw, text, font, max_width_px):
    text = (text or "").strip()
    if not text:
        return []
    words = text.split()
    if not words:
        return []
    lines = []
    current = [words[0]]
    for word in words[1:]:
        trial = " ".join(current + [word])
        if _text_width(draw, trial, font) <= max_width_px:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def _draw_line(draw, text, font, color, x, y, w, align="left", justify=False):
    text = (text or "").strip()
    if not text:
        return
    if justify:
        words = text.split()
        if len(words) > 1:
            words_w = sum(_text_width(draw, word, font) for word in words)
            gaps = len(words) - 1
            free = max(0, w - words_w)
            gap_w = free / gaps if gaps else 0
            cursor_x = float(x)
            for idx, word in enumerate(words):
                draw.text((cursor_x, y), word, font=font, fill=color)
                cursor_x += _text_width(draw, word, font)
                if idx < gaps:
                    cursor_x += gap_w
            return

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    if align == "center":
        draw_x = x + (w - text_w) // 2
    elif align == "right":
        draw_x = x + w - text_w
    else:
        draw_x = x
    draw.text((draw_x, y), text, font=font, fill=color)


def _draw_venue_text_block(draw, venue_name, venue_addr, font_path, cfg):
    if not cfg or (not venue_name and not venue_addr):
        return
    x = mm_to_px(cfg["x"])
    y = mm_to_px(cfg["y"])
    w = mm_to_px(cfg["w"])
    h = mm_to_px(cfg.get("h", 10))
    align = cfg.get("align", "right")
    color = _hex_to_rgb(cfg.get("color", "#ffffff"))
    gap = mm_to_px(float(cfg.get("line_gap_mm", 1)))
    justify_addr = bool(cfg.get("justify_address", True))
    auto_width = bool(cfg.get("auto_width", False))
    pad_px = mm_to_px(float(cfg.get("pad_mm", 1.5)))

    name_font = _load_font(font_path, pt_to_px(cfg.get("name_size", 19)))
    addr_font = _load_font(font_path, pt_to_px(cfg.get("address_size", 17)))
    addr_text = (venue_addr or "").strip()
    addr_paragraphs = [ln.strip() for ln in addr_text.replace("\r", "").split("\n") if ln.strip()] if addr_text else []
    if not addr_paragraphs and addr_text:
        addr_paragraphs = [addr_text]

    # Optional auto-width: shrink the address/sponsor text region to content width
    # while preserving right-edge alignment of the original box.
    if auto_width:
        sponsor_line = f"Venue Sponsor : {venue_name}" if venue_name else ""
        sponsor_w = _text_width(draw, sponsor_line, name_font) if sponsor_line else 0
        para_w = 0
        for para in addr_paragraphs:
            para_w = max(para_w, _text_width(draw, para, addr_font))
        desired_w = max(sponsor_w, para_w)
        if desired_w > 0:
            effective_w = min(w, desired_w + 2 * pad_px)
            x = x + max(0, w - effective_w)
            w = effective_w

    cursor_y = y

    if venue_name:
        sponsor_line = f"Venue Sponsor : {venue_name}"
        _draw_line(draw, sponsor_line, name_font, color, x, cursor_y, w, align=align, justify=False)
        sponsor_h = draw.textbbox((0, 0), sponsor_line, font=name_font)[3] - draw.textbbox((0, 0), sponsor_line, font=name_font)[1]
        cursor_y += sponsor_h + gap

    remaining_h = max(0, (y + h) - cursor_y)
    if venue_addr and remaining_h > 0:
        addr_lines = []
        for para in addr_paragraphs:
            wrapped = _wrap_text_to_width(draw, para, addr_font, w)
            addr_lines.extend(wrapped if wrapped else [para])

        for idx, line in enumerate(addr_lines):
            # Avoid stretching the final line (or single-line address) unnaturally.
            do_justify = justify_addr and idx < len(addr_lines) - 1
            _draw_line(draw, line, addr_font, color, x, cursor_y, w, align=align, justify=do_justify)
            line_h = draw.textbbox((0, 0), line, font=addr_font)[3] - draw.textbbox((0, 0), line, font=addr_font)[1]
            cursor_y += line_h + gap
            if cursor_y > y + h:
                break


def _detect_top_right_logo_size_px(image):
    """
    Detect top-right W-logo white square size from background.
    Returns side length in pixels or None.
    """
    arr = np.array(image.convert("RGB"))
    h, w, _ = arr.shape
    y_max = int(h * 0.35)
    x_min = int(w * 0.60)
    roi = arr[:y_max, x_min:]
    mask = (roi[:, :, 0] > 220) & (roi[:, :, 1] > 220) & (roi[:, :, 2] > 220)
    hh, ww = mask.shape
    visited = np.zeros_like(mask, dtype=bool)

    best_area = 0
    best_side = None

    directions = ((1, 0), (-1, 0), (0, 1), (0, -1))
    for y in range(hh):
        for x in range(ww):
            if not mask[y, x] or visited[y, x]:
                continue
            q = deque([(x, y)])
            visited[y, x] = True
            count = 0
            min_x = max_x = x
            min_y = max_y = y

            while q:
                cx, cy = q.popleft()
                count += 1
                if cx < min_x:
                    min_x = cx
                if cx > max_x:
                    max_x = cx
                if cy < min_y:
                    min_y = cy
                if cy > max_y:
                    max_y = cy
                for dx, dy in directions:
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < ww and 0 <= ny < hh and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        q.append((nx, ny))

            bw = max_x - min_x + 1
            bh = max_y - min_y + 1
            ratio = bw / max(1, bh)
            if count < 2000:
                continue
            if ratio < 0.80 or ratio > 1.20:
                continue
            if bw < 120 or bh < 120:
                continue
            if count > best_area:
                best_area = count
                best_side = min(bw, bh)

    return best_side


def _generate_qr(url, size=264):
    if not url:
        return None
    try:
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("1").convert("RGB")
        return img.resize((size, size), Image.NEAREST)
    except Exception:
        return None


def _add_rounded_corners(img, radius):
    img = img.convert("RGBA")
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    drawer = ImageDraw.Draw(mask)
    drawer.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=max(0, radius), fill=255)
    img.putalpha(mask)
    return img


def _make_platform_canvas(master_rgb, target_w, target_h):
    # Background layer: fill canvas with center-cropped, blurred image.
    base = master_rgb.copy()
    bg_scale = max(target_w / max(1, base.width), target_h / max(1, base.height))
    bg_w = max(1, int(round(base.width * bg_scale)))
    bg_h = max(1, int(round(base.height * bg_scale)))
    bg = base.resize((bg_w, bg_h), Image.LANCZOS)
    crop_x = max(0, (bg_w - target_w) // 2)
    crop_y = max(0, (bg_h - target_h) // 2)
    bg = bg.crop((crop_x, crop_y, crop_x + target_w, crop_y + target_h))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=18))

    # Dark overlay to improve foreground separation.
    overlay = Image.new("RGB", (target_w, target_h), (20, 25, 45))
    bg = Image.blend(bg, overlay, alpha=0.32)

    # Foreground layer: keep full poster visible with margins.
    pad_w = int(round(target_w * 0.04))
    pad_h = int(round(target_h * 0.04))
    max_w = max(1, target_w - 2 * pad_w)
    max_h = max(1, target_h - 2 * pad_h)
    fg_scale = min(max_w / max(1, base.width), max_h / max(1, base.height))
    fg_w = max(1, int(round(base.width * fg_scale)))
    fg_h = max(1, int(round(base.height * fg_scale)))
    fg = base.resize((fg_w, fg_h), Image.LANCZOS)
    fg = fg.filter(ImageFilter.UnsharpMask(radius=0.8, percent=120, threshold=1))

    # Soft card/shadow effect for better platform readability.
    card = Image.new("RGBA", (fg_w + 8, fg_h + 8), (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(card)
    cdraw.rounded_rectangle([(0, 0), (fg_w + 7, fg_h + 7)], radius=10, fill=(0, 0, 0, 80))
    fx = (target_w - fg_w) // 2
    fy = (target_h - fg_h) // 2
    bg_rgba = bg.convert("RGBA")
    bg_rgba.paste(card, (fx - 2, fy + 2), card)

    frame = Image.new("RGBA", (fg_w + 4, fg_h + 4), (255, 255, 255, 0))
    fdraw = ImageDraw.Draw(frame)
    fdraw.rounded_rectangle([(0, 0), (fg_w + 3, fg_h + 3)], radius=8, outline=(255, 255, 255, 110), width=2)
    bg_rgba.paste(fg.convert("RGBA"), (fx, fy), fg.convert("RGBA"))
    bg_rgba.paste(frame, (fx - 2, fy - 2), frame)
    return bg_rgba.convert("RGB")


def _platform_output_dir(speaker_count, mode, platform_key):
    platform_folder = PLATFORM_SPECS[platform_key]["folder"]
    speaker_folder = SPEAKER_FOLDER_BY_COUNT.get(speaker_count, f"{speaker_count} Speaker")
    mode_folder = MODE_FOLDER_BY_KEY.get(mode, mode.title())
    out_dir = os.path.join(PLATFORM_OUTPUT_ROOT, platform_folder, speaker_folder, mode_folder)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def generate_platform_variants(master_poster_path, speaker_count, mode, filename_stem):
    if not master_poster_path or not os.path.exists(master_poster_path):
        return []
    try:
        master = Image.open(master_poster_path).convert("RGB")
    except Exception as exc:
        logger.warning("Cannot open master poster for platform export: %s", exc)
        return []

    outputs = []
    for platform_key, spec in PLATFORM_SPECS.items():
        canvas = _make_platform_canvas(master, int(spec["w"]), int(spec["h"]))
        out_dir = _platform_output_dir(speaker_count, mode, platform_key)
        out_name = f"{filename_stem}_{platform_key}.png"
        out_path = os.path.join(out_dir, out_name)
        canvas.save(out_path, "PNG")
        outputs.append(out_path)
        logger.info("Platform poster saved: %s", out_path)
    return outputs


def _scale_layout_value(key, value, sx, sy, fs):
    if not isinstance(value, (int, float)):
        return value
    if key in ("x", "w", "max_w", "min_w"):
        return float(value) * sx
    if key in ("y", "h", "box_h"):
        return float(value) * sy
    if key in ("size", "name_size", "role_size", "add_size", "address_size"):
        return max(1.0, float(value) * fs)
    if key in ("spacing", "padding", "corner_r", "radius", "line_gap_mm", "pad_mm"):
        return max(0.0, float(value) * fs)
    return value


def _scale_layout_tree(node, sx, sy, fs):
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if isinstance(v, (dict, list)):
                out[k] = _scale_layout_tree(v, sx, sy, fs)
            else:
                out[k] = _scale_layout_value(k, v, sx, sy, fs)
        return out
    if isinstance(node, list):
        return [_scale_layout_tree(item, sx, sy, fs) for item in node]
    return node


def _scaled_layout_for_target(layout, target_w, target_h):
    sx = float(target_w) / float(BASE_W)
    sy = float(target_h) / float(BASE_H)
    fs = min(sx, sy)
    layout_copy = copy.deepcopy(layout)
    return _scale_layout_tree(layout_copy, sx, sy, fs)


def _reflow_speaker_slot(base_slot, scaled_slot, sx, sy, fs):
    base_photo = base_slot.get("photo")
    scaled_photo = scaled_slot.get("photo")
    if base_photo and scaled_photo:
        # Prevent non-uniform stretch: keep speaker photos square.
        side = min(float(base_photo.get("w", 0)) * sx, float(base_photo.get("h", 0)) * sy)
        cx = float(scaled_photo.get("x", 0)) + float(scaled_photo.get("w", side)) / 2.0
        cy = float(scaled_photo.get("y", 0)) + float(scaled_photo.get("h", side)) / 2.0
        scaled_photo["w"] = side
        scaled_photo["h"] = side
        scaled_photo["x"] = cx - side / 2.0
        scaled_photo["y"] = cy - side / 2.0
        if "radius" in base_photo:
            scaled_photo["radius"] = max(1.0, float(base_photo.get("radius", 0)) * fs)

    # Keep speaker text block centered to speaker photo like original composition.
    base_name = base_slot.get("name")
    base_role = base_slot.get("role")
    scaled_name = scaled_slot.get("name")
    scaled_role = scaled_slot.get("role")
    if not (base_photo and scaled_photo and base_name and base_role and scaled_name and scaled_role):
        return
    if "h" not in base_name or "h" not in base_role:
        return

    b_top = min(float(base_name["y"]), float(base_role["y"]))
    b_bottom = max(float(base_name["y"]) + float(base_name["h"]), float(base_role["y"]) + float(base_role["h"]))
    b_h = b_bottom - b_top
    if b_h <= 0:
        return

    b_photo_cy = float(base_photo["y"]) + float(base_photo["h"]) / 2.0
    b_block_cy = b_top + b_h / 2.0
    offset = b_block_cy - b_photo_cy

    s_photo_cy = float(scaled_photo["y"]) + float(scaled_photo["h"]) / 2.0
    s_h = b_h * fs
    s_top = s_photo_cy + (offset * fs) - s_h / 2.0

    for key, b_cfg in (("name", base_name), ("role", base_role)):
        s_cfg = scaled_slot.get(key)
        if not s_cfg:
            continue
        rel = (float(b_cfg["y"]) - b_top) / b_h
        s_cfg["y"] = s_top + rel * s_h
        if "h" in b_cfg:
            s_cfg["h"] = float(b_cfg["h"]) * fs


def _adjust_responsive_layout_for_platform(base_layout, scaled_layout, speaker_count, mode, sx, sy):
    # For one-speaker online, keep speaker photo/details visually balanced on all aspect ratios.
    if not (mode == "online" and speaker_count == 1):
        return scaled_layout
    fs = min(sx, sy)
    base_speakers = base_layout.get("speakers", [])
    scaled_speakers = scaled_layout.get("speakers", [])
    for idx in range(min(len(base_speakers), len(scaled_speakers))):
        _reflow_speaker_slot(base_speakers[idx], scaled_speakers[idx], sx, sy, fs)
    return scaled_layout


def generate_platform_variants_responsive(
    row,
    drive,
    background_path,
    font_path,
    speaker_count,
    mode,
    filename_stem,
):
    base_layout = ONLINE_LAYOUTS[speaker_count] if mode == "online" else OFFLINE_LAYOUTS[speaker_count]
    outputs = []
    for platform_key, spec in PLATFORM_SPECS.items():
        target_w = int(spec["w"])
        target_h = int(spec["h"])
        sx = float(target_w) / float(BASE_W)
        sy = float(target_h) / float(BASE_H)
        scaled_layout = _scaled_layout_for_target(base_layout, target_w, target_h)
        scaled_layout = _adjust_responsive_layout_for_platform(base_layout, scaled_layout, speaker_count, mode, sx, sy)
        out_dir = _platform_output_dir(speaker_count, mode, platform_key)
        out_name = f"{filename_stem}_{platform_key}.png"
        out_path = os.path.join(out_dir, out_name)
        result = generate_event_poster(
            row=row,
            drive=drive,
            background_path=background_path,
            font_path=font_path,
            speaker_count=speaker_count,
            mode=mode,
            layout_override=scaled_layout,
            target_size=(target_w, target_h),
            out_path_override=out_path,
        )
        if result:
            outputs.append(result)
            logger.info("Responsive platform poster saved: %s", result)
    return outputs


def _prepare_image_for_box(image, target_w, target_h):
    src_w, src_h = image.size
    if src_w <= 0 or src_h <= 0 or target_w <= 0 or target_h <= 0:
        return None
    src_ratio = src_w / src_h
    target_ratio = target_w / target_h
    img = image
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        x0 = (src_w - new_w) // 2
        img = img.crop((x0, 0, x0 + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio)
        y0 = (src_h - new_h) // 2
        img = img.crop((0, y0, src_w, y0 + new_h))
    return img.resize((target_w, target_h), Image.LANCZOS)


def _trim_logo_margins(image):
    rgba = image.convert("RGBA")
    px = rgba.load()
    w, h = rgba.size

    # Detect "content" pixels: visible and not near-white.
    content = []
    for y in range(h):
        row_has_content = False
        for x in range(w):
            r, g, b, a = px[x, y]
            if a > 10 and (r < 245 or g < 245 or b < 245):
                row_has_content = True
                content.append((x, y))
        # quick skip for rows with no content
        if not row_has_content:
            continue

    # If non-white detection fails, fallback to alpha-only content.
    if not content:
        for y in range(h):
            for x in range(w):
                if px[x, y][3] > 10:
                    content.append((x, y))

    if not content:
        return rgba

    xs = [p[0] for p in content]
    ys = [p[1] for p in content]
    left = max(0, min(xs))
    right = min(w, max(xs) + 1)
    top = max(0, min(ys))
    bottom = min(h, max(ys) + 1)
    if right - left <= 1 or bottom - top <= 1:
        return rgba
    return rgba.crop((left, top, right, bottom))


def _download_source_to_cache(drive, source, cache_path, folder_id=None):
    if not source:
        return False
    source = str(source).strip()
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    if os.path.exists(cache_path):
        return True

    downloaded = False
    if source.startswith("http"):
        downloaded = drive.download_by_link(source, cache_path)
        if not downloaded:
            fid = _extract_file_id(source)
            if fid:
                try:
                    url = f"https://drive.google.com/uc?export=download&id={fid}"
                    response = requests.get(url, timeout=30)
                    if response.status_code == 200 and response.content:
                        with open(cache_path, "wb") as out:
                            out.write(response.content)
                        downloaded = True
                except Exception:
                    pass
    else:
        if folder_id:
            file_id = drive.find_file_case_insensitive(source, folder_id)
            if not file_id:
                for ext in [".png", ".jpg", ".jpeg", ".webp"]:
                    file_id = drive.find_file_case_insensitive(source + ext, folder_id)
                    if file_id:
                        break
            if file_id:
                downloaded = drive.download_file(file_id, cache_path)
    return downloaded and os.path.exists(cache_path)


def _fetch_photo(drive, source, cache_key, width, height):
    if not source:
        return None
    cache_path = os.path.join(TEMP_FOLDER, f"{cache_key}.img")
    ok = _download_source_to_cache(drive, source, cache_path, folder_id=drive.speaker_photos_folder_id)
    if not ok:
        return None
    try:
        image = Image.open(cache_path).convert("RGB")
        return _prepare_image_for_box(image, width, height)
    except Exception:
        return None


def _fetch_logo_images(drive, value, folder_id, cache_dir, prefix):
    logos = []
    for index, source in enumerate(_split_sources(value), start=1):
        token = _extract_file_id(source) or _sanitize_filename(source)
        cache_path = os.path.join(cache_dir, f"{prefix}_{index}_{token}.img")
        ok = _download_source_to_cache(drive, source, cache_path, folder_id=folder_id)
        if not ok:
            logger.warning("Could not fetch logo source: %s", source)
            continue
        try:
            logo = Image.open(cache_path).convert("RGBA")
            logos.append(_trim_logo_margins(logo))
        except Exception:
            logger.warning("Could not open logo source: %s", source)
    return logos


def _fetch_single_logo(drive, value, folder_id, cache_dir, prefix):
    sources = _split_sources(value)
    if not sources:
        return None
    logos = _fetch_logo_images(drive, sources[0], folder_id, cache_dir, prefix)
    return logos[0] if logos else None


def _draw_logo_in_box(canvas, logo, box_cfg):
    if not logo or not box_cfg:
        return
    x = mm_to_px(box_cfg["x"])
    y = mm_to_px(box_cfg["y"])
    w = mm_to_px(box_cfg["w"])
    h = mm_to_px(box_cfg["h"])
    if box_cfg.get("draw_box"):
        corner_r = mm_to_px(box_cfg.get("corner_r", 2))
        drawer = ImageDraw.Draw(canvas)
        drawer.rounded_rectangle(
            [(x, y), (x + w, y + h)],
            radius=max(1, corner_r),
            fill=(255, 255, 255),
        )
    pad = mm_to_px(box_cfg.get("padding", 0))
    inner_w = max(1, w - 2 * pad)
    inner_h = max(1, h - 2 * pad)
    scale = min(inner_w / max(1, logo.width), inner_h / max(1, logo.height))
    draw_w = max(1, int(logo.width * scale))
    draw_h = max(1, int(logo.height * scale))
    resized = logo.resize((draw_w, draw_h), Image.LANCZOS)
    px = x + pad + (inner_w - draw_w) // 2
    py = y + pad + (inner_h - draw_h) // 2
    canvas.paste(resized, (px, py), resized)


def _draw_community_logos(canvas, logos, cfg):
    if not logos or not cfg:
        return None
    start_x = mm_to_px(cfg["x"])
    start_y = mm_to_px(cfg["y"])
    max_w_px = mm_to_px(cfg.get("max_w", cfg.get("w", 84)))
    min_w_px = mm_to_px(cfg.get("min_w", 0))
    box_h_px = mm_to_px(cfg.get("box_h", 23))
    pad_px = mm_to_px(cfg.get("padding", 2))
    corner_r = mm_to_px(cfg.get("corner_r", 2))
    gap_px = mm_to_px(cfg.get("spacing", 1))
    rect_w = mm_to_px(cfg["rect"]["w"])
    rect_h = mm_to_px(cfg["rect"]["h"])
    sq_w = mm_to_px(cfg["square"]["w"])
    sq_h = mm_to_px(cfg["square"]["h"])

    slots = []
    total_w = 0
    max_slot_h = 0
    for logo in logos:
        aspect = logo.width / max(1, logo.height)
        if aspect >= 1.2:
            box_w, box_h = rect_w, rect_h
        else:
            box_w, box_h = sq_w, sq_h
        slots.append((logo, box_w, box_h))
        total_w += box_w
        max_slot_h = max(max_slot_h, box_h)

    total_w += gap_px * max(0, len(slots) - 1)
    dynamic_width = bool(cfg.get("dynamic_width", False))
    if dynamic_width:
        content_plus_padding = total_w + 2 * pad_px
        box_w_px = max(min_w_px, min(max_w_px, content_plus_padding))
    else:
        box_w_px = max_w_px

    # Draw white background box (new background has no white panel).
    if cfg.get("draw_box", True):
        drawer = ImageDraw.Draw(canvas)
        drawer.rounded_rectangle(
            [(start_x, start_y), (start_x + box_w_px, start_y + box_h_px)],
            radius=max(1, corner_r),
            fill=(255, 255, 255),
        )

    inner_x = start_x + pad_px
    inner_y = start_y + pad_px
    inner_w = max(1, box_w_px - 2 * pad_px)
    inner_h = max(1, box_h_px - 2 * pad_px)

    shrink = min(1.0, inner_w / total_w) if total_w > 0 else 1.0
    if max_slot_h > 0:
        shrink = min(shrink, inner_h / max_slot_h)

    draw_widths = [max(1, int(box_w * shrink)) for _, box_w, _ in slots]
    content_w = sum(draw_widths) + gap_px * max(0, len(draw_widths) - 1)
    x = inner_x + max(0, (inner_w - content_w) // 2)

    for (logo, box_w, box_h), draw_box_w in zip(slots, draw_widths):
        draw_box_h = max(1, int(box_h * shrink))
        scale = min(draw_box_w / max(1, logo.width), draw_box_h / max(1, logo.height))
        draw_w = max(1, int(logo.width * scale))
        draw_h = max(1, int(logo.height * scale))
        resized = logo.resize((draw_w, draw_h), Image.LANCZOS)
        px = x + (draw_box_w - draw_w) // 2
        py = inner_y + max(0, (inner_h - draw_h) // 2)
        canvas.paste(resized, (px, py), resized)
        x += draw_box_w + gap_px

    return {
        "x": start_x / MM_TO_PX,
        "y": start_y / MM_TO_PX,
        "w": box_w_px / MM_TO_PX,
        "h": box_h_px / MM_TO_PX,
    }


def _safe_row(row, column_name):
    if column_name not in row.index:
        return None
    return _txt(row.get(column_name))


def _normalize_mode(value):
    text = _txt(value)
    if not text:
        return None
    lower = text.lower()
    if lower == "online":
        return "online"
    if lower == "offline":
        return "offline"
    return None


def _parse_speaker_count(raw_value, row=None):
    parsed = None
    try:
        parsed = int(float(raw_value))
    except Exception:
        parsed = None

    if parsed in (1, 2, 3):
        return parsed

    if row is None:
        return None

    names = [
        _safe_row(row, COL_S1_NAME),
        _safe_row(row, COL_S2_NAME),
        _safe_row(row, COL_S3_NAME),
    ]
    return sum(1 for item in names if item)


def _speaker_payload(row, speaker_count):
    payload = []
    speaker_columns = [
        (COL_S1_NAME, COL_S1_ROLE, COL_S1_COMPANY, COL_S1_PHOTO, COL_S1_ADD_INFO),
        (COL_S2_NAME, COL_S2_ROLE, COL_S2_COMPANY, COL_S2_PHOTO, COL_S2_ADD_INFO),
        (COL_S3_NAME, COL_S3_ROLE, COL_S3_COMPANY, COL_S3_PHOTO, COL_S3_ADD_INFO),
    ]
    for idx in range(min(3, speaker_count)):
        name_col, role_col, company_col, photo_col, add_col = speaker_columns[idx]
        payload.append(
            {
                "name": _safe_row(row, name_col),
                "role": _safe_row(row, role_col),
                "company": _safe_row(row, company_col),
                "photo": _safe_row(row, photo_col),
                "add_info": _safe_row(row, add_col),
            }
        )
    return payload


def _date_values(row):
    date_key = "undated"
    date_label = _safe_row(row, COL_DATE) or ""
    raw_value = row.get(COL_DATE) if COL_DATE in row.index else None
    try:
        parsed = pd.to_datetime(raw_value)
        date_key = parsed.strftime("%Y-%m-%d")
        date_label = parsed.strftime("%d %b %Y")
    except Exception:
        if date_label:
            date_key = _sanitize_filename(date_label)
    return date_key, date_label


def _build_role_line(speaker):
    parts = [speaker.get("role"), speaker.get("company")]
    line = ", ".join(part for part in parts if part)
    extra = speaker.get("add_info")
    if extra:
        line = f"{line} | {extra}" if line else extra
    return line


def _build_role_company_line(speaker):
    parts = [speaker.get("role"), speaker.get("company")]
    return ", ".join(part for part in parts if part)


def _resolve_local_output_dir(speaker_count, mode):
    candidates = LOCAL_OUTPUT_ROOT_CANDIDATES.get(speaker_count, [os.path.join(OUTPUT_LOCAL_FOLDER, f"{speaker_count} Speaker")])
    root = None
    for candidate in candidates:
        if os.path.isdir(candidate):
            root = candidate
            break
    if root is None:
        root = candidates[0]
    mode_dir = os.path.join(root, MODE_FOLDER_BY_KEY[mode])
    os.makedirs(mode_dir, exist_ok=True)
    return mode_dir


def _resolve_template_background(drive, template_folder_id, speaker_count, mode):
    if not template_folder_id:
        return None
    mode_folder_id = drive.find_folder(MODE_FOLDER_BY_KEY[mode], template_folder_id)
    general_folder_id = drive.find_folder("General", mode_folder_id) if mode_folder_id else None
    search_folder_ids = [folder_id for folder_id in [general_folder_id, mode_folder_id, template_folder_id] if folder_id]
    names = ONLINE_BACKGROUND_FILENAMES if mode == "online" else OFFLINE_BACKGROUND_FILENAMES
    for search_folder_id in search_folder_ids:
        for filename in names:
            file_id = drive.find_file_case_insensitive(filename, search_folder_id)
            if file_id:
                ext = os.path.splitext(filename)[1] or ".png"
                local_path = os.path.join(TEMP_FOLDER, f"bg_{mode}_{speaker_count}{ext}")
                if drive.download_file(file_id, local_path):
                    return local_path

    if mode == "offline" and speaker_count == 1:
        logger.warning("One-speaker offline background missing. Falling back to online/sample background.")
        for search_folder_id in search_folder_ids:
            for filename in OFFLINE_ONE_FALLBACK_FILENAMES:
                file_id = drive.find_file_case_insensitive(filename, search_folder_id)
                if file_id:
                    ext = os.path.splitext(filename)[1] or ".png"
                    local_path = os.path.join(TEMP_FOLDER, f"bg_offline_{speaker_count}_fallback{ext}")
                    if drive.download_file(file_id, local_path):
                        return local_path
    return None


def _ensure_generated_folder_map(drive, generated_root_id):
    folder_map = {}
    if not generated_root_id:
        return folder_map

    for speaker_count, speaker_folder in GENERATED_SUBFOLDER_BY_SPEAKER.items():
        speaker_id = drive.find_folder(speaker_folder, generated_root_id) or drive.create_folder(speaker_folder, generated_root_id)
        if not speaker_id:
            continue
        for mode_key, mode_folder in MODE_FOLDER_BY_KEY.items():
            mode_id = drive.find_folder(mode_folder, speaker_id) or drive.create_folder(mode_folder, speaker_id)
            general_id = drive.find_folder("General", mode_id) or drive.create_folder("General", mode_id) if mode_id else None
            if general_id:
                folder_map[(speaker_count, mode_key)] = general_id
    return folder_map


def _ensure_font_path(drive):
    local_font = os.path.join(TEMP_FOLDER, FONT_FILENAME)
    if os.path.exists(local_font):
        return local_font
    if not drive.base_folder_id:
        return local_font
    font_id = drive.find_file_case_insensitive(FONT_FILENAME, drive.base_folder_id)
    if font_id:
        drive.download_file(font_id, local_font)
    return local_font


def generate_event_poster(
    row,
    drive,
    background_path,
    font_path,
    speaker_count,
    mode,
    layout_override=None,
    target_size=None,
    out_path_override=None,
):
    layout = layout_override if layout_override is not None else (
        ONLINE_LAYOUTS[speaker_count] if mode == "online" else OFFLINE_LAYOUTS[speaker_count]
    )
    date_key, date_label = _date_values(row)
    day_label = _safe_row(row, COL_DAY)
    time_label = _safe_row(row, COL_TIME)
    title = _safe_row(row, COL_TITLE)
    title1 = _safe_row(row, COL_TITLE1)
    meetup_link = _safe_row(row, COL_MEETUP_LINK)
    community_value = _safe_row(row, COL_COMM_PART)
    mode_value = _safe_row(row, COL_MODE) or mode.title()
    venue_addr = _safe_row(row, COL_VENUE_ADDR)
    venue_name = _safe_row(row, COL_VENUE_SPONSOR_NAME)
    venue_logo_source = _safe_row(row, COL_VENUE_SPONSOR_IMAGE)
    gift_logo_source = _safe_row(row, COL_GIFT_SPONSOR)

    try:
        bg = Image.open(background_path).convert("RGB")
        target_w, target_h = target_size if target_size else (BASE_W, BASE_H)
        if bg.size != (target_w, target_h):
            bg = bg.resize((target_w, target_h), Image.LANCZOS)
        canvas = bg.copy()
    except Exception as exc:
        logger.error("Cannot open background %s: %s", background_path, exc)
        return None

    draw = ImageDraw.Draw(canvas)
    speakers = _speaker_payload(row, speaker_count)

    qr_cfg = layout.get("qr")
    if meetup_link and qr_cfg:
        qr_size_px = mm_to_px(qr_cfg.get("w", 39))
        qr_img = _generate_qr(meetup_link, qr_size_px)
        if qr_img:
            canvas.paste(qr_img.convert("RGBA"), (mm_to_px(qr_cfg["x"]), mm_to_px(qr_cfg["y"])))

    draw_static_labels = layout.get("draw_static_labels", True)
    if draw_static_labels:
        scan_cfg = layout.get("scan_to_register")
        if scan_cfg:
            scan_cfg = dict(scan_cfg)
            if qr_cfg:
                scan_cfg["x"] = qr_cfg["x"]
                scan_cfg["w"] = qr_cfg["w"]
                scan_cfg["align"] = "center"
        _draw_text_box(draw, "Scan To Register", font_path, scan_cfg)
    _draw_title_block(draw, title, font_path, layout.get("title", {}))
    _draw_text_box(draw, title1, font_path, layout.get("title1"))
    if draw_static_labels:
        _draw_text_box(draw, "This will be a series of Meetup", font_path, layout.get("series_text"))

    if day_label and date_label:
        _draw_text_box(draw, f"{day_label} {date_label}", font_path, layout.get("day_date"))
    elif date_label:
        _draw_text_box(draw, date_label, font_path, layout.get("day_date"))

    if time_label:
        time_cfg = layout.get("time")
        if time_cfg and time_cfg.get("sync_y_with"):
            ref_cfg = layout.get(time_cfg["sync_y_with"])
            if ref_cfg and "y" in ref_cfg:
                time_cfg = dict(time_cfg)
                time_cfg["y"] = ref_cfg["y"] + float(time_cfg.get("sync_y_offset", 0))
        _draw_text_box(draw, time_label, font_path, time_cfg)

    draw_mode = layout.get("draw_mode", mode == "online")
    if draw_mode and layout.get("mode"):
        mode_text = mode_value.strip() if mode_value else mode.title()
        if mode == "online" and not mode_text.lower().endswith("event"):
            mode_text = f"{mode_text} Event"
        _draw_text_box(draw, mode_text, font_path, layout.get("mode"))

    for idx, slot in enumerate(layout.get("speakers", [])):
        if idx >= len(speakers):
            break
        speaker = speakers[idx]
        photo_cfg = slot.get("photo")
        name_cfg = slot.get("name")
        role_cfg = slot.get("role")
        block_cfg = slot.get("block")

        if speaker.get("photo") and photo_cfg:
            photo_w = mm_to_px(photo_cfg["w"])
            photo_h = mm_to_px(photo_cfg["h"])
            cache_key = f"speaker_{speaker_count}_{mode}_{date_key}_{idx + 1}"
            photo = _fetch_photo(drive, speaker["photo"], cache_key, photo_w, photo_h)
            if photo:
                radius = int(photo_cfg.get("radius", 6))
                rounded = _add_rounded_corners(photo, radius)
                canvas.paste(rounded, (mm_to_px(photo_cfg["x"]), mm_to_px(photo_cfg["y"])), rounded)

        role_company_line = _build_role_company_line(speaker)
        add_info_line = speaker.get("add_info")

        if block_cfg:
            has_add = bool(add_info_line)
            variant = block_cfg.get("with_add") if has_add else block_cfg.get("without_add")
            if variant:
                variant = dict(variant)
                should_center = bool(block_cfg.get("center_to_photo"))
                if (not has_add) and bool(block_cfg.get("center_to_photo_without_add")):
                    should_center = True
                if should_center and photo_cfg:
                    variant["y"] = float(photo_cfg["y"]) + (float(photo_cfg["h"]) - float(variant.get("h", 0))) / 2.0
                lines = [speaker.get("name"), role_company_line]
                sizes = [variant.get("name_size", 14), variant.get("role_size", 13)]
                if has_add:
                    lines.append(add_info_line)
                    sizes.append(variant.get("add_size", 10))
                text_box_cfg = {
                    "x": variant["x"],
                    "y": variant["y"],
                    "w": variant["w"],
                    "h": variant["h"],
                    "align": block_cfg.get("align", "left"),
                    "valign": block_cfg.get("valign", "top"),
                    "color": variant.get("color", "#ffffff"),
                    "stroke_width": int(variant.get("stroke_width", 0)),
                }
                if "line_gap_px" in variant:
                    text_box_cfg["line_gap_px"] = int(variant.get("line_gap_px", 0))
                if "line_gap_mm" in variant:
                    text_box_cfg["line_gap_mm"] = float(variant.get("line_gap_mm", 0))
                _draw_text_lines_box(draw, lines, sizes, font_path, text_box_cfg)
        else:
            if speaker.get("name"):
                _draw_text_box(draw, speaker["name"], font_path, name_cfg)
            if role_company_line or add_info_line:
                combined = role_company_line
                if add_info_line:
                    combined = f"{combined} | {add_info_line}" if combined else add_info_line
                _draw_text_box(draw, combined, font_path, role_cfg)

    if draw_static_labels:
        free_text_label = layout.get("free_text_text", "THIS EVENT IS FREE AND OPEN FOR ALL GENDERS")
        _draw_text_box(draw, free_text_label, font_path, layout.get("free_text"))

    if layout.get("venue_logo_box") and venue_logo_source:
        venue_logo = _fetch_single_logo(
            drive=drive,
            value=venue_logo_source,
            folder_id=drive.venue_sponsors_folder_id,
            cache_dir=VENUE_LOGOS_CACHE,
            prefix=f"venue_{date_key}",
        )
        if venue_logo:
            _draw_logo_in_box(canvas, venue_logo, layout["venue_logo_box"])

    venue_block = layout.get("venue_text_block")
    if venue_block and (venue_name or venue_addr):
        _draw_venue_text_block(draw, venue_name, venue_addr, font_path, venue_block)
    else:
        if venue_name and layout.get("venue_name"):
            _draw_text_box(draw, venue_name, font_path, layout.get("venue_name"))
        if venue_addr and layout.get("venue_address"):
            _draw_text_box(draw, venue_addr, font_path, layout.get("venue_address"))

    gift_box_metrics = None
    if layout.get("gift") and gift_logo_source:
        gift_logos = _fetch_logo_images(
            drive=drive,
            value=gift_logo_source,
            folder_id=drive.gift_sponsors_folder_id,
            cache_dir=GIFT_LOGOS_CACHE,
            prefix=f"gift_{date_key}",
        )
        if gift_logos:
            gift_box_metrics = _draw_community_logos(canvas, gift_logos, layout["gift"])
    elif layout.get("gift_logo_box") and gift_logo_source:
        gift_logo = _fetch_single_logo(
            drive=drive,
            value=gift_logo_source,
            folder_id=drive.gift_sponsors_folder_id,
            cache_dir=GIFT_LOGOS_CACHE,
            prefix=f"gift_{date_key}",
        )
        if gift_logo:
            _draw_logo_in_box(canvas, gift_logo, layout["gift_logo_box"])
            gift_box_metrics = {
                "x": layout["gift_logo_box"]["x"],
                "y": layout["gift_logo_box"]["y"],
                "w": layout["gift_logo_box"]["w"],
                "h": layout["gift_logo_box"]["h"],
            }

    community_cfg = layout.get("community")
    community_box_metrics = None
    if community_cfg:
        community_cfg = dict(community_cfg)
        if layout.get("community_follow_gift") and gift_box_metrics:
            gap_mm = float(layout.get("sponsor_gap_mm", 2))
            community_cfg["x"] = gift_box_metrics["x"] + gift_box_metrics["w"] + gap_mm

    community_logos = _fetch_logo_images(
        drive=drive,
        value=community_value,
        folder_id=drive.community_logos_folder_id,
        cache_dir=COMM_LOGOS_CACHE,
        prefix=f"community_{date_key}_{speaker_count}_{mode}",
    )
    if community_logos:
        community_box_metrics = _draw_community_logos(canvas, community_logos, community_cfg)
        logger.info("Placed %s community logo(s)", len(community_logos))

    if draw_static_labels and layout.get("gift_heading"):
        gift_heading_cfg = dict(layout["gift_heading"])
        if gift_box_metrics:
            gift_heading_cfg["x"] = gift_box_metrics["x"]
            gift_heading_cfg["w"] = gift_box_metrics["w"]
            gift_heading_cfg["align"] = "center"
        _draw_text_box(draw, layout.get("gift_heading_text", "GIFT SPONSOR"), font_path, gift_heading_cfg)

    if draw_static_labels and layout.get("community_heading"):
        community_heading_cfg = dict(layout["community_heading"])
        if community_box_metrics:
            community_heading_cfg["x"] = community_box_metrics["x"]
            community_heading_cfg["w"] = community_box_metrics["w"]
            community_heading_cfg["align"] = "center"
        _draw_text_box(draw, layout.get("community_heading_text", "COMMUNITY PARTNERS"), font_path, community_heading_cfg)

    # Mild variant-specific sharpening to improve small text legibility.
    sharpen_by_variant = {
        ("online", 1): (1.0, 140, 1),
        ("online", 2): (1.1, 160, 2),
        ("online", 3): (1.2, 220, 1),
        ("offline", 1): (1.0, 140, 1),
        ("offline", 2): (1.0, 145, 1),
        ("offline", 3): (1.0, 150, 1),
    }
    params = sharpen_by_variant.get((mode, speaker_count))
    if params:
        radius, percent, threshold = params
        canvas = canvas.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=threshold))

    if out_path_override:
        out_path = out_path_override
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
    else:
        local_mode_dir = _resolve_local_output_dir(speaker_count, mode)
        safe_title = _sanitize_filename(title or "Event")
        out_name = f"{date_key}_{safe_title[:60]}_{mode}_{speaker_count}.png"
        out_path = os.path.join(local_mode_dir, out_name)
    canvas.convert("RGB").save(out_path, "PNG")
    logger.info("Poster saved: %s", out_path)
    return out_path


def generate_poster(row, drive, background_path, font_path, platform="online_one"):
    tag = str(platform).lower()
    mode = "online" if "online" in tag else "offline"
    speaker_count = 1
    if "3" in tag or "three" in tag:
        speaker_count = 3
    elif "2" in tag or "two" in tag:
        speaker_count = 2
    return generate_event_poster(row, drive, background_path, font_path, speaker_count=speaker_count, mode=mode)


def generate_online_poster(row, drive, background_path, font_path, platform="online_one"):
    return generate_poster(row, drive, background_path, font_path, platform=platform or "online_one")


def generate_offline_poster(row, drive, background_path, font_path, platform="offline_one"):
    return generate_poster(row, drive, background_path, font_path, platform=platform or "offline_one")


def check_and_generate(drive):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("[%s] Checking for upcoming events...", timestamp)

    if not drive.base_folder_id:
        logger.warning("Base folder unavailable. Skipping check.")
        return

    excel_id = drive.find_file_case_insensitive(EXCEL_FILENAME, drive.base_folder_id)
    if not excel_id:
        logger.error("'%s' not found in Drive base folder.", EXCEL_FILENAME)
        return

    local_excel = os.path.join(TEMP_FOLDER, EXCEL_FILENAME)
    if not drive.download_file(excel_id, local_excel):
        logger.error("Excel download failed.")
        return
    logger.info("Excel downloaded")

    try:
        df = pd.read_excel(local_excel)
        df = _normalize_columns(df)
    except Exception as exc:
        logger.error("Cannot read Excel: %s", exc)
        return

    required_columns = [COL_STATUS, COL_NUM_SPEAKERS, COL_MODE]
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        logger.error("Missing required columns: %s", ", ".join(missing))
        return

    upcoming = df[df[COL_STATUS].astype(str).str.strip().str.lower() == "upcoming"]
    if upcoming.empty:
        logger.info("No upcoming rows found.")
        return

    # Required order: Status (already filtered) -> No. of Speakers -> Mode
    tasks = []
    speaker_filtered = upcoming[
        pd.to_numeric(upcoming[COL_NUM_SPEAKERS], errors="coerce").isin([1, 2, 3])
    ]
    for idx, row in speaker_filtered.iterrows():
        speaker_count = _parse_speaker_count(row.get(COL_NUM_SPEAKERS), row)
        if speaker_count not in (1, 2, 3):
            continue
        mode = _normalize_mode(row.get(COL_MODE))
        if mode not in ("online", "offline"):
            continue
        if FOCUS_SPEAKER_MODE:
            focus_speaker, focus_mode = FOCUS_SPEAKER_MODE
            if not (speaker_count == int(focus_speaker) and mode == str(focus_mode).lower()):
                continue
        tasks.append((idx, row, speaker_count, mode))

    if not tasks:
        logger.info("No matching rows for mode online/offline and speakers 1/2/3.")
        return

    templates_root_id = drive.find_folder(GDRIVE_TEMPLATES_FOLDER, drive.base_folder_id)
    generated_root_id = drive.find_folder(GDRIVE_GENERATED_FOLDER, drive.base_folder_id)
    if not templates_root_id or not generated_root_id:
        logger.error("Templates or Generated Posters folder not found in Drive.")
        return

    font_path = _ensure_font_path(drive)
    generated_folder_map = _ensure_generated_folder_map(drive, generated_root_id)

    template_folder_map = {}
    for speaker_count, folder_name in TEMPLATE_SUBFOLDER_BY_SPEAKER.items():
        folder_id = drive.find_folder(folder_name, templates_root_id)
        if folder_id:
            template_folder_map[speaker_count] = folder_id
        else:
            logger.warning("Template folder missing: %s", folder_name)

    needed_pairs = sorted({(speaker_count, mode) for _, _, speaker_count, mode in tasks})
    background_map = {}
    for speaker_count, mode in needed_pairs:
        template_folder_id = template_folder_map.get(speaker_count)
        if not template_folder_id:
            continue
        bg_path = _resolve_template_background(drive, template_folder_id, speaker_count, mode)
        if bg_path:
            background_map[(speaker_count, mode)] = bg_path
        else:
            logger.warning("Background missing for %s speaker(s), mode=%s.", speaker_count, mode)

    logger.info("Processing %s matching upcoming row(s)...", len(tasks))

    for _, row, speaker_count, mode in tasks:
        title = _safe_row(row, COL_TITLE) or "Untitled"
        date_key, _ = _date_values(row)
        dedupe_key = f"{date_key}|{title}|{speaker_count}|{mode}"
        if dedupe_key in generated_posters:
            continue

        bg_path = background_map.get((speaker_count, mode))
        if not bg_path:
            logger.warning("%s skipped: no background available for %s-%s", title, speaker_count, mode)
            continue

        logger.info("Generating poster for %s [%s speaker(s), %s]", title, speaker_count, mode)
        poster_path = generate_event_poster(
            row=row,
            drive=drive,
            background_path=bg_path,
            font_path=font_path,
            speaker_count=speaker_count,
            mode=mode,
        )
        if not poster_path:
            continue

        upload_folder_id = generated_folder_map.get((speaker_count, mode))
        if upload_folder_id:
            drive.upload_image(poster_path, upload_folder_id)
        else:
            logger.warning("Upload folder missing for %s-%s. Saved locally only.", speaker_count, mode)

        generated_posters.add(dedupe_key)


def main():
    configure_logging()
    logger.info("=" * 70)
    logger.info("POSTER AGENT - Multi-variant Event Poster Generator")
    logger.info("=" * 70)
    logger.info("Drive base folder: %s/", GDRIVE_BASE_FOLDER)
    logger.info("Local output: %s/", OUTPUT_LOCAL_FOLDER)
    logger.info("Interval: every %s minute(s)", CHECK_INTERVAL // 60)
    logger.info("=" * 70)
    logger.info("Initializing...")
    try:
        drive = GoogleDriveManager()
    except Exception as exc:
        logger.exception("Initialization failed: %s", exc)
        traceback.print_exc()
        return

    if not drive.base_folder_id:
        logger.error("Could not resolve Drive base folder.")
        return

    logger.info("Monitoring for upcoming events. Press Ctrl+C to stop.")

    def safe_check():
        for attempt in range(1, 4):
            try:
                check_and_generate(drive)
                return
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                if attempt < 3:
                    logger.warning("Transient error (attempt %s/3): %s", attempt, exc)
                    time.sleep(30)
                else:
                    logger.exception("Failed after 3 attempts: %s", exc)
                    traceback.print_exc()

    safe_check()

    try:
        while True:
            nxt = datetime.fromtimestamp(time.time() + CHECK_INTERVAL).strftime("%H:%M:%S")
            logger.info("Next check at %s", nxt)
            time.sleep(CHECK_INTERVAL)
            safe_check()
    except KeyboardInterrupt:
        logger.info("%s", "=" * 70)
        logger.info("Stopped. Posters this session: %s", len(generated_posters))
        logger.info("%s", "=" * 70)


if __name__ == "__main__":
    main()
