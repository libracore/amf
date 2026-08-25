#!/usr/bin/env python3
"""Improve descriptions for active physical items with submitted purchase history.

The update deliberately excludes accounting, freight, discount and service
placeholders.  It combines the Item master, submitted purchase documents,
supplier part numbers, supplier websites and a curated set of manufacturer or
supplier product pages.  Existing production notes are preserved verbatim in
the generated internal description.  Disabled BOM output items are excluded
from production-usage traversal, purchased Part items are assigned to stable
child groups, and every run emits a compact CSV for review/debugging.

Run from the bench directory::

    ./env/bin/python apps/amf/amf/amf/utils/purchased_item_description_update_2026.py
    ./env/bin/python apps/amf/amf/amf/utils/purchased_item_description_update_2026.py --apply
"""

from __future__ import unicode_literals

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime


BENCH_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
if BENCH_PATH not in sys.path:
	sys.path.insert(0, BENCH_PATH)


EXCLUDED_NON_PHYSICAL_ITEMS = {
	"Account Balance",
	"Discount",
	"GX.BN",
	"GX.GE-6400",
}

# Tangible equipment that was intentionally expensed/non-stocked in ERPNext.
INCLUDED_NON_STOCK_ITEMS = {
	"PRD.1004",
	"PRD.3003",
	"PRD.3004",
	"PRD.3005",
	"PRD.3006",
	"PRD.3010",
	"PRD.3011",
	"PRD.3012",
}

CLIENT_START = "<!-- AMF:PURCHASED:CLIENT START -->"
CLIENT_END = "<!-- AMF:PURCHASED:CLIENT END -->"
FACTS_START = "<!-- AMF:PURCHASED:FACTS START -->"
FACTS_END = "<!-- AMF:PURCHASED:FACTS END -->"
BASIS_START = "<!-- AMF:PURCHASED:BASIS START -->"
BASIS_END = "<!-- AMF:PURCHASED:BASIS END -->"
INTERNAL_START = "<!-- AMF:PURCHASED:INTERNAL START -->"
INTERNAL_END = "<!-- AMF:PURCHASED:INTERNAL END -->"
PRESERVED_START = "<!-- AMF:PURCHASED:PRESERVED START -->"
PRESERVED_END = "<!-- AMF:PURCHASED:PRESERVED END -->"


