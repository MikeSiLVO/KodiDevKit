"""
KodiDevKit is a plugin to assist with Kodi skinning / scripting
using Sublime Text 4
Expression validation for Kodi skins.

This module documents which XML tags support dynamic expressions ($VAR, $INFO, $LOCALIZE)
and which require literal values. It also validates that expressions are only used in
tags that support them.

Source: Analyzed from Kodi source code (GUIControlFactory.cpp)
Date: 2025-11-04
Kodi Version: v21 (Omega) / v22 (Piers) compatible

CRITICAL DISTINCTION:
- Tags parsed with GetInfoLabel/GetInfoTexture/GetInfoColor: Support expressions
- Tags parsed with XMLUtils::GetInt/GetFloat/GetString/GetTexture: Literal only
"""

import logging
import os
from .. import utils
from .constants import SEVERITY_ERROR

logger = logging.getLogger(__name__)


SUPPORTS_EXPRESSIONS = {
    'label': {
        'expressions': ['$VAR', '$INFO', '$LOCALIZE', '$PARAM'],
        'source_line': 1113,
        'parse_method': 'GetInfoLabels',
        'description': 'Primary label text for controls'
    },
    'altlabel': {
        'expressions': ['$VAR', '$INFO', '$LOCALIZE', '$PARAM'],
        'source_line': None,
        'parse_method': 'GetInfoLabels',
        'description': 'Alternate label for fadelabel'
    },
    'label2': {
        'expressions': ['$VAR', '$INFO', '$LOCALIZE', '$PARAM'],
        'source_line': 1117,
        'parse_method': 'GetString',
        'description': 'Secondary label text'
    },
    'hinttext': {
        'expressions': ['$VAR', '$INFO', '$LOCALIZE', '$PARAM'],
        'source_line': 1303,
        'parse_method': 'GetInfoLabel',
        'description': 'Hint text for edit controls'
    },
    'scrollsuffix': {
        'expressions': ['$VAR', '$INFO', '$LOCALIZE', '$PARAM'],
        'source_line': 1236,
        'parse_method': 'GetString',
        'description': 'Suffix for scrolling labels'
    },

    'texture': {
        'expressions': ['$VAR', '$INFO', '$LOCALIZE', '$PARAM'],
        'source_line': 1107,
        'parse_method': 'GetInfoTexture',
        'description': 'Main texture for image controls - ONLY this texture tag supports expressions!',
        'controls': ['image', 'largeimage']
    },
    'imagepath': {
        'expressions': ['$VAR', '$INFO', '$LOCALIZE', '$PARAM'],
        'source_line': 1142,
        'parse_method': 'GetInfoTexture',
        'description': 'Image path for slideshow/multiimage controls',
        'controls': ['multiimage']
    },

    'videofilter': {
        'expressions': ['$VAR', '$INFO', '$LOCALIZE', '$PARAM'],
        'source_line': 1323,
        'parse_method': 'GetInfoLabel',
        'description': 'Video filter effect'
    },
    'imagefilter': {
        'expressions': ['$VAR', '$INFO', '$LOCALIZE', '$PARAM'],
        'source_line': 1506,
        'parse_method': 'GetInfoLabel',
        'description': 'Image filter effect'
    },
    'diffusefilter': {
        'expressions': ['$VAR', '$INFO', '$LOCALIZE', '$PARAM'],
        'source_line': 1511,
        'parse_method': 'GetInfoLabel',
        'description': 'Diffuse filter for textures'
    },
    'stretchmode': {
        'expressions': ['$VAR', '$INFO', '$LOCALIZE', '$PARAM'],
        'source_line': 1327,
        'parse_method': 'GetInfoLabel',
        'description': 'Image stretch mode'
    },
    'rotation': {
        'expressions': ['$VAR', '$INFO', '$LOCALIZE', '$PARAM'],
        'source_line': 1331,
        'parse_method': 'GetInfoLabel',
        'description': 'Rotation angle'
    },
    'pixels': {
        'expressions': ['$VAR', '$INFO', '$LOCALIZE', '$PARAM'],
        'source_line': 1335,
        'parse_method': 'GetInfoLabel',
        'description': 'Pixel shader parameter'
    },

    'textcolor': {
        'expressions': ['$VAR', '$INFO', '$PARAM'],
        'source_line': 985,
        'parse_method': 'GetInfoColor',
        'description': 'Default text color'
    },
    'focusedcolor': {
        'expressions': ['$VAR', '$INFO', '$PARAM'],
        'source_line': 986,
        'parse_method': 'GetInfoColor',
        'description': 'Text color when focused'
    },
    'disabledcolor': {
        'expressions': ['$VAR', '$INFO', '$PARAM'],
        'source_line': 987,
        'parse_method': 'GetInfoColor',
        'description': 'Text color when disabled'
    },
    'shadowcolor': {
        'expressions': ['$VAR', '$INFO', '$PARAM'],
        'source_line': 988,
        'parse_method': 'GetInfoColor',
        'description': 'Text shadow color'
    },
    'selectedcolor': {
        'expressions': ['$VAR', '$INFO', '$PARAM'],
        'source_line': 989,
        'parse_method': 'GetInfoColor',
        'description': 'Text color when selected'
    },
    'invalidcolor': {
        'expressions': ['$VAR', '$INFO', '$PARAM'],
        'source_line': 990,
        'parse_method': 'GetInfoColor',
        'description': 'Text color for invalid input'
    },
    'colorbox': {
        'expressions': ['$VAR', '$INFO', '$PARAM'],
        'source_line': 977,
        'parse_method': 'GetInfoColor',
        'description': 'Color for colorbox'
    },

    'visible': {
        'expressions': ['$VAR', '$INFO', '$PARAM', 'Boolean'],
        'source_line': 979,
        'parse_method': 'GetConditionalVisibility',
        'description': 'Visibility condition'
    },
    'enable': {
        'expressions': ['$VAR', '$INFO', '$PARAM', 'Boolean'],
        'source_line': 980,
        'parse_method': 'XMLUtils::GetString',
        'description': 'Enable condition (treated as condition string)'
    },
    'usealttexture': {
        'expressions': ['$VAR', '$INFO', '$PARAM', 'Boolean'],
        'source_line': 1025,
        'parse_method': 'XMLUtils::GetString',
        'description': 'Boolean condition for alternate texture'
    },
    'selected': {
        'expressions': ['$VAR', '$INFO', '$PARAM', 'Boolean'],
        'source_line': 1026,
        'parse_method': 'XMLUtils::GetString',
        'description': 'Boolean condition for selected state'
    },

    'info': {
        'expressions': ['$INFO', '$PARAM'],
        'source_line': 1015,
        'parse_method': 'GetString -> TranslateString',
        'description': 'Info field for label fallback'
    },
    'info2': {
        'expressions': ['$INFO', '$PARAM'],
        'source_line': 1017,
        'parse_method': 'GetString -> TranslateString',
        'description': 'Secondary info field'
    },

    'controllerid': {
        'expressions': ['$VAR', '$INFO', '$LOCALIZE', '$PARAM'],
        'source_line': 1688,
        'parse_method': 'GetInfoLabel',
        'description': 'Game controller ID'
    },
    'controlleraddress': {
        'expressions': ['$VAR', '$INFO', '$LOCALIZE', '$PARAM'],
        'source_line': 1693,
        'parse_method': 'GetInfoLabel',
        'description': 'Game controller address'
    },
    'portaddress': {
        'expressions': ['$VAR', '$INFO', '$LOCALIZE', '$PARAM'],
        'source_line': 1703,
        'parse_method': 'GetInfoLabel',
        'description': 'Controller port address'
    },
    'peripherallocation': {
        'expressions': ['$VAR', '$INFO', '$LOCALIZE', '$PARAM'],
        'source_line': 1708,
        'parse_method': 'GetInfoLabel',
        'description': 'Peripheral device location'
    },
}


