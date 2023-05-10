#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import codecs
import os
import re
from argparse import ArgumentParser
from io import BytesIO
from xml.etree import ElementTree

from PIL import Image
from bplist.bplist import BPListReader
from fontTools.misc.xmlWriter import XMLWriter
from fontTools.ttLib import TTFont


def write_sbix_to_file(filename):
	basename = os.path.basename(filename)
	xml_filename = basename + ".xml"
	out_filename = os.path.join(os.getcwd(), xml_filename)

	if os.path.exists(out_filename):
		print(f"{out_filename} already exists. not extracting")
		return out_filename

	print(f"extracting sbix chunk to file {out_filename}")

	with open(out_filename, "wb") as fx:
		mx = XMLWriter(fx)
		mx.begintag("root")

		font = TTFont(filename, fontNumber=1)
		bix = font["sbix"]
		bix.toXML(xmlWriter=mx, ttFont=font)
		mx.endtag("root")
		mx.close()

	return out_filename


def get_parsed_strings():
	apple_name = "/System/Library/PrivateFrameworks/CoreEmoji.framework/Versions/A/Resources/en.lproj/AppleName.strings"
	with open(apple_name, "rb") as fp:
		reader = BPListReader(fp.read())
		parsed = reader.parse()

	new_parsed = parsed.copy()
	for key in parsed:
		graphical_key = key.replace("\uFE0F", "").replace("\u20E3", "").replace("\u200D", "")
		value = parsed[key]
		if type(value) is bytes:
			value = value.decode()

		new_parsed[graphical_key] = value

	return new_parsed


def extract_strikes_from_file(filename):
	sbix_table = ElementTree.parse(filename)
	strikes = sbix_table.findall("strike")
	return strikes


def escaped_string_from_string(string):
	hex_code = string.replace("u", "")
	number = int(hex_code, 16)
	return f"\\U{number:0>8X}"


def extract_pngs_from_sbix_xml_file(filename, sizes: list[int]):
	names = get_parsed_strings()

	strikes = extract_strikes_from_file(filename)

	created_dirs_for_sizes = []

	modifier_matcher = re.compile(r"\.(?P<skin_tone>[0-5]?)?\.?(?P<gender>[MWBG]{0,4})?")
	matcher = re.compile(r"([A-F0-9]{4,8})")

	for strike in strikes:
		for glyph in strike:
			gender = None
			skin_tone = None
			glyph_codes = glyph.attrib.get("name")

			png_hexdata = glyph.find("hexdata")
			if png_hexdata is None:
				continue

			filtered_text = re.sub(r"[\n\s]", "", png_hexdata.text)
			png_data = bytearray.fromhex(filtered_text)
			png_image = Image.open(BytesIO(png_data))
			width = png_image.size[0]
			height = png_image.size[1]
			if sizes and (width not in sizes and height not in sizes):
				continue

			modifiers = modifier_matcher.search(glyph_codes)
			codes = matcher.findall(glyph_codes)
			if codes is None:
				continue

			if modifiers is not None:
				mod_dict = modifiers.groupdict()
				gender = mod_dict["gender"]
				skin_tone = mod_dict["skin_tone"]

			key_string = ""
			for code in codes:
				if "fe0f" in code or "20E3" in code:
					continue

				key_string += escaped_string_from_string(code)

			decoded = codecs.decode(key_string, "unicode-escape")

			if gender == "W":
				decoded += "\u2640"
				gender = None
			elif gender == "M":
				decoded += "\u2642"
				gender = None

			try:
				name = names[decoded].replace("/", " ")
			except KeyError:

				name = glyph.attrib.get("name")
				print(f"""\
No name found for {decoded} ({key_string}). This is likely a modifier emoji, it will still be saved with the filename {name}.png
Try going to https://graphemica.com/{decoded} to find out more.\
				""")

			image_dir = os.path.join("./images", f"{png_image.size[0]}x{png_image.size[1]}")
			if image_dir not in created_dirs_for_sizes:
				created_dirs_for_sizes += image_dir
				if not os.path.exists(image_dir):
					os.makedirs(image_dir)
					created_dirs_for_sizes += image_dir

			image_filename = name

			if gender:
				image_filename += f" {gender.lower()}"
			if skin_tone:
				image_filename += f" {skin_tone}"

			image_filename += ".png"

			png_image.save(os.path.join(image_dir, image_filename))
			print(f"saved {image_dir}/{image_filename}")


if __name__ == "__main__":
	parser = ArgumentParser(description="Extract PNG elements from TTF")
	parser.add_argument("-f", "--ttc_file", help="ttc file")
	parser.add_argument("-s", "--sizes", action="append", type=int, choices=[20, 26, 32, 40, 48, 52, 64, 96, 160], help="Which emoji sizes to extract")

	args = parser.parse_args()
	ttc_file = args.ttc_file
	parsed = get_parsed_strings()

	if ttc_file is None:
		ttc_file = "/System/Library/Fonts/Apple Color Emoji.ttc"

	sbix = write_sbix_to_file(ttc_file)

	extract_pngs_from_sbix_xml_file(sbix, args.sizes)