# Exact, manually verified catalog facts.  URLs point to the manufacturer or
# the supplier catalog used for the purchase whenever an exact page exists.
RESEARCHED_ITEMS = {
	"700001": {
		"facts": "3M 3365/08 flat gray ribbon cable with 8 conductors on 1.27 mm pitch, supplied as a 30.48 m (100 ft) length.",
		"source": "https://www.digikey.com/en/products/detail/3m/3365-08-100/1107678",
	},
	"RVM.3001": {
		"facts": "Bivar 9911-250 unthreaded nylon round spacer for a #4 screw; 3.18 mm inside diameter and 6.35 mm outside diameter/length.",
		"source": "https://www.digikey.co.uk/en/products/detail/bivar-inc/9911-250/586409",
	},
	"SPL.3058": {
		"facts": "Molex PicoBlade 51021-0400 natural 4-position receptacle housing with 1.25 mm contact pitch.",
		"source": "https://www.digikey.com/en/products/detail/molex/0510210400/242844",
	},
	"SPM.4008": {
		"facts": "Molex PicoBlade 51021-0400 natural 4-position receptacle housing with 1.25 mm contact pitch.",
		"source": "https://www.digikey.com/en/products/detail/molex/0510210400/242844",
	},
	"SPL.3059": {
		"facts": "Würth Elektronik 74271111S hinged snap-on ferrite core, 5 mm cable opening and 320 ohm impedance at 100 MHz.",
		"source": "https://www.digikey.com/en/products/detail/w%C3%BCrth-elektronik/74271111S/2901116",
	},
	"SPM.3021": {
		"facts": "Cantherm MF52C1103F3380 bead NTC thermistor, 10 kohm resistance, B3380K characteristic, ±1% tolerance and -55 to +125 °C operating range.",
		"source": "https://www.digikey.com/en/products/detail/cantherm/MF52C1103F3380/1840604",
	},
	"SPL.3077": {
		"facts": "JST PHR-6 natural 6-position receptacle housing for the PH series, with 2.00 mm contact pitch.",
		"source": "https://www.digikey.com/en/products/detail/jst-sales-america-inc/PHR-6/608604",
	},
	"SPL.3043": {
		"facts": "E-Switch PV6F240SS-341 illuminated anti-vandal pushbutton: 16 mm panel mounting, momentary SPST action, 2 A at 48 VDC, blue ring illumination and IP65 front protection.",
		"source": "https://www.e-switch.com/product/pv6-series-illuminated-anti-vandal-switch/",
	},
	"SPM.4001": {
		"facts": "Wakefield-Vette CD-02-05-126 orange thermal interface pad for TO-126 packages, measuring 12.7 × 8.89 × 0.076 mm.",
		"source": "https://www.digikey.com/en/products/detail/wakefield-thermal-solutions/CD-02-05-126/9369973",
	},
	"SPM.3039": {
		"facts": "Panasonic EYG-E0912XD6D graphite thermal interface sheet, 115 × 90 × 1 mm, gray, with adhesive on one side.",
		"source": "https://www.digikey.es/en/products/detail/panasonic-electronic-components/EYG-E0912XD6D/5844917",
	},
	"RVM.3020": {
		"facts": "MaxLinear SP335EER1-L multiprotocol RS-232/RS-422/RS-485 transceiver, 3.0–5.5 V supply, 20 Mb/s maximum data rate, ±15 kV ESD protection and 32-pin QFN package.",
		"source": "https://www.mouser.com/ProductDetail/MaxLinear/SP335EER1-L?qs=2Ga3DkcWsp0dU5IfUNiqhQ%3D%3D",
	},
	"SPL.3007": {
		"facts": "Misumi SB605ZZ stainless-steel deep-groove ball bearing with double shields, 5 mm bore, 14 mm outside diameter and 5 mm width.",
		"source": "https://uk.misumi-ec.com/vona2/detail/110302590640/?HissuCode=C-SB605ZZ",
	},
	"990004": {
		"facts": "Misumi C-SFL686ZZ stainless-steel flanged ball bearing with double shields, 6 mm bore, 13 mm outside diameter, 5 mm width and 15 mm flange diameter.",
		"source": "https://us.misumi-ec.com/pdf/fa/2019/2019_US_1032.pdf",
	},
	"990001": {
		"facts": "NSK F696ZZ1 flanged miniature deep-groove ball bearing, 6 mm bore, 15 mm outside diameter, 5 mm width and 17 mm flange diameter.",
		"source": "https://www.oss.nsk.com/products/bearings/ball-bearings/deep-groove-ball-bearings/extra-small-ball-bearings-and-miniature-ball-bearings-metric-series-with-flamge/f696zz1-esm-md-wf.html",
	},
	"RVM.3032": {
		"facts": "igus iglide G GTM-0913-010 self-lubricating thrust washer, 9.2 mm inside diameter, 13 mm outside diameter and 1 mm thickness.",
		"source": "https://www.igus.com/iglide-ibh/thrust-washers/product-details/iglide-g-m?artnr=GTM-0913-010",
	},
	"MAT.1001": {
		"facts": "Virgin FL100 PTFE round rod, 15 mm diameter; a chemically resistant, low-friction fluoropolymer machining stock.",
		"source": "https://fluorocarbon.co.uk/products/materials/ptfe/",
	},
	"MAT.1003": {
		"facts": "TIVAR 1000 virgin UHMW-PE round rod, 15 mm diameter; engineering plastic stock with low friction and high wear resistance.",
		"source": "https://www.mcam.com/en/products/shapes/engineering/tivar/tivar-1000-virgin-uhmw-pe",
	},
	"MAT.1007": {
		"facts": "Guarniflon G400 virgin PTFE ground round rod, 16.5 mm diameter, specified at +0.1/0 mm; chemically resistant, low-friction machining stock.",
		"source": "https://www.guarniflon.com/en/resources/materials/ptfe/virgin-ptfe-g400",
	},
	"MAT.1016": {
		"facts": "Guarniflon G400 virgin PTFE ground round rod, 16 mm nominal diameter and 2 m length; chemically resistant, low-friction machining stock.",
		"source": "https://www.guarniflon.com/en/resources/materials/ptfe/virgin-ptfe-g400",
	},
	"MAT.1009": {
		"facts": "Fluorseals fluteck K300 natural PEEK extruded round rod, 30 mm diameter; high-performance engineering polymer stock with strong mechanical, chemical and thermal resistance.",
		"source": "https://www.fluorseals.it/materials/fluteck-k-peek/",
	},
	"MAT.1010": {
		"facts": "Fluorseals fluteck K300 natural PEEK extruded round rod, 40 mm diameter; high-performance engineering polymer stock with strong mechanical, chemical and thermal resistance.",
		"source": "https://www.fluorseals.it/materials/fluteck-k-peek/",
	},
	"MAT.1020": {
		"facts": "Fluorseals fluteck K300 natural PEEK extruded round rod, 30.0 ±0.2 mm diameter; high-performance engineering polymer machining stock.",
		"source": "https://www.fluorseals.it/materials/fluteck-k-peek/",
	},
	"PRD.1025": {
		"facts": "Sylvac S_Dial Work Nano digital indicator with 12.5 mm measuring range, 0.1 µm resolution, high-visibility tolerance display and IP54 protection.",
		"source": "https://www.sylvac.ch/de/produkt/digital-indicators-s_dial-work-nano-nano-smart/",
	},
	"PRD.1026": {
		"facts": "Sylvac S_Dial Work Nano Smart digital indicator with 25 mm measuring range, 0.1 µm resolution, Bluetooth data transfer and IP54 protection.",
		"source": "https://www.sylvac.ch/de/produkt/digital-indicators-s_dial-work-nano-nano-smart/",
	},
	"PRD.1027": {
		"facts": "DIATEST MST58 checking stand for precise and repeatable bore gauging, with an approximately 35 mm measuring stroke and 58 mm table.",
		"source": "https://www.diatest.com/en/products/accessories/checking-stands/",
	},
	"PRD.1034": {
		"facts": "Sylvac PS16 V2 measuring bench with 25 mm range, 0.1 µm selectable resolution, 1.5 µm maximum error, 0.2 µm repeatability, adjustable measuring force and USB/Bluetooth output.",
		"source": "https://www.sylvac.ch/wp-content/uploads/2024/11/SYL1503_PS16V2_EN_Web.pdf",
	},
	"PRD.1126": {
		"facts": "Sylvac S_Dial Work Basic digital indicator with 25 mm measuring range and selectable 0.01 mm or 0.001 mm display resolution.",
		"source": "https://www.sylvac.ch/product/digital-indicators-s_dial-work-basic/",
	},
	"C100": {
		"facts": "Mean Well GSM60A18-P1J regulated AC/DC desktop adapter, 18 VDC at 3.33 A (60 W), with IEC C14 inlet and 5.5 × 2.1 mm center-positive P1J barrel plug.",
		"source": "https://medical.meanwell.com/Upload/PDF/GSM60A/GSM60A-SPEC.PDF",
	},
}


SUPPLIER_WEBSITE_FALLBACKS = {
	"Bossard AG": "https://www.bossard.com/eshop/ch-en/advanced-search",
	"Bosch GmbH": "https://www.bosch-professional.com/",
	"Bambu Lab EU": "https://eu.store.bambulab.com/",
	"Cavitech SA": "https://www.cavitech.ch/home-en.html",
	"Conrad AG": "https://www.conrad.ch/",
	"Digikey": "https://www.digikey.com/",
	"Digitec Galaxus AG": "https://www.digitec.ch/",
	"Distrelec": "https://www.distrelec.ch/",
	"Dongguan Mechplus Tech Co., Ltd.": "https://www.mechplus.com/",
	"Farnell AG": "https://ch.farnell.com/",
	"FlexFluidics": "https://flexfluidics.com/precision-glass-syringes/3cm-fe-syringe/",
	"Fluorocarbon": "https://fluorocarbon.co.uk/products/materials/ptfe/",
	"Fluorseals": "https://www.fluorseals.it/",
	"Guarniflon": "https://www.guarniflon.com/",
	"GM Précision": "https://www.gmprecision.ch/",
	"Gugler Elektronik AG": "https://www.gugler-elektronik.ch/",
	"HLH Prototypes Co Ltd": "https://www.hlhprototypes.com/cnc-machining/",
	"IGUS": "https://www.igus.com/",
	"Logystem SA": "https://www.logystem.ch/",
	"Misumi": "https://uk.misumi-ec.com/",
	"MK Fluidic Systems": "https://www.mkfluidicsystems.com/products/syringes/",
	"Mouser": "https://www.mouser.ch/",
	"PCBGoGo": "https://www.pcbgogo.com/",
	"PCBWay": "https://www.pcbway.com/",
	"RS Components GmbH": "https://ch.rs-online.com/",
	"SFS Group": "https://www.sfs.ch/en/",
	"StepperOnline": "https://www.omc-stepperonline.com/",
	"SZ LCH INDUSTRY CO., LTD": "https://www.wlc-cnc.com/",
	"WeDirekt": "https://www.wedirekt.de/",
}

