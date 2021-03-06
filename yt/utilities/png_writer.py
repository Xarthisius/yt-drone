"""
Writing PNGs
"""

#-----------------------------------------------------------------------------
# Copyright (c) 2013, yt Development Team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
#-----------------------------------------------------------------------------

import matplotlib._png as _png
import cStringIO

def write_png(buffer, filename, dpi=100):
    width = buffer.shape[1]
    height = buffer.shape[0]
    _png.write_png(buffer, width, height, filename, dpi)

def write_png_to_string(buffer, dpi=100, gray=0):
    width = buffer.shape[1]
    height = buffer.shape[0]
    fileobj = cStringIO.StringIO()
    _png.write_png(buffer, width, height, fileobj, dpi)
    png_str = fileobj.getvalue()
    fileobj.close()
    return png_str

