"""Build white PNG email icons from the installed Frappe SVG sprites (MIT).

Run with bench Python on a host with librsvg and gdk-pixbuf. Generated assets
have no runtime dependency on these libraries. SVG sprites are trusted source
assets; lxml recovery accommodates duplicate attributes in the Espresso sprite.
"""

import ctypes
import ctypes.util
import hashlib
import json
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from lxml import etree

frappe_root = Path(sys.argv[1]).resolve()
destination = Path(__file__).resolve().parents[1] / "dinext_common/public/images/workflow-icons"
destination.mkdir(parents=True, exist_ok=True)
(destination / "LICENSE").write_bytes((frappe_root / "LICENSE").read_bytes())
rsvg = ctypes.CDLL(ctypes.util.find_library("rsvg-2"))
pixbuf = ctypes.CDLL(ctypes.util.find_library("gdk_pixbuf-2.0"))
gobject = ctypes.CDLL(ctypes.util.find_library("gobject-2.0"))
rsvg.rsvg_handle_new_from_data.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_void_p]
rsvg.rsvg_handle_new_from_data.restype = ctypes.c_void_p
rsvg.rsvg_handle_get_pixbuf.argtypes = [ctypes.c_void_p]
rsvg.rsvg_handle_get_pixbuf.restype = ctypes.c_void_p
pixbuf.gdk_pixbuf_savev.argtypes = [
	ctypes.c_void_p,
	ctypes.c_char_p,
	ctypes.c_char_p,
	ctypes.c_void_p,
	ctypes.c_void_p,
	ctypes.c_void_p,
]
pixbuf.gdk_pixbuf_savev.restype = ctypes.c_int
gobject.g_object_unref.argtypes = [ctypes.c_void_p]
sources = {}
for family in ("timeless", "espresso"):
	path = frappe_root / "frappe/public/icons" / family / "icons.svg"
	sources[family] = hashlib.sha256(path.read_bytes()).hexdigest()
	document = etree.fromstring(path.read_bytes(), parser=etree.XMLParser(recover=True))
	for symbol in document.findall(".//{http://www.w3.org/2000/svg}symbol"):
		identifier = symbol.get("id", "")
		name = identifier.removeprefix("icon-")
		if not re.fullmatch(r"[a-z0-9-]+", name):
			continue
		svg = etree.Element(
			"svg",
			xmlns="http://www.w3.org/2000/svg",
			width="32",
			height="32",
			viewBox=symbol.get("viewBox", "0 0 24 24"),
			fill=symbol.get("fill", "none"),
		)
		for child in symbol:
			svg.append(deepcopy(child))
		# Rebuild attribute maps: recovery retains duplicate attribute nodes.
		for element in svg.iter():
			attributes = dict(element.attrib)
			element.attrib.clear()
			element.attrib.update(attributes)
		data = etree.tostring(svg).decode()
		data = re.sub(r"var\(--[^)]+\)", "#ffffff", data).replace("currentColor", "#ffffff").encode()
		handle = rsvg.rsvg_handle_new_from_data(data, len(data), None)
		if not handle:
			raise RuntimeError("Cannot render " + identifier)
		image = rsvg.rsvg_handle_get_pixbuf(handle)
		try:
			if not image or not pixbuf.gdk_pixbuf_savev(
				image, str(destination / (name + ".png")).encode(), b"png", None, None, None
			):
				raise RuntimeError("Cannot save " + identifier)
		finally:
			if image:
				gobject.g_object_unref(image)
			gobject.g_object_unref(handle)
sources["frappe_commit"] = subprocess.check_output(
	["git", "-C", str(frappe_root), "rev-parse", "HEAD"], text=True
).strip()
(destination / "provenance.json").write_text(json.dumps(sources, indent=2) + "\n")
print("Generated", len(list(destination.glob("*.png"))), "workflow email icons")