CUSTOM_MACHINING_SUPPLIERS = {
	"HLH Prototypes Co Ltd",
	"Dongguan Mechplus Tech Co., Ltd.",
	"Shenzhen Ruiyi Model Technology Co.,Ltd",
	"SZ LCH INDUSTRY CO., LTD",
}

PCB_SUPPLIERS = {
	"Gugler Elektronik AG",
	"JLCPCB",
	"PCBGoGo",
	"PCBWay",
	"RC2 ELECTRONIQUE SA",
	"SYSTRONIC",
	"WeDirekt",
}

EVIDENCE_BASIS_LABELS = {
	"researched": "Exact supplier/manufacturer product page",
	"erp-catalog": "Existing Item and submitted purchase-document specifications",
	"previous-generated": "Previously reviewed generated catalog specification",
	"supplier-capability": "Supplier capability and AMF-controlled drawing/specification",
	"group-specification": "Supplier product family and ERP item classification",
	"supplier-catalog": "Supplier catalog and approved supplier part number",
	"safe-fallback": "ERP item identity; confirm the approved drawing/specification before substitution",
}

PART_CHILD_GROUPS = (
	"Fasteners",
	"Bearings and Bushings",
	"Springs",
	"Seals and Elastomers",
	"Fluidic Components",
	"Motors and Motion",
	"Sensors and Magnets",
	"Electrical Connectors and Wiring",
	"Electronic Components",
	"Thermal Components",
	"Custom Mechanical Parts",
	"General Mechanical Parts",
)

PART_GROUP_PARENT = "Part"

PART_ITEM_GROUP_OVERRIDES = {
	"700017": "Sensors and Magnets",
	"990003": "Fluidic Components",
	"RVM.3044": "Electronic Components",
	"RVM.3047": "Electrical Connectors and Wiring",
}

CUSTOM_PART_SUPPLIERS = CUSTOM_MACHINING_SUPPLIERS.union({
	"ARRK LCO Protomoule",
	"AUPI",
	"Bossme'd",
	"DDLG",
	"Décolletage Laurent Rais SA",
	"G-Shank",
	"GM Précision",
	"JFB (Jean-François Baud) SA",
	"Mécamachine",
	"Presse étude",
	"Tole Factory SA",
})


def esc(value):
	return html.escape(str(value or "").strip(), quote=True)


def plain(value):
	value = re.sub(r"<[^>]+>", " ", str(value or ""))
	return re.sub(r"\s+", " ", html.unescape(value)).strip()


def div(label, value):
	return "<div><strong>{}:</strong> {}</div>".format(esc(label), esc(value))


def normalized(value):
	return re.sub(r"[^a-z0-9]+", " ", plain(value).lower()).strip()


def clean_client_text(value):
	value = re.sub(r"\bnon[\s-]*medical\b", "", plain(value), flags=re.IGNORECASE)
	value = re.sub(r"\bRVM\s*Mini\b", "RVM mini", value, flags=re.IGNORECASE)
	value = re.sub(r"\bu[lL]\b", "µL", value)
	value = re.sub(r"\bm[lL]\b", "mL", value)
	return re.sub(r"\s+([,.;:])", r"\1", re.sub(r"\s+", " ", value)).strip(" ,.;:")


def clean_title(item):
	code = plain(item.get("item_code") or item.get("name"))
	name = plain(item.get("item_name"))
	name = re.sub(r"^{}\s*[-:–—]?\s*".format(re.escape(code)), "", name, flags=re.IGNORECASE).strip()
	name = re.sub(r"\bRVM\s*Mini\b", "RVM mini", name, flags=re.IGNORECASE)
	if not name or normalized(name) == normalized(code):
		return "Reference-specific {}".format(group_identity(item).lower())
	return clean_client_text(name).rstrip(" .")


def group_identity(item):
	return {
		"Accessory": "equipment accessory",
		"Assembly": "production subassembly",
		"Bearings and Bushings": "bearing or bushing",
		"Body": "actuator body component",
		"Cable": "electrical cable or power component",
		"Custom Mechanical Parts": "custom mechanical component",
		"Electrical Connectors and Wiring": "electrical connector or wiring component",
		"Electronic Board": "electronic circuit board",
		"Electronic Components": "electronic component",
		"Fasteners": "mechanical fastener",
		"Fluidic Components": "fluidic component",
		"General Mechanical Parts": "mechanical component",
		"Generic Item": "equipment or production supply",
		"Glass": "glass component",
		"Kit": "component kit",
		"Marketing Material": "printed marketing material",
		"Motors and Motion": "motor or motion component",
		"Packaging": "packaging component",
		"Part": "production component",
		"Plunger": "syringe plunger",
		"Raw Material": "machining raw material",
		"Seals and Elastomers": "seal or elastomer component",
		"Sensors and Magnets": "sensor or magnet",
		"Springs": "spring component",
		"Storage": "storage equipment",
		"Syringe": "precision glass syringe",
		"Thermal Components": "thermal-management component",
		"Tool": "production or inspection tool",
	}.get(item.get("item_group"), "purchased item")


def strip_unsafe_html(value):
	value = re.sub(r"<\s*(script|style)\b[^>]*>.*?<\s*/\s*\1\s*>", "", str(value or ""), flags=re.I | re.S)
	return re.sub(r"\s+on[a-z]+\s*=\s*(['\"]).*?\1", "", value, flags=re.I | re.S).strip()


def html_lines(value):
	value = str(value or "")
	value = re.sub(r"(?i)<br\s*/?>|</(?:div|p|li|ul|ol|h[1-6])>", "\n", value)
	value = re.sub(r"<[^>]+>", " ", value)
	return [re.sub(r"\s+", " ", html.unescape(line)).strip(" •\t") for line in value.splitlines()]


NOISE_PREFIXES = (
	"code:", "reference:", "name:", "group:", "components:", "initially created for",
	"product details", "détails du produit", "informations environnementales", "information additionnelle",
	"informations sur l‘article", "informations sur l'article", "remarque sur l'utilisation",
	"réglementation reach", "rohs", "reach", "pas de déclaration", "unspsc", "catalogue papier", "ancien numéro",
	"country of origin", "pays d'origine", "gross weight", "poids brut", "packaging dimensions",
	"dimensions de l'emballage", "customs number", "numéro des douanes",
)


