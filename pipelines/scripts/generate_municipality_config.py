#!/usr/bin/env python3
"""Generate the municipality_websites tuple for county_config.py from survey results.

Reads /tmp/zhb_pc_survey.json and outputs the Python tuple.
"""
import json

with open('/tmp/zhb_pc_survey.json') as f:
    data = json.load(f)

# Manual overrides (not available via SDK scan).
MANUAL_ENTRIES = {
    "York Twp": {
        "board_of_commissioners": "https://yorktownshippa.gov/boards/boc/",
        "planning_commission": "https://yorktownshippa.gov/boards/pc/",
        "zoning_hearing": "https://yorktownshippa.gov/boards/zhb/",
    },
    "Springettsbury Twp": {
        "board_of_supervisors": "https://springettsbury.com/township-document-archives/?_checkbox_filter_2=meeting-minutes",
    },
    "Manchester Twp": {
        "board_of_supervisors": "https://www.mantwp.com/meetings-agendas/",
    },
    "York City": {
        "city_council": "https://www.yorkcity.org/government/city-council/meetings/",
    },
    "Hanover Boro": {
        "borough_council": "https://hanoverboroughpa.gov/AgendaCenter",
    },
    "Manheim Twp": {
        "board_of_supervisors": "https://www.manheimtwpyorkpa.org/index.php/government/minutes-agendas",
    },
}

# Standard BOS/Council URLs from county_config (already there)
BOS_URLS = {
    "Carroll Twp": "https://www.carrolltownship.com/bos-agenda-2024/",
    "Codorus Twp": "https://codorustownship.org/meeting-minutes/",
    "Conewago Twp": "https://conewagotownship.com/boards-and-commissions/board-of-supervisors/minutes/",
    "Dover Twp": "https://www.dovertownship.org/minutes/",
    "East Hopewell Twp": "https://www.easthopewelltownshippa.gov/meetings",
    "East Prospect Boro": "https://www.eastprospectborough.com/minutes",
    "Fairview Twp": "https://www.fairviewtownship.com/boards/supervisors/minutes",
    "Fawn Grove Boro": "https://fawngroveborough.org/documents/council-meeting-minutes/",
    "Fawn Twp": "https://fawntownship.com/meetings/",
    "Franklin Twp": "https://franklintownship.org/meeting-minutes-agendas/",
    "Hallam Boro": "https://hallamborough.com/AgendaCenter",
    "Hellam Twp": "https://www.hellamtownship.gov/departments/public-meetings/",
    "Hopewell Twp": "https://www.hopewelltownship.com/public-meetings/board-of-supervisors/",
    "Jackson Twp": "https://jackson-township.org/meeting-agendas/",
    "Lewisberry Boro": "https://lewisberryborough.org/AgendaCenter/",
    "Manchester Boro": "https://manchesterborough.gov/AgendaCenter/",
    "Monaghan Twp": "https://monaghantownship.com/AgendaCenter",
    "New Salem Boro": "https://newsalemborough.org/AgendaCenter/",
    "North York Boro": "https://northyorkborough.com/borough-council-meeting-minutes/",
    "Peach Bottom Twp": "https://www.peachbottomtownship.org/meeting-minutes",
    "Penn Twp": "https://penntownship.org/meeting-minutes/",
    "Seven Valleys Boro": "https://sevenvalleysborough.com/minutes/",
    "Shrewsbury Boro": "https://shrewsburyborough.org/minutes/",
    "Shrewsbury Twp": "https://www.shrewsburytownship.org/minutes/",
    "Springfield Twp": "https://springfieldtownship.com/AgendaCenter",
    "Spring Garden Twp": "https://www.springgardentwp.org/meeting-minutes/",
    "Wellsville Boro": "https://wellsvilleborough.com/boards-commissions/borough-council-agenda-budget/",
    "West Manchester Twp": "https://www.westmanchestertownship.com/boards-committees/board-of-supervisors/",
    "Windsor Twp": "https://windsortownship.com/events-minutes/board-of-trustees/",
    "Wrightsville Boro": "https://wrightsvilleborough.com/meeting-minutes/",
    "Yoe Boro": "https://yoeborough.org/information/minutes/",
    "Yorkana Boro": "https://yorkanaborough.com/meeting-minutes/",
    "York Haven Boro": "https://yorkhavenborough.org/AgendaCenter/",
    # User-provided
    "Glen Rock Boro": "https://www.glenrockpa.org/borough-government/council-meeting-minutes-agendas/",
    "Chanceford Twp": "https://www.chancefordtwp.com/Minutes.html",
    "Delta Boro": "https://www.deltaborough.us/current-meeting-minutes",
    "Dillsburg Boro": "https://dillsburg.com/minutes/",
    "Dover Boro": "https://www.doverboroughpa.com/minutes.html",
    "Goldsboro Boro": "https://goldsboropa.com/document-library-2/",
    "Jacobus Boro": "https://jacobuspa.com/council-meeting/council-meeting-minutes/",
    "Jefferson Boro": "https://jeffersonboro.net/council-minutes-agendas",
    "Mount Wolf Boro": "https://mtwolfpa.gov/agenda-minutes/",
    "New Freedom Boro": "https://newfreedomboro.org/2026-meeting-minutes/",
    "Red Lion Boro": "https://redlionpa.org/government/agendas-minutes/borough-council-agendas-minutes/",
    "Spring Grove Boro": "https://www.springgrovepa.gov/meeting-minutes",
    "Stewartstown Boro": "https://www.stewartstown.org/borough-government/",
    "Windsor Boro": "https://www.windsorboropa.com/agenda-minutes.html",
    "East Manchester Twp": "https://emanchestertwp.com/boards-and-committees/meetings-archive/",
    "Lower Chanceford Twp": "https://lowerchancefordtwppa.gov/meetings.php",
    "West Manheim Twp": "https://westmanheimtwp.com/boards-comissions/board-of-supervisors/minutes/",
    "Warrington Twp": "https://warringtontownship.org/",
    "Felton Boro": "https://feltonboroughpa.com/documents/minutes/",
    "Dallastown Boro": "https://dallastownboro.com/meetings-agendas-minutes/",
    "North Codorus Twp": "https://northcodorustwp.org/board-of-supervisors-3/",
    "Loganville Boro": "https://loganvilleborough.com/",
}