LITERAL_ONLY = {
    'id': {
        'type': 'int',
        'source_line': 926,
        'parse_method': 'XMLUtils::GetInt',
        'description': 'Control ID',
        'reason': 'Must be known at parse time for focus management'
    },
    'defaultcontrol': {
        'type': 'int',
        'source_line': 968,
        'parse_method': 'XMLUtils::GetInt',
        'description': 'Default control ID for focus',
        'reason': 'Control ID references must be static'
    },
    'pagecontrol': {
        'type': 'int',
        'source_line': 974,
        'parse_method': 'XMLUtils::GetInt',
        'description': 'Page control ID reference',
        'reason': 'Control ID references must be static'
    },

    'posx': {
        'type': 'float',
        'source_line': None,
        'parse_method': 'GetDimensions',
        'description': 'X position',
        'reason': 'Layout must be calculated at parse time'
    },
    'posy': {
        'type': 'float',
        'source_line': None,
        'parse_method': 'GetDimensions',
        'description': 'Y position',
        'reason': 'Layout must be calculated at parse time'
    },
    'width': {
        'type': 'float',
        'source_line': None,
        'parse_method': 'GetDimensions',
        'description': 'Control width',
        'reason': 'Layout must be calculated at parse time'
    },
    'height': {
        'type': 'float',
        'source_line': None,
        'parse_method': 'GetDimensions',
        'description': 'Control height',
        'reason': 'Layout must be calculated at parse time'
    },
    'offsetx': {
        'type': 'float',
        'source_line': 951,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'X offset',
        'reason': 'Offset must be known at layout time'
    },
    'offsety': {
        'type': 'float',
        'source_line': 952,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Y offset',
        'reason': 'Offset must be known at layout time'
    },
    'textoffsetx': {
        'type': 'float',
        'source_line': 991,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Text X offset',
        'reason': 'Text layout must be calculated at parse time'
    },
    'textoffsety': {
        'type': 'float',
        'source_line': 992,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Text Y offset',
        'reason': 'Text layout must be calculated at parse time'
    },
    'textwidth': {
        'type': 'float',
        'source_line': 1003,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Text width for truncation',
        'reason': 'Text layout must be calculated at parse time'
    },

    'scrolltime': {
        'type': 'int',
        'source_line': 1167,
        'parse_method': 'XMLUtils::GetInt',
        'description': 'Scroll animation time in milliseconds',
        'reason': 'Animation timing must be compile-time constant'
    },
    'scrollspeed': {
        'type': 'int',
        'source_line': 1234,
        'parse_method': 'XMLUtils::GetInt',
        'description': 'Scroll speed value',
        'reason': 'Animation timing must be compile-time constant'
    },
    'timeperimage': {
        'type': 'int',
        'source_line': None,
        'parse_method': 'XMLUtils::GetUInt',
        'description': 'Time per image in slideshow (milliseconds)',
        'reason': 'Timing must be compile-time constant'
    },

    'angle': {
        'type': 'int',
        'source_line': 994,
        'parse_method': 'XMLUtils::GetInt',
        'description': 'Text rotation angle in degrees',
        'reason': 'Rotation must be known at render setup time',
        'note': 'For text only - image rotation uses <rotation> which supports expressions!'
    },

    'spinwidth': {
        'type': 'float',
        'source_line': 1037,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Spinner width',
        'reason': 'Layout must be calculated at parse time'
    },
    'spinheight': {
        'type': 'float',
        'source_line': 1038,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Spinner height',
        'reason': 'Layout must be calculated at parse time'
    },
    'spinposx': {
        'type': 'float',
        'source_line': 1039,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Spinner X position',
        'reason': 'Layout must be calculated at parse time'
    },
    'spinposy': {
        'type': 'float',
        'source_line': 1040,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Spinner Y position',
        'reason': 'Layout must be calculated at parse time'
    },
    'sliderwidth': {
        'type': 'float',
        'source_line': 1042,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Slider width',
        'reason': 'Layout must be calculated at parse time'
    },
    'sliderheight': {
        'type': 'float',
        'source_line': 1043,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Slider height',
        'reason': 'Layout must be calculated at parse time'
    },
    'radiowidth': {
        'type': 'float',
        'source_line': 1151,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Radio button width',
        'reason': 'Layout must be calculated at parse time'
    },
    'radioheight': {
        'type': 'float',
        'source_line': 1152,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Radio button height',
        'reason': 'Layout must be calculated at parse time'
    },
    'radioposx': {
        'type': 'float',
        'source_line': 1153,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Radio button X position',
        'reason': 'Layout must be calculated at parse time'
    },
    'radioposy': {
        'type': 'float',
        'source_line': 1154,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Radio button Y position',
        'reason': 'Layout must be calculated at parse time'
    },
    'colorwidth': {
        'type': 'float',
        'source_line': 1156,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Color picker width',
        'reason': 'Layout must be calculated at parse time'
    },
    'colorheight': {
        'type': 'float',
        'source_line': 1157,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Color picker height',
        'reason': 'Layout must be calculated at parse time'
    },
    'colorposx': {
        'type': 'float',
        'source_line': 1158,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Color picker X position',
        'reason': 'Layout must be calculated at parse time'
    },
    'colorposy': {
        'type': 'float',
        'source_line': 1159,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Color picker Y position',
        'reason': 'Layout must be calculated at parse time'
    },

    'itemgap': {
        'type': 'float',
        'source_line': 1128,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Gap between items',
        'reason': 'Layout must be calculated at parse time'
    },
    'movement': {
        'type': 'int',
        'source_line': 1129,
        'parse_method': 'XMLUtils::GetInt',
        'description': 'Movement range for containers',
        'reason': 'Container behavior must be compile-time constant'
    },
    'focusposition': {
        'type': 'int',
        'source_line': 1166,
        'parse_method': 'XMLUtils::GetInt',
        'description': 'Focus position in list',
        'reason': 'List behavior must be compile-time constant'
    },
    'preloaditems': {
        'type': 'int',
        'source_line': 1168,
        'parse_method': 'XMLUtils::GetInt',
        'description': 'Number of items to preload (0-2)',
        'reason': 'Performance optimization must be compile-time'
    },

    'timeblocks': {
        'type': 'int',
        'source_line': 1137,
        'parse_method': 'XMLUtils::GetInt',
        'description': 'EPG time blocks',
        'reason': 'EPG layout must be compile-time constant'
    },
    'rulerunit': {
        'type': 'int',
        'source_line': 1139,
        'parse_method': 'XMLUtils::GetInt',
        'description': 'EPG ruler unit',
        'reason': 'EPG layout must be compile-time constant'
    },
    'minspertimeblock': {
        'type': 'int',
        'source_line': 1138,
        'parse_method': 'XMLUtils::GetUInt',
        'description': 'Minutes per EPG time block',
        'reason': 'EPG layout must be compile-time constant'
    },

    'font': {
        'type': 'string',
        'source_line': 997,
        'parse_method': 'XMLUtils::GetString',
        'description': 'Font name reference',
        'reason': 'Font must be looked up at parse time'
    },
    'monofont': {
        'type': 'string',
        'source_line': 999,
        'parse_method': 'XMLUtils::GetString',
        'description': 'Monospace font name',
        'reason': 'Font must be looked up at parse time'
    },

    'orientation': {
        'type': 'string',
        'source_line': 1122,
        'parse_method': 'XMLUtils::GetString',
        'description': 'Orientation: horizontal or vertical',
        'reason': 'Layout direction must be compile-time constant'
    },

    'type': {
        'type': 'string',
        'source_line': 742,
        'parse_method': 'XMLUtils::GetString',
        'description': 'Control type',
        'reason': 'Control class instantiation requires literal type'
    },
    'subtype': {
        'type': 'string',
        'source_line': 1078,
        'parse_method': 'XMLUtils::GetString',
        'description': 'RSS subtype',
        'reason': 'RSS feed type must be compile-time constant'
    },

    'haspath': {
        'type': 'bool',
        'source_line': 1028,
        'parse_method': 'XMLUtils::GetBoolean',
        'description': 'Whether label contains file path',
        'reason': 'Label parsing behavior must be compile-time'
    },
    'wrapmultiline': {
        'type': 'bool',
        'source_line': 1119,
        'parse_method': 'XMLUtils::GetBoolean',
        'description': 'Enable multiline text wrapping',
        'reason': 'Text layout must be compile-time constant'
    },
    'reverse': {
        'type': 'bool',
        'source_line': None,
        'parse_method': 'XMLUtils::GetBoolean',
        'description': 'Reverse progress bar direction',
        'reason': 'Layout direction must be compile-time constant'
    },
    'reveal': {
        'type': 'bool',
        'source_line': 1098,
        'parse_method': 'XMLUtils::GetBoolean',
        'description': 'Reveal animation for progress',
        'reason': 'Animation type must be compile-time constant'
    },
    'password': {
        'type': 'bool',
        'source_line': 1174,
        'parse_method': 'XMLUtils::GetBoolean',
        'description': 'Mask input as password',
        'reason': 'Input type must be compile-time constant'
    },
    'usecontrolcoords': {
        'type': 'bool',
        'source_line': 1170,
        'parse_method': 'XMLUtils::GetBoolean',
        'description': 'Use control coordinates for children',
        'reason': 'Layout calculation mode must be compile-time'
    },
    'renderfocusedlast': {
        'type': 'bool',
        'source_line': 1171,
        'parse_method': 'XMLUtils::GetBoolean',
        'description': 'Render focused control last',
        'reason': 'Render order must be compile-time constant'
    },
    'resetonlabelchange': {
        'type': 'bool',
        'source_line': 1172,
        'parse_method': 'XMLUtils::GetBoolean',
        'description': 'Reset scroll on label change',
        'reason': 'Scroll behavior must be compile-time constant'
    },

    'depth': {
        'type': 'float',
        'source_line': 1231,
        'parse_method': 'XMLUtils::GetFloat',
        'description': 'Stereo depth (-1.0 to 1.0)',
        'reason': '3D rendering must be calculated at parse time'
    },
    'bordersize': {
        'type': 'string',
        'source_line': 1162,
        'parse_method': 'XMLUtils::GetString',
        'description': 'Border size (parsed as rect)',
        'reason': 'Border must be calculated at parse time'
    },
    'urlset': {
        'type': 'int',
        'source_line': 1120,
        'parse_method': 'XMLUtils::GetInt',
        'description': 'RSS URL set ID',
        'reason': 'RSS feed lookup must be compile-time'
    },

    'action': {
        'type': 'string',
        'source_line': 1238,
        'parse_method': 'XMLUtils::GetString',
        'description': 'Action name to execute',
        'reason': 'Action must be mapped at parse time'
    },

    # ALL texture* tags (except 'texture' for image controls) use GetTexture() NOT GetInfoTexture()
    'texturefocus': {
        'type': 'string',
        'source_line': 1020,
        'parse_method': 'GetTexture',
        'description': 'Focused texture (literal path)',
        'reason': 'Button textures must be loaded at parse time'
    },
    'texturenofocus': {
        'type': 'string',
        'source_line': 1021,
        'parse_method': 'GetTexture',
        'description': 'Unfocused texture (literal path)',
        'reason': 'Button textures must be loaded at parse time'
    },
    'alttexturefocus': {
        'type': 'string',
        'source_line': 1022,
        'parse_method': 'GetTexture',
        'description': 'Alternate focused texture (literal path)',
        'reason': 'Button textures must be loaded at parse time'
    },
    'alttexturenofocus': {
        'type': 'string',
        'source_line': 1023,
        'parse_method': 'GetTexture',
        'description': 'Alternate unfocused texture (literal path)',
        'reason': 'Button textures must be loaded at parse time'
    },
    'textureup': {
        'type': 'string',
        'source_line': 1030,
        'parse_method': 'GetTexture',
        'description': 'Up button texture (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'texturedown': {
        'type': 'string',
        'source_line': 1031,
        'parse_method': 'GetTexture',
        'description': 'Down button texture (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'textureupfocus': {
        'type': 'string',
        'source_line': 1032,
        'parse_method': 'GetTexture',
        'description': 'Focused up button texture (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'texturedownfocus': {
        'type': 'string',
        'source_line': 1033,
        'parse_method': 'GetTexture',
        'description': 'Focused down button texture (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'textureupdisabled': {
        'type': 'string',
        'source_line': 1034,
        'parse_method': 'GetTexture',
        'description': 'Disabled up button texture (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'texturedowndisabled': {
        'type': 'string',
        'source_line': 1035,
        'parse_method': 'GetTexture',
        'description': 'Disabled down button texture (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'textureradioonfocus': {
        'type': 'string',
        'source_line': 1044,
        'parse_method': 'GetTexture',
        'description': 'Radio button ON focused (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'textureradioonnofocus': {
        'type': 'string',
        'source_line': 1045,
        'parse_method': 'GetTexture',
        'description': 'Radio button ON unfocused (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'textureradioofffocus': {
        'type': 'string',
        'source_line': 1051,
        'parse_method': 'GetTexture',
        'description': 'Radio button OFF focused (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'textureradiooffnofocus': {
        'type': 'string',
        'source_line': 1052,
        'parse_method': 'GetTexture',
        'description': 'Radio button OFF unfocused (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'textureradioondisabled': {
        'type': 'string',
        'source_line': 1058,
        'parse_method': 'GetTexture',
        'description': 'Radio button ON disabled (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'textureradiooffdisabled': {
        'type': 'string',
        'source_line': 1059,
        'parse_method': 'GetTexture',
        'description': 'Radio button OFF disabled (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'texturesliderbackground': {
        'type': 'string',
        'source_line': 1060,
        'parse_method': 'GetTexture',
        'description': 'Slider background (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'texturesliderbar': {
        'type': 'string',
        'source_line': 1061,
        'parse_method': 'GetTexture',
        'description': 'Slider bar (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'texturesliderbarfocus': {
        'type': 'string',
        'source_line': 1062,
        'parse_method': 'GetTexture',
        'description': 'Slider bar focused (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'texturesliderbardisabled': {
        'type': 'string',
        'source_line': 1063,
        'parse_method': 'GetTexture',
        'description': 'Slider bar disabled (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'textureslidernib': {
        'type': 'string',
        'source_line': 1065,
        'parse_method': 'GetTexture',
        'description': 'Slider nib/handle (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'textureslidernibfocus': {
        'type': 'string',
        'source_line': 1066,
        'parse_method': 'GetTexture',
        'description': 'Slider nib focused (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'textureslidernibdisabled': {
        'type': 'string',
        'source_line': 1067,
        'parse_method': 'GetTexture',
        'description': 'Slider nib disabled (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'texturecolormask': {
        'type': 'string',
        'source_line': 1070,
        'parse_method': 'GetTexture',
        'description': 'Color mask texture (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'texturecolordisabledmask': {
        'type': 'string',
        'source_line': 1071,
        'parse_method': 'GetTexture',
        'description': 'Disabled color mask (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'texturebg': {
        'type': 'string',
        'source_line': 1100,
        'parse_method': 'GetTexture',
        'description': 'Background texture (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'lefttexture': {
        'type': 'string',
        'source_line': 1101,
        'parse_method': 'GetTexture',
        'description': 'Left side texture (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'midtexture': {
        'type': 'string',
        'source_line': 1102,
        'parse_method': 'GetTexture',
        'description': 'Middle texture (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'righttexture': {
        'type': 'string',
        'source_line': 1103,
        'parse_method': 'GetTexture',
        'description': 'Right side texture (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'overlaytexture': {
        'type': 'string',
        'source_line': 1104,
        'parse_method': 'GetTexture',
        'description': 'Overlay texture (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'bordertexture': {
        'type': 'string',
        'source_line': 1109,
        'parse_method': 'GetTexture',
        'description': 'Border texture (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
    'progresstexture': {
        'type': 'string',
        'source_line': 1140,
        'parse_method': 'GetTexture',
        'description': 'Progress indicator texture (literal path)',
        'reason': 'Control textures must be loaded at parse time'
    },
}


def supports_expressions(tag_name):
    """
    Check if a tag supports dynamic expressions ($VAR, $INFO, etc.)

    Args:
        tag_name: XML tag name (e.g., 'label', 'texture', 'posx')

    Returns:
        bool: True if tag supports expressions, False if literal only
    """
    return tag_name in SUPPORTS_EXPRESSIONS


def get_tag_info(tag_name):
    """
    Get full information about a tag's expression support.

    Args:
        tag_name: XML tag name

    Returns:
        dict: Tag information including type, description, reason
        None: If tag not found in either dict
    """
    if tag_name in SUPPORTS_EXPRESSIONS:
        return {
            'supports_expressions': True,
            **SUPPORTS_EXPRESSIONS[tag_name]
        }
    elif tag_name in LITERAL_ONLY:
        return {
            'supports_expressions': False,
            **LITERAL_ONLY[tag_name]
        }
    return None


def validate_tag_expression(tag_name, value):
    """
    Validate if a tag value is appropriate (literal vs expression).

    Args:
        tag_name: XML tag name
        value: Tag content/value as string

    Returns:
        tuple: (is_valid: bool, message: str)

    Examples:
        >>> validate_tag_expression('label', '$VAR[MyLabel]')
        (True, 'Tag supports expressions')

        >>> validate_tag_expression('posx', '$VAR[XPos]')
        (False, 'Tag requires literal value, found expression: $VAR[XPos]')

        >>> validate_tag_expression('texture', '$INFO[ListItem.Art(thumb)]')
        (True, 'Tag supports expressions')

        >>> validate_tag_expression('texturefocus', '$VAR[ButtonTexture]')
        (False, 'Tag requires literal value, found expression: $VAR[ButtonTexture]')
    """
    has_expression = ('$VAR[' in value or '$INFO[' in value or
                     '$LOCALIZE[' in value or '$PARAM[' in value)

    if has_expression:
        if supports_expressions(tag_name):
            return (True, f'Tag <{tag_name}> supports expressions')
        else:
            tag_info = get_tag_info(tag_name)
            reason = tag_info.get('reason', 'Expression not supported') if tag_info else 'Unknown tag'
            return (False, f'Tag <{tag_name}> requires literal value, found expression. Reason: {reason}')
    else:
        return (True, 'Literal value is valid')


class ValidationExpression:
    """Validates that expressions are only used in tags that support them."""

    def __init__(self, addon, validation_index=None):
        """
        Args:
            addon: Addon/Skin instance with xml_folders, path
            validation_index: Pre-built validation index for performance (optional)
        """
        self.addon = addon
        self._validation_index = validation_index

    def check(self, progress_callback=None):
        """
        Validate that $VAR, $INFO, $LOCALIZE are only used in tags that support expressions.
        Returns list of {"message": str, "file": str, "line": int}.
        """
        if progress_callback:
            progress_callback("Validating expression usage in tags...")

        issues = []
        checked_files = 0

        for folder in self.addon.xml_folders:
            xml_files = self.addon.window_files.get(folder, [])

            for xml_file in xml_files:
                checked_files += 1
                file_path = os.path.join(self.addon.path, folder, xml_file)

                if progress_callback and checked_files % 5 == 0:
                    progress_callback(f"Checking expressions in {xml_file} ({checked_files}/{sum(len(self.addon.window_files.get(f, [])) for f in self.addon.xml_folders)})...")

                root = utils.get_root_from_file(file_path)
                if root is None:
                    continue

                issues.extend(self._check_xml_tree(root, file_path))

        error_count = len(issues)
        if progress_callback:
            progress_callback(f"Complete: {error_count} expression validation issues found")

        return issues

    def _check_xml_tree(self, root, file_path):
        """
        Check all elements in an XML tree for invalid expression usage.

        Args:
            root: XML root element
            file_path: Path to the file being checked

        Returns:
            List of issues found
        """
        issues = []

        for element in root.iter():
            tag_name = element.tag
            tag_value = element.text or ''

            has_expression = ('$VAR[' in tag_value or
                            '$INFO[' in tag_value or
                            '$LOCALIZE[' in tag_value)

            if has_expression:
                is_valid, message = validate_tag_expression(tag_name, tag_value)

                if not is_valid:
                    issues.append({
                        'file': file_path,
                        'line': getattr(element, 'sourceline', 0),
                        'message': f'Tag <{tag_name}> does not support expressions, found: {tag_value[:50]}{"..." if len(tag_value) > 50 else ""}',
                        'type': 'expression',
                        'identifier': tag_name,
                        'name': tag_name,
                        'severity': SEVERITY_ERROR,
                    })

        return issues


def check(addon, validation_index):
    """
    Module-level check function for expression validation.

    Args:
        addon: Skin instance
        validation_index: Validation index dict (not currently used but kept for API consistency)

    Returns:
        List of issues
    """
    checker = ValidationExpression(addon, validation_index)
    return checker.check()