def meaningful_lines(value, item, maximum=8):
	code = normalized(item.get("item_code") or item.get("name"))
	name = normalized(item.get("item_name"))
	result = []
	seen = set()
	for line in html_lines(value):
		line = re.sub(r"https?://\S+", "", line, flags=re.I).strip(" ;,-")
		key = normalized(line)
		if not key or key in seen or key in (code, name):
			continue
		if any(line.lower().startswith(prefix) for prefix in NOISE_PREFIXES):
			continue
		if re.search(r"(?:CHF|EUR|USD|\$|€)\s*\d|\d\s*(?:CHF|EUR|USD|€)", line, re.I):
			continue
		if len(line) < 3:
			continue
		seen.add(key)
		result.append(line)
		if len(result) >= maximum:
			break
	return result


def extract_between(value, start, end):
	match = re.search(re.escape(start) + r"(.*?)" + re.escape(end), str(value or ""), flags=re.S)
	return match.group(1).strip() if match else ""


def original_internal_note(value):
	if INTERNAL_START in str(value or ""):
		return strip_unsafe_html(extract_between(value, PRESERVED_START, PRESERVED_END))
	return strip_unsafe_html(value)


def choose_catalog_facts(item, purchase_descriptions, suppliers):
	code = item.get("item_code") or item.get("name")
	if code in RESEARCHED_ITEMS:
		return clean_client_text(RESEARCHED_ITEMS[code]["facts"]), "researched"
	if CLIENT_START in str(item.get("description") or ""):
		previous = plain(extract_between(item.get("description"), FACTS_START, FACTS_END))
		if previous:
			basis = plain(extract_between(item.get("description"), BASIS_START, BASIS_END))
			if basis not in EVIDENCE_BASIS_LABELS:
				old_internal = plain(item.get("internal_description"))
				basis = next(
					(key for key, label in EVIDENCE_BASIS_LABELS.items() if label in old_internal),
					"previous-generated",
				)
			return clean_client_text(previous), basis

	lines = []
	for value in [item.get("description")] + list(purchase_descriptions):
		for line in meaningful_lines(value, item):
			if normalized(line) not in {normalized(existing) for existing in lines}:
				lines.append(line)
		if len(lines) >= 6:
			break
	if lines:
		facts = "; ".join(lines[:6]).strip(" ;")
		if len(facts) > 750:
			facts = facts[:747].rsplit(" ", 1)[0] + "…"
		return clean_client_text(facts), "erp-catalog"

	supplier_names = {row.get("supplier") for row in suppliers}
	if item.get("item_group") == "Electronic Board":
		return "Custom printed circuit board produced to the controlled AMF electronic design and revision for laboratory and OEM fluid-handling equipment.", "supplier-capability"
	if "Cavitech SA" in supplier_names:
		return "Custom cable assembly manufactured and electrically tested to the controlled AMF wiring specification for laboratory and OEM equipment.", "supplier-capability"
	if supplier_names.intersection(CUSTOM_MACHINING_SUPPLIERS):
		return "Custom-manufactured precision component produced to the controlled AMF drawing and revision for laboratory and OEM fluid-handling equipment.", "supplier-capability"
	if item.get("item_group") in ("Syringe", "Glass"):
		return "Precision-bore glass syringe for accurate liquid dosing in AMF laboratory and OEM syringe-pump systems; exact capacity and interface are controlled by this item reference.", "group-specification"
	if item.get("item_group") == "Plunger":
		return "Precision syringe plunger for AMF laboratory and OEM syringe-pump systems; material, capacity and interface are controlled by this item reference.", "group-specification"
	if supplier_names.intersection({"Bossard AG", "SFS Group"}):
		return "Standard fastening component procured to the DIN, ISO or BN designation, dimensions, material and finish stated in the item title and approved supplier part number.", "supplier-catalog"
	if supplier_names.intersection({"Misumi", "SMB Bearings Limited", "IGUS"}):
		return "Catalog mechanical component procured to the model, dimensions, material and finish stated in the item title and approved supplier part number.", "supplier-catalog"
	if supplier_names.intersection({"Digikey", "Distrelec", "Farnell AG", "Mouser", "RS Components GmbH"}):
		return "Catalog electrical or electronic component procured to the manufacturer model and technical specification stated in the item title and approved supplier part number.", "supplier-catalog"
	return "Purchased {} selected for AMF laboratory, production or OEM fluid-handling equipment; the exact approved specification is controlled by this item reference.".format(group_identity(item)), "safe-fallback"


def classify_part_item(item, facts, suppliers):
	"""Return a stable child group for items currently classified under Part."""
	current_group = item.get("item_group") or ""
	if current_group in PART_CHILD_GROUPS:
		return current_group
	if current_group != PART_GROUP_PARENT:
		return current_group
	item_code = item.get("item_code") or item.get("name")
	if item_code in PART_ITEM_GROUP_OVERRIDES:
		return PART_ITEM_GROUP_OVERRIDES[item_code]

	text = "{} {} {}".format(
		plain(item.get("item_name")),
		plain(item.get("reference_code")),
		plain(facts),
	).lower()
	rules = (
		("Bearings and Bushings", r"\b(?:bearing|bushing|palier)\b|roulement|plain bearing|iglid|thrust washer"),
		("Seals and Elastomers", r"\bo[- ]?ring\b|\boring\b|joint torique|\bseal\b|gasket|\bnbr\b|\bepdm\b|viton|elastomer|rubber foot|bumpon"),
		("Springs", r"\bspring\b|ressort|belleville|lame flexible|spring blade"),
		("Fluidic Components", r"fluidic|fitting|ferrule|tubing|tube mixer|nanotight|sample loop|manifold|peek connector|syringe to connector|1/4-28|gripper|cap 5\s*m[lL]|plug core"),
		("Thermal Components", r"thermal(?!\s+sleeve)|thermist|thermostat|peltier|heatsink|heat sink|\bheater\b|incubator"),
		("Electronic Components", r"resistor|résistance|\bdiode\b|transceiver|microcontroller|expander|expandeur|\bi2c\b|\bsmbus\b|\bbuffer\b|\bdriver\b|\bswitch\b|integrated circuit|microchip|\bic\b|\btvs\b|\bpcb\b|mosfet|\bdisplay\b|7-?seg|uart|usb bridge"),
		("Motors and Motion", r"\bmotor\b|stepper|pulley|\bbelt\b|courroie|camshaft|oldham|lead screw|eichenberger|spindle|coupling|couplage|\bgear\b|gearbox|actuator"),
		("Electrical Connectors and Wiring", r"\bconnector\b|conn housing|conn plug|conn header|\bcable\b|\bcbl\b|\bwire\b|wiring|\busb\b|picoblade|receptacle|pre-crimp|\bcrimp\b|ferrite|shielding tape|power jack|thermal sleeve|protection sleeve|heat\s*shrink|heatshrink|\bjumper\b"),
		("Sensors and Magnets", r"\bsensor\b|\bmagnet\b|magnetic scale|\bhall\b|\bencoder\b"),
		("Fasteners", r"\bscrews?\b|\bvis\b|\bbolts?\b|\bnuts?\b|écrou|ecrou|\bwashers?\b|rondelle|\bpins?\b|goupille|spacer|standoff|stand-off|goujon|threaded|\bclip\b|circlip|retaining ring|fastening component"),
	)
	for group, pattern in rules:
		if re.search(pattern, text, flags=re.IGNORECASE):
			return group

	supplier_names = {row.get("supplier") for row in suppliers}
	if supplier_names.intersection({"Bossard AG", "SFS Group"}):
		return "Fasteners"
	if supplier_names.intersection(CUSTOM_PART_SUPPLIERS):
		return "Custom Mechanical Parts"
	return "General Mechanical Parts"