# Compile all entries: BOS + ZHB + PC
all_entries = []

for name, bos_url in sorted(BOS_URLS.items()):
    ptype = "board_of_supervisors"
    if "Boro" in name:
        ptype = "borough_council"
    if "City" in name:
        ptype = "city_council"
    all_entries.append((f"{name} {ptype.replace('_', ' ').title()}", bos_url, ptype))

# Add ZHB entries from survey
for name, info in sorted(data.items()):
    if isinstance(info, dict) and info.get("zhb"):
        for link in info["zhb"][:1]:  # first link only
            url = link["url"]
            if url and "googleapis" not in url and "plugins" not in url:
                all_entries.append((f"{name} Zoning Hearing Board", url, "zoning_hearing"))

# Add PC entries from survey
for name, info in sorted(data.items()):
    if isinstance(info, dict) and info.get("pc"):
        for link in info["pc"][:1]:
            url = link["url"]
            if url and "googleapis" not in url and "plugins" not in url:
                all_entries.append((f"{name} Planning Commission", url, "planning_commission"))

# Add manual overrides
for name, committees in MANUAL_ENTRIES.items():
    for ctype, url in committees.items():
        label = f"{name} {ctype.replace('_', ' ').title()}"
        # Check if already in the list
        existing = [e for e in all_entries if e[0] == label]
        if not existing:
            all_entries.append((label, url, ctype))

# Sort and print
all_entries.sort(key=lambda x: (x[0], x[2]))

print(f"# Total entries: {len(all_entries)}")
print(f"# BOS/Council: {sum(1 for e in all_entries if e[2] in ('board_of_supervisors','borough_council','city_council','board_of_commissioners'))}")
print(f"# ZHB: {sum(1 for e in all_entries if e[2] == 'zoning_hearing')}")
print(f"# Planning: {sum(1 for e in all_entries if e[2] == 'planning_commission')}")
print()

print("municipality_websites=(")
for label, url, ptype in all_entries:
    print(f'    ("{label}", "{url}", "{ptype}"),')
print(")")

# Save
with open('/tmp/municipality_config_entries.py', 'w') as f:
    f.write("municipality_websites=(\n")
    for label, url, ptype in all_entries:
        f.write(f'    ("{label}", "{url}", "{ptype}"),\n')
    f.write(")\n")

print(f"\nSaved to /tmp/municipality_config_entries.py")