def client_description(item, facts, fact_basis="safe-fallback"):
	code = item.get("item_code") or item.get("name")
	return "".join([
		CLIENT_START,
		"<div><strong>{}</strong></div>".format(esc(clean_title(item))),
		FACTS_START,
		"<div>{}</div>".format(esc(facts)),
		FACTS_END,
		BASIS_START,
		esc(fact_basis),
		BASIS_END,
		"<div><br></div>",
		div("Item reference", code),
		CLIENT_END,
	])


def key_specification(item, facts=""):
	text = clean_title(item)
	if text.lower().startswith("reference-specific") and facts:
		text = facts
	text = re.sub(r"\bRVM\s*Mini\b", "RVM mini", text, flags=re.I)
	text = re.sub(r"\s+", " ", text).strip(" .;:-")
	return text[:125]


def customs_description(item, facts=""):
	code = item.get("item_code") or item.get("name")
	if code in RESEARCHED_ITEMS:
		facts = RESEARCHED_ITEMS[code]["facts"]
	text = "{} {}".format(clean_title(item), facts).lower()
	spec = key_specification(item, facts)
	group = item.get("item_group")
	if group == "Electronic Board":
		return "Printed electronic circuit board; {}".format(spec)[:200]
	if group in ("Syringe", "Glass"):
		return "Precision glass syringe for liquid-handling equipment; {}".format(spec)[:200]
	if group == "Plunger":
		return "Engineering-plastic syringe plunger; {}".format(spec)[:200]

	patterns = [
		(r"\b(ribbon cable|electrical cable|cable assembly|cable mounted|wire assembly|usb cable|cbl ribn)\b", "Electrical cable or cable assembly"),
		(r"\b(transceiver|integrated circuit|electronic component|usb bridge|uart|rs-?232|rs-?422|rs-?485|ic usb)\b", "Electronic integrated circuit"),
		(r"\b(printed circuit|circuit board|pcb)\b", "Printed electronic circuit board"),
		(r"\b(syringe plunger|plunger)\b", "Engineering-plastic syringe plunger"),
		(r"\b(syringe glass|glass syringe|precision-bore glass syringe)\b", "Precision glass syringe for liquid-handling equipment"),
		(r"\b(vis|screw|bolt|socket head|din 7984|iso 4762)\b", "Steel machine screw"),
		(r"\b(rondelle|washer)\b", "Metal or engineering-plastic washer"),
		(r"\b(écrou|ecrou|nut)\b", "Steel machine nut"),
		(r"\b(goupille|dowel|locating pin)\b", "Metal locating pin"),
		(r"\b(ressort|spring)\b", "Metal spring"),
		(r"\b(roulement|bearing)\b", "Miniature ball bearing"),
		(r"\b(entretoise|spacer)\b", "Engineering-plastic spacer"),
		(r"\b(aimant|magnet)\b", "Permanent magnet"),
		(r"\b(joint torique|o-ring|oring)\b", "Elastomer O-ring seal"),
		(r"\b(courroie|timing belt|belt)\b", "Rubber timing belt"),
		(r"\b(poulie|pulley)\b", "Metal timing pulley"),
		(r"\b(thermistor|thermistance|ntc)\b", "Electronic temperature sensor"),
		(r"\b(connector|conn housing|receptacle|molex|jst)\b", "Electrical connector housing"),
		(r"\b(ferrite)\b", "Ferrite cable interference suppressor"),
		(r"\b(switch|pushbutton)\b", "Electrical pushbutton switch"),
		(r"\b(thermal pad|thermal interface)\b", "Thermal interface sheet"),
		(r"\b(power supply|ac/dc|adapter)\b", "AC/DC electrical power adapter"),
	]
	for pattern, lead in patterns:
		if re.search(pattern, text, re.I):
			return "{}; {}".format(lead, spec)[:200]

	lead = {
		"Accessory": "Equipment accessory",
		"Assembly": "Mechanical/electromechanical subassembly",
		"Bearings and Bushings": "Bearing or self-lubricating bushing",
		"Body": "Machined actuator housing component",
		"Cable": "Electrical cable assembly",
		"Custom Mechanical Parts": "Custom mechanical equipment component",
		"Electrical Connectors and Wiring": "Electrical connector or wiring component",
		"Electronic Board": "Printed electronic circuit board",
		"Electronic Components": "Electronic equipment component",
		"Fasteners": "Metal or engineering-plastic machine fastener",
		"Fluidic Components": "Fluid-handling equipment component",
		"General Mechanical Parts": "Mechanical equipment component",
		"Generic Item": "Laboratory or production equipment",
		"Glass": "Laboratory glass component",
		"Kit": "Mechanical component kit",
		"Marketing Material": "Printed promotional material",
		"Motors and Motion": "Electric motor or mechanical motion component",
		"Packaging": "Product packaging material",
		"Part": "Mechanical/electromechanical equipment component",
		"Plunger": "Engineering-plastic syringe plunger",
		"Raw Material": "Engineering-plastic machining rod",
		"Seals and Elastomers": "Elastomer seal or damping component",
		"Sensors and Magnets": "Electrical sensor or permanent magnet",
		"Springs": "Metal spring component",
		"Storage": "Plastic storage equipment",
		"Syringe": "Precision glass syringe for liquid-handling equipment",
		"Thermal Components": "Thermal-management equipment component",
		"Tool": "Production or dimensional-inspection tool",
	}.get(group, "Laboratory equipment component")
	return "{}; {}".format(lead, spec)[:200]


def supplier_website(row):
	website = plain(row.get("website")) or SUPPLIER_WEBSITE_FALLBACKS.get(row.get("supplier"), "")
	if website and not re.match(r"^https?://", website, re.I):
		website = "https://" + website
	return website


def supplier_line(row):
	name = row.get("supplier") or "Supplier not set"
	part = plain(row.get("supplier_part_no"))
	website = supplier_website(row)
	label = esc(name)
	if website:
		label = '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>'.format(esc(website), label)
	if part:
		label += " — supplier part {}".format(esc(part))
	return label


def internal_description(item, facts, fact_basis, suppliers, purchases, usage):
	code = item.get("item_code") or item.get("name")
	parts = [
		INTERNAL_START,
		"<div><strong>Procurement and production specification</strong></div>",
		div("ERP item", "{} — {}".format(code, plain(item.get("item_name")))),
		div("Classification", "{} / {}".format(item.get("item_group") or "Not set", item.get("item_type") or "Not set")),
		div("Stock unit", item.get("stock_uom") or "Not set"),
		div("Verified/catalog facts", facts),
		div("Evidence basis", EVIDENCE_BASIS_LABELS.get(fact_basis, fact_basis)),
	]

	research = RESEARCHED_ITEMS.get(code)
	if research:
		parts.append('<div><strong>Exact technical source:</strong> <a href="{}" target="_blank" rel="noopener noreferrer">supplier/manufacturer product page</a></div>'.format(esc(research["source"])))

	if suppliers:
		parts.append("<div><strong>Approved/actual suppliers:</strong></div><ul>{}</ul>".format(
			"".join("<li>{}</li>".format(supplier_line(row)) for row in suppliers)
		))
	else:
		parts.append(div("Approved/actual suppliers", "No supplier master row found; use submitted purchase history below"))

	if purchases:
		latest = purchases[0]
		parts.append(div("Latest submitted purchase", "{} from {} ({})".format(
			latest.get("date"), latest.get("supplier"), latest.get("document")
		)))
	if usage.get("products"):
		parts.append(div("Used in active product BOMs", ", ".join(usage["products"][:20])))
	elif usage.get("parents"):
		parts.append(div("Direct active BOM parents", ", ".join(usage["parents"][:20])))
	else:
		parts.append(div("BOM usage", "No active submitted BOM usage found; verify intended use before issue to production"))

	legacy = original_internal_note(item.get("internal_description"))
	if legacy:
		parts.extend([
			"<div><strong>Existing production/catalog notes (preserved):</strong></div>",
			PRESERVED_START,
			legacy,
			PRESERVED_END,
		])
	else:
		parts.extend([PRESERVED_START, PRESERVED_END])
	parts.append(INTERNAL_END)
	return "".join(parts)


def load_target_items(frappe):
	rows = frappe.db.sql(
		"""
		select distinct i.name
		from tabItem i
		where i.disabled = 0
		  and i.is_purchase_item = 1
		  and i.item_group != 'Product'
		  and i.name not in %(excluded)s
		  and (i.is_stock_item = 1 or i.name in %(included_non_stock)s)
		  and exists (
			select 1
			from `tabPurchase Invoice Item` pii
			join `tabPurchase Invoice` pi on pi.name = pii.parent
			where pii.item_code = i.name and pi.docstatus = 1
		  )
		order by i.name
		""",
		{
			"excluded": tuple(sorted(EXCLUDED_NON_PHYSICAL_ITEMS)),
			"included_non_stock": tuple(sorted(INCLUDED_NON_STOCK_ITEMS)),
		},
		as_dict=True,
	)
	names = [row.name for row in rows]
	if not names:
		return []
	fields = [
		"name", "item_code", "item_name", "item_group", "item_type", "reference_code",
		"description", "internal_description", "custom_description", "customs_tariff_number",
		"stock_uom", "purchase_uom", "is_stock_item", "modified",
	]
	items = frappe.get_all("Item", filters={"name": ["in", names]}, fields=fields, limit_page_length=10000)
	return sorted(items, key=lambda row: row.name)


def load_procurement(frappe, item_names):
	if not item_names:
		return {}, {}, {}
	params = {"items": tuple(item_names)}
	item_supplier_rows = frappe.db.sql(
		"""
		select isi.parent item_code, isi.idx, isi.supplier, isi.supplier_part_no, s.website
		from `tabItem Supplier` isi
		left join tabSupplier s on s.name = isi.supplier
		where isi.parent in %(items)s
		order by isi.parent, isi.idx
		""",
		params,
		as_dict=True,
	)
	purchase_rows = frappe.db.sql(
		"""
		select pii.item_code, pi.posting_date date, pi.supplier, pi.name document,
		       pii.description, pii.manufacturer, pii.manufacturer_part_no, pii.brand
		from `tabPurchase Invoice Item` pii
		join `tabPurchase Invoice` pi on pi.name = pii.parent
		where pi.docstatus = 1 and pii.item_code in %(items)s
		order by pii.item_code, pi.posting_date desc, pi.name desc, pii.idx
		""",
		params,
		as_dict=True,
	)
	receipt_rows = frappe.db.sql(
		"""
		select pri.item_code, pr.posting_date date, pr.supplier, pr.name document,
		       pri.description, pri.supplier_part_no, pri.manufacturer, pri.manufacturer_part_no, pri.brand
		from `tabPurchase Receipt Item` pri
		join `tabPurchase Receipt` pr on pr.name = pri.parent
		where pr.docstatus = 1 and pri.item_code in %(items)s
		order by pri.item_code, pr.posting_date desc, pr.name desc, pri.idx
		""",
		params,
		as_dict=True,
	)

	suppliers = defaultdict(list)
	for row in item_supplier_rows:
		if row.supplier:
			suppliers[row.item_code].append(row)
	purchases = defaultdict(list)
	for row in purchase_rows:
		purchases[row.item_code].append(row)
	descriptions = defaultdict(list)
	for row in list(purchase_rows) + list(receipt_rows):
		if row.get("description"):
			descriptions[row.item_code].append(row.description)

	# Include actual suppliers even where the Item Supplier child table is old or missing.
	for item_code, rows in purchases.items():
		known = {row.supplier for row in suppliers[item_code]}
		for purchase in rows:
			if purchase.supplier in known:
				continue
			website = frappe.db.get_value("Supplier", purchase.supplier, "website") or ""
			suppliers[item_code].append({
				"supplier": purchase.supplier,
				"supplier_part_no": "",
				"website": website,
			})
			known.add(purchase.supplier)
	return suppliers, purchases, descriptions


def load_bom_usage(frappe, target_names):
	if not target_names:
		return {}
	boms = frappe.db.sql(
		"""
		select b.name, b.item, b.is_default, b.modified
		from tabBOM b
		join tabItem parent_item on parent_item.name = b.item and parent_item.disabled = 0
		where b.docstatus = 1 and b.is_active = 1
		order by b.item, b.is_default desc, b.modified desc, b.name desc
		""",
		as_dict=True,
	)
	selected = {}
	for row in boms:
		selected.setdefault(row.item, row)
	if not selected:
		return {}
	components = frappe.db.sql(
		"""
		select parent, item_code
		from `tabBOM Item`
		where parent in %(parents)s
		""",
		{"parents": tuple(row.name for row in selected.values())},
		as_dict=True,
	)
	bom_to_item = {row.name: row.item for row in selected.values()}
	parents_by_component = defaultdict(set)
	all_names = set(target_names)
	for row in components:
		parent_item = bom_to_item.get(row.parent)
		if parent_item:
			parents_by_component[row.item_code].add(parent_item)
			all_names.update((row.item_code, parent_item))
	groups = dict(frappe.db.sql(
		"select name, item_group from tabItem where name in %(items)s",
		{"items": tuple(all_names)},
	))

	usage = {}
	for item_code in target_names:
		seen = {item_code}
		queue = list(parents_by_component.get(item_code, set()))
		all_parents = set(queue)
		products = set()
		while queue:
			parent = queue.pop(0)
			if parent in seen:
				continue
			seen.add(parent)
			if groups.get(parent) == "Product":
				products.add(parent)
			for ancestor in parents_by_component.get(parent, set()):
				all_parents.add(ancestor)
				if ancestor not in seen:
					queue.append(ancestor)
		usage[item_code] = {
			"parents": sorted(all_parents),
			"products": sorted(products),
		}
	return usage


def build_updates(frappe):
	items = load_target_items(frappe)
	names = [row.name for row in items]
	suppliers_by_item, purchases_by_item, descriptions_by_item = load_procurement(frappe, names)
	usage_by_item = load_bom_usage(frappe, names)
	updates = []
	for item in items:
		suppliers = suppliers_by_item.get(item.name, [])
		purchases = purchases_by_item.get(item.name, [])
		facts, basis = choose_catalog_facts(item, descriptions_by_item.get(item.name, []), suppliers)
		new_item_group = classify_part_item(item, facts, suppliers)
		generated_item = dict(item)
		generated_item["item_group"] = new_item_group
		new_values = {
			"description": client_description(generated_item, facts, basis),
			"internal_description": internal_description(
				generated_item, facts, basis, suppliers, purchases, usage_by_item.get(item.name, {})
			),
			"custom_description": customs_description(generated_item, facts),
		}
		updates.append({
			"name": item.name,
			"item": dict(item),
			"facts": facts,
			"fact_basis": basis,
			"suppliers": [dict(row) for row in suppliers],
			"purchases": [dict(row) for row in purchases[:5]],
			"usage": usage_by_item.get(item.name, {}),
			"new_item_group": new_item_group,
			"new_values": new_values,
		})
	return updates


def validate_updates(updates):
	errors = []
	seen = set()
	if not updates:
		errors.append("No active physical purchased items with submitted invoice history were found.")
	for row in updates:
		name = row["name"]
		if name in seen:
			errors.append("Duplicate generated Item: {}".format(name))
		seen.add(name)
		if name in EXCLUDED_NON_PHYSICAL_ITEMS:
			errors.append("Excluded non-physical Item entered update: {}".format(name))
		new_item_group = row.get("new_item_group")
		if row["item"].get("item_group") in (PART_GROUP_PARENT,) + PART_CHILD_GROUPS:
			if new_item_group not in PART_CHILD_GROUPS:
				errors.append("{} has invalid Part child group {}".format(name, new_item_group))
		for fieldname, value in row["new_values"].items():
			if not plain(value):
				errors.append("{} has empty {}".format(name, fieldname))
			if re.search(r"<\s*script", str(value), re.I):
				errors.append("{} has unsafe script markup in {}".format(name, fieldname))
		client = row["new_values"]["description"]
		if "non-medical" in plain(client).lower():
			errors.append("{} client description contains non-medical wording".format(name))
		if "RVM Mini" in plain(client) or "RVMmini" in plain(client):
			errors.append("{} uses incorrect RVM mini capitalization".format(name))
		if div("Item reference", row["item"].get("item_code") or name) not in client:
			errors.append("{} client Item reference is not the Item Code".format(name))
		if "<div><br></div>" + div("Item reference", row["item"].get("item_code") or name) not in client:
			errors.append("{} client Item reference does not start after a blank line".format(name))
		if len(plain(row["new_values"]["custom_description"])) > 512:
			errors.append("{} customs description exceeds DHL's 512-character limit".format(name))
	if errors:
		raise RuntimeError("Purchased-item description validation failed:\n- " + "\n- ".join(errors[:100]))


def report_summary(updates):
	changed = [
		row for row in updates
		if row["item"].get("item_group") != row["new_item_group"]
		or any((row["item"].get(field) or "") != value for field, value in row["new_values"].items())
	]
	return {
		"target_count": len(updates),
		"changed_count": len(changed),
		"item_group_changed_count": sum(
			row["item"].get("item_group") != row["new_item_group"] for row in updates
		),
		"stock_item_count": sum(bool(row["item"].get("is_stock_item")) for row in updates),
		"included_non_stock_equipment_count": sum(not row["item"].get("is_stock_item") for row in updates),
		"researched_exact_item_count": sum(row["name"] in RESEARCHED_ITEMS for row in updates),
		"preserved_internal_note_count": sum(bool(original_internal_note(row["item"].get("internal_description"))) for row in updates),
		"group_counts": dict(sorted(Counter(row["item"].get("item_group") for row in updates).items())),
		"resulting_group_counts": dict(sorted(Counter(row["new_item_group"] for row in updates).items())),
		"part_child_group_counts": dict(sorted(Counter(
			row["new_item_group"] for row in updates if row["new_item_group"] in PART_CHILD_GROUPS
		).items())),
		"fact_basis_counts": dict(sorted(Counter(row["fact_basis"] for row in updates).items())),
		"maximum_customs_description_length": max(
			[len(plain(row["new_values"]["custom_description"])) for row in updates] or [0]
		),
	}


def serializable_update(row):
	return {
		"name": row["name"],
		"item_name": row["item"].get("item_name"),
		"item_group": row["item"].get("item_group"),
		"new_item_group": row["new_item_group"],
		"fact_basis": row["fact_basis"],
		"facts": row["facts"],
		"suppliers": row["suppliers"],
		"purchases": row["purchases"],
		"usage": row["usage"],
		"before": {
			field: row["item"].get(field)
			for field in ("description", "internal_description", "custom_description")
		},
		"after": row["new_values"],
	}


def write_json(path, value):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w", encoding="utf-8") as handle:
		json.dump(value, handle, ensure_ascii=False, indent=2, default=str)
		handle.write("\n")


def write_debug_csv(path, updates):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	fieldnames = [
		"item_code",
		"item_name",
		"new_item_group",
		"client_description",
		"internal_description",
		"customs_description",
	]
	with open(path, "w", encoding="utf-8-sig", newline="") as handle:
		writer = csv.DictWriter(handle, fieldnames=fieldnames)
		writer.writeheader()
		for row in updates:
			writer.writerow({
				"item_code": row["item"].get("item_code") or row["name"],
				"item_name": row["item"].get("item_name") or "",
				"new_item_group": row["new_item_group"],
				"client_description": row["new_values"]["description"],
				"internal_description": row["new_values"]["internal_description"],
				"customs_description": row["new_values"]["custom_description"],
			})


def file_sha256(path):
	digest = hashlib.sha256()
	with open(path, "rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def output_path(output_dir, filename):
	path = os.path.join(output_dir, filename)
	if not os.path.exists(path):
		return path
	stem, extension = os.path.splitext(filename)
	stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
	return os.path.join(output_dir, "{}_{}{}".format(stem, stamp, extension))


def ensure_part_item_groups(frappe_module):
	parent = frappe_module.db.get_value(
		"Item Group", PART_GROUP_PARENT, ["name", "is_group"], as_dict=True
	)
	if not parent or not parent.is_group:
		raise RuntimeError("Item Group {} must exist and be a group".format(PART_GROUP_PARENT))
	created = []
	for group_name in PART_CHILD_GROUPS:
		existing = frappe_module.db.get_value(
			"Item Group", group_name, ["parent_item_group", "is_group"], as_dict=True
		)
		if existing:
			if existing.parent_item_group != PART_GROUP_PARENT or existing.is_group:
				raise RuntimeError(
					"Item Group {} exists with an incompatible parent/type".format(group_name)
				)
			continue
		frappe_module.get_doc({
			"doctype": "Item Group",
			"item_group_name": group_name,
			"parent_item_group": PART_GROUP_PARENT,
			"is_group": 0,
			"show_in_website": 0,
		}).insert(ignore_permissions=True)
		created.append(group_name)
	return created


def self_test():
	item = {
		"name": "RVM.3001", "item_code": "RVM.3001", "item_name": "Round Spacer Nylon",
		"item_group": "Part", "internal_description": "<div>Keep this note.</div>",
	}
	client = client_description(item, RESEARCHED_ITEMS["RVM.3001"]["facts"])
	assert div("Item reference", "RVM.3001") in client
	assert "<div><br></div>" + div("Item reference", "RVM.3001") in client
	assert "non-medical" not in client.lower()
	assert original_internal_note("{}{}{}{}".format(INTERNAL_START, PRESERVED_START, item["internal_description"], PRESERVED_END)) == item["internal_description"]
	assert len(customs_description(item, RESEARCHED_ITEMS["RVM.3001"]["facts"])) <= 512


def apply_purchased_item_description_updates(frappe_module, update_modified=True):
	self_test()
	updates = build_updates(frappe_module)
	validate_updates(updates)
	created_groups = ensure_part_item_groups(frappe_module)
	changed = []
	for row in updates:
		new_values = dict(row["new_values"])
		new_values["item_group"] = row["new_item_group"]
		if any((row["item"].get(field) or "") != value for field, value in new_values.items()):
			changed.append(row)
			frappe_module.db.set_value(
				"Item",
				row["name"],
				new_values,
				modified_by="Administrator",
				update_modified=update_modified,
			)

	for row in updates:
		persisted = frappe_module.db.get_value(
			"Item", row["name"],
			["description", "internal_description", "custom_description", "item_group"], as_dict=True
		)
		expected = dict(row["new_values"])
		expected["item_group"] = row["new_item_group"]
		if any((persisted.get(field) or "") != value for field, value in expected.items()):
			raise RuntimeError("Post-write verification failed for Item {}".format(row["name"]))
	summary = report_summary(updates)
	summary["applied_count"] = len(changed)
	summary["created_item_group_count"] = len(created_groups)
	summary["created_item_groups"] = created_groups
	return summary


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--site", default="site1.local", help="Frappe site name")
	parser.add_argument("--apply", action="store_true", help="Persist the generated descriptions")
	parser.add_argument(
		"--output-dir",
		default=os.path.join(BENCH_PATH, "purchased_item_description_update_2026-08-20"),
		help="Directory for preview, backup and summary files",
	)
	parser.add_argument(
		"--csv-file",
		default=None,
		help="Path for the simple purchased-item description debug CSV",
	)
	args = parser.parse_args()
	self_test()

	import frappe

	frappe.init(site=args.site, sites_path=os.path.join(BENCH_PATH, "sites"))
	frappe.connect()
	try:
		frappe.set_user("Administrator")
		updates = build_updates(frappe)
		validate_updates(updates)
		summary = report_summary(updates)
		preview_path = output_path(args.output_dir, "preview.json")
		write_json(preview_path, [serializable_update(row) for row in updates])
		summary["preview_file"] = preview_path
		summary["preview_sha256"] = file_sha256(preview_path)
		csv_path = args.csv_file or os.path.join(args.output_dir, "purchased_item_descriptions_debug.csv")
		write_debug_csv(csv_path, updates)
		summary["csv_file"] = csv_path
		summary["csv_sha256"] = file_sha256(csv_path)

		if args.apply:
			backup_path = output_path(args.output_dir, "backup_before_apply.json")
			write_json(backup_path, [{
				"name": row["name"],
				"modified": row["item"].get("modified"),
				"item_group": row["item"].get("item_group"),
				"description": row["item"].get("description"),
				"internal_description": row["item"].get("internal_description"),
				"custom_description": row["item"].get("custom_description"),
			} for row in updates])
			summary["backup_file"] = backup_path
			summary["backup_sha256"] = file_sha256(backup_path)
			applied = apply_purchased_item_description_updates(frappe)
			frappe.db.commit()
			summary["applied_count"] = applied["applied_count"]
			summary["created_item_group_count"] = applied["created_item_group_count"]
			summary["created_item_groups"] = applied["created_item_groups"]
			summary["applied"] = True
			summary["verified_count"] = len(updates)
		else:
			frappe.db.rollback()
			summary["applied"] = False

		summary_path = output_path(args.output_dir, "summary.json")
		write_json(summary_path, summary)
		print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
		print("Summary file: {}".format(summary_path))
	except Exception:
		frappe.db.rollback()
		raise
	finally:
		frappe.destroy()


if __name__ == "__main__":
	main()
