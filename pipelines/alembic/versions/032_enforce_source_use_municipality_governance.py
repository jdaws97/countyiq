"""enforce source use and govern municipal proceedings per body

Revision ID: 032
Revises: 031
Create Date: 2026-08-27
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


_MUNICIPALITY_SOURCES = json.loads(r"""[
  {
    "source_key": "hanover_borough_council",
    "municipality_name": "HANOVER",
    "body_name": "Hanover Borough Council",
    "listing_url": "https://hanoverboroughpa.gov/AgendaCenter",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "monaghan_twp_board_of_supervisors",
    "municipality_name": "MONAGHAN TWP",
    "body_name": "Monaghan Twp Board of Supervisors",
    "listing_url": "https://monaghantownship.com/AgendaCenter",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "hallam_borough_council",
    "municipality_name": "HALLAM",
    "body_name": "Hallam Borough Council",
    "listing_url": "https://hallamborough.com/library/agendas-minutes",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "lewisberry_borough_council",
    "municipality_name": "LEWISBERRY",
    "body_name": "Lewisberry Borough Council",
    "listing_url": "https://lewisberryborough.org/residents/meeting-agendas-and-minutes/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "manchester_borough_council",
    "municipality_name": "MANCHESTER",
    "body_name": "Manchester Borough Council",
    "listing_url": "https://manchesterborough.gov/documents/meeting-minutes-agendas/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "new_salem_borough_council",
    "municipality_name": "NEW SALEM",
    "body_name": "New Salem Borough Council",
    "listing_url": "https://newsalemborough.org/government/agendas-minutes/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "york_haven_borough_council",
    "municipality_name": "YORK HAVEN",
    "body_name": "York Haven Borough Council",
    "listing_url": "https://yorkhavenborough.org/administration/borough-council-meeting-agendas-minutes/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "carroll_twp_board_of_supervisors",
    "municipality_name": "CARROLL TWP",
    "body_name": "Carroll Twp Board of Supervisors",
    "listing_url": "https://www.carrolltownship.com/bos-agenda-2024/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "codorus_twp_board_of_supervisors",
    "municipality_name": "CODORUS TWP",
    "body_name": "Codorus Twp Board of Supervisors",
    "listing_url": "https://codorustownship.org/meeting-minutes/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "conewago_twp_board_of_supervisors",
    "municipality_name": "CONEWAGO TWP",
    "body_name": "Conewago Twp Board of Supervisors",
    "listing_url": "https://www.conewagotwp.com/board-of-supervisors/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "dallastown_borough_council",
    "municipality_name": "DALLASTOWN",
    "body_name": "Dallastown Borough Council",
    "listing_url": "https://dallastownboro.com/meetings-agendas-minutes/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "dover_twp_board_of_supervisors",
    "municipality_name": "DOVER TWP",
    "body_name": "Dover Twp Board of Supervisors",
    "listing_url": "https://www.dovertownship.org/home/government/agendas-minutes/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "east_hopewell_twp_board_of_supervisors",
    "municipality_name": "EAST HOPEWELL TWP",
    "body_name": "East Hopewell Twp Board of Supervisors",
    "listing_url": "https://www.easthopewelltownshippa.gov/board-of-supervisors",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "east_manchester_twp_board_of_supervisors",
    "municipality_name": "EAST MANCHESTER TWP",
    "body_name": "East Manchester Twp Board of Supervisors",
    "listing_url": "https://emanchestertwp.com/boards-and-committees/meetings-archive/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "east_prospect_borough_council",
    "municipality_name": "EAST PROSPECT",
    "body_name": "East Prospect Borough Council",
    "listing_url": "https://www.eastprospectborough.com/minutes",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "fairview_twp_board_of_supervisors",
    "municipality_name": "FAIRVIEW TWP",
    "body_name": "Fairview Twp Board of Supervisors",
    "listing_url": "https://twp.fairview.pa.us/board-of-supervisors/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "fawn_grove_borough_council",
    "municipality_name": "FAWN GROVE",
    "body_name": "Fawn Grove Borough Council",
    "listing_url": "https://fawngroveborough.org/documents/council-meeting-minutes/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "fawn_twp_board_of_supervisors",
    "municipality_name": "FAWN TWP",
    "body_name": "Fawn Twp Board of Supervisors",
    "listing_url": "https://fawntwp.org/monthly-meeting-minutes/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "felton_borough_council",
    "municipality_name": "FELTON",
    "body_name": "Felton Borough Council",
    "listing_url": "https://feltonboroughpa.com/documents/minutes/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "franklin_twp_board_of_supervisors",
    "municipality_name": "FRANKLIN TWP",
    "body_name": "Franklin Twp Board of Supervisors",
    "listing_url": "https://franklintownship.org/meeting-minutes-agendas/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "goldsboro_borough_council",
    "municipality_name": "GOLDSBORO",
    "body_name": "Goldsboro Borough Council",
    "listing_url": "https://goldsboropa.com/document-library-2/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "hellam_twp_board_of_supervisors",
    "municipality_name": "HELLAM TWP",
    "body_name": "Hellam Twp Board of Supervisors",
    "listing_url": "https://www.hellamtownship.gov/departments/public-meetings/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "hopewell_twp_board_of_supervisors",
    "municipality_name": "HOPEWELL TWP",
    "body_name": "Hopewell Twp Board of Supervisors",
    "listing_url": "https://www.hopewelltownship.com/public-meetings/board-of-supervisors/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "jackson_twp_board_of_supervisors",
    "municipality_name": "JACKSON TWP",
    "body_name": "Jackson Twp Board of Supervisors",
    "listing_url": "https://jackson-township.org/meeting-agendas/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "manchester_twp_board_of_supervisors",
    "municipality_name": "MANCHESTER TWP",
    "body_name": "Manchester Twp Board of Supervisors",
    "listing_url": "https://www.mantwp.com/meetings-agendas/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "manheim_twp_board_of_supervisors",
    "municipality_name": "MANHEIM TWP",
    "body_name": "Manheim Twp Board of Supervisors",
    "listing_url": "https://www.manheimtwpyorkpa.org/index.php/government/minutes-agendas",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "north_codorus_twp_board_of_supervisors",
    "municipality_name": "NORTH CODORUS TWP",
    "body_name": "North Codorus Twp Board of Supervisors",
    "listing_url": "https://northcodorustwp.org/board-of-supervisors-3/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "north_york_borough_council",
    "municipality_name": "NORTH YORK",
    "body_name": "North York Borough Council",
    "listing_url": "https://northyorkborough.com/borough-council-meeting-minutes/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "paradise_twp_board_of_supervisors",
    "municipality_name": "PARADISE TWP",
    "body_name": "Paradise Twp Board of Supervisors",
    "listing_url": "https://paradisetownship.org/documents/board-of-supervisor-agenda-notices/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "peach_bottom_twp_board_of_supervisors",
    "municipality_name": "PEACH BOTTOM TWP",
    "body_name": "Peach Bottom Twp Board of Supervisors",
    "listing_url": "https://www.peachbottomtownship.org/meeting-minutes",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "penn_twp_board_of_supervisors",
    "municipality_name": "PENN TWP",
    "body_name": "Penn Twp Board of Supervisors",
    "listing_url": "https://penntownship.org/documents/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "red_lion_borough_council",
    "municipality_name": "RED LION",
    "body_name": "Red Lion Borough Council",
    "listing_url": "https://redlionpa.org/government/agendas-minutes/borough-council-agendas-minutes/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "seven_valleys_borough_council",
    "municipality_name": "SEVEN VALLEYS",
    "body_name": "Seven Valleys Borough Council",
    "listing_url": "https://sevenvalleysborough.com/minutes/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "shrewsbury_borough_council",
    "municipality_name": "SHREWSBURY",
    "body_name": "Shrewsbury Borough Council",
    "listing_url": "https://shrewsburyborough.org/minutes/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "spring_garden_twp_board_of_supervisors",
    "municipality_name": "SPRING GARDEN TWP",
    "body_name": "Spring Garden Twp Board of Supervisors",
    "listing_url": "https://www.springgardentwp.org/meeting-minutes/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "spring_grove_borough_council",
    "municipality_name": "SPRING GROVE",
    "body_name": "Spring Grove Borough Council",
    "listing_url": "https://www.springgrovepa.gov/meeting-minutes",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "springfield_twp_board_of_supervisors",
    "municipality_name": "SPRINGFIELD TWP",
    "body_name": "Springfield Twp Board of Supervisors",
    "listing_url": "https://springfieldyork.org/meeting-minutes/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "springettsbury_twp_board_of_supervisors",
    "municipality_name": "SPRINGETTSBURY TWP",
    "body_name": "Springettsbury Twp Board of Supervisors",
    "listing_url": "https://springettsbury.com/township-document-archives/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "wellsville_borough_council",
    "municipality_name": "WELLSVILLE",
    "body_name": "Wellsville Borough Council",
    "listing_url": "https://wellsvilleborough.com/boards-commissions/borough-council-agenda-budget/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "west_manchester_twp_board_of_supervisors",
    "municipality_name": "WEST MANCHESTER TWP",
    "body_name": "West Manchester Twp Board of Supervisors",
    "listing_url": "https://www.westmanchestertownship.com/boards-committees/board-of-supervisors/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "west_manheim_twp_board_of_supervisors",
    "municipality_name": "WEST MANHEIM TWP",
    "body_name": "West Manheim Twp Board of Supervisors",
    "listing_url": "https://westmanheimtwp.com/boards-comissions/board-of-supervisors/minutes/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "windsor_twp_board_of_supervisors",
    "municipality_name": "WINDSOR TWP",
    "body_name": "Windsor Twp Board of Supervisors",
    "listing_url": "https://windsortownship.com/events-minutes/board-of-trustees/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "wrightsville_borough_council",
    "municipality_name": "WRIGHTSVILLE",
    "body_name": "Wrightsville Borough Council",
    "listing_url": "https://wrightsvilleborough.com/meeting-minutes/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "yoe_borough_council",
    "municipality_name": "YOE",
    "body_name": "Yoe Borough Council",
    "listing_url": "https://yoeborough.org/information/minutes/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "yorkana_borough_council",
    "municipality_name": "YORKANA",
    "body_name": "Yorkana Borough Council",
    "listing_url": "https://yorkanaborough.com/meeting-minutes/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "york_city_council",
    "municipality_name": "YORK",
    "body_name": "York City Council",
    "listing_url": "https://www.yorkcity.org/government/city-council/meetings/",
    "proceeding_type": "city_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "york_twp_board_of_commissioners",
    "municipality_name": "YORK TWP",
    "body_name": "York Twp Board of Commissioners",
    "listing_url": "https://yorktownshippa.gov/boards/boc/",
    "proceeding_type": "board_of_commissioners",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "chanceford_twp_board_of_supervisors",
    "municipality_name": "CHANCEFORD TWP",
    "body_name": "Chanceford Twp Board of Supervisors",
    "listing_url": "https://www.chancefordtwp.com/Minutes.html",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "delta_borough_council",
    "municipality_name": "DELTA",
    "body_name": "Delta Borough Council",
    "listing_url": "https://www.deltaborough.us/current-meeting-minutes",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "dillsburg_borough_council",
    "municipality_name": "DILLSBURG",
    "body_name": "Dillsburg Borough Council",
    "listing_url": "https://dillsburg.com/minutes/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "dover_borough_council",
    "municipality_name": "DOVER",
    "body_name": "Dover Borough Council",
    "listing_url": "https://www.doverboroughpa.com/minutes.html",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "franklintown_borough_council",
    "municipality_name": "FRANKLINTOWN",
    "body_name": "Franklintown Borough Council",
    "listing_url": "https://franklintownborough.net/notices%2Fagendas%2Fminutes",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "glen_rock_borough_council",
    "municipality_name": "GLEN ROCK",
    "body_name": "Glen Rock Borough Council",
    "listing_url": "https://www.glenrockpa.org/borough-government/council-meeting-minutes-agendas/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "jacobus_borough_council",
    "municipality_name": "JACOBUS",
    "body_name": "Jacobus Borough Council",
    "listing_url": "https://jacobuspa.com/council-meeting/council-meeting-minutes/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "jefferson_borough_council",
    "municipality_name": "JEFFERSON",
    "body_name": "Jefferson Borough Council",
    "listing_url": "https://jeffersonboro.net/council-minutes-agendas",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "loganville_borough_council",
    "municipality_name": "LOGANVILLE",
    "body_name": "Loganville Borough Council",
    "listing_url": "https://loganvilleborough.com/loganville_borough_council",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "lower_chanceford_twp_board_of_supervisors",
    "municipality_name": "LOWER CHANCEFORD TWP",
    "body_name": "Lower Chanceford Twp Board of Supervisors",
    "listing_url": "https://lowerchancefordtwppa.gov/meetings.php",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "lower_windsor_twp_board_of_supervisors",
    "municipality_name": "LOWER WINDSOR TWP",
    "body_name": "Lower Windsor Twp Board of Supervisors",
    "listing_url": "https://www.lowerwindsor.com/board-of-supervisors/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "mount_wolf_borough_council",
    "municipality_name": "MOUNT WOLF",
    "body_name": "Mount Wolf Borough Council",
    "listing_url": "https://mtwolfpa.gov/agenda-minutes/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "newberry_twp_board_of_supervisors",
    "municipality_name": "NEWBERRY TWP",
    "body_name": "Newberry Twp Board of Supervisors",
    "listing_url": "https://newberrytwp.com/board-of-supervisors-info",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "new_freedom_borough_council",
    "municipality_name": "NEW FREEDOM",
    "body_name": "New Freedom Borough Council",
    "listing_url": "https://newfreedomboro.org/meeting-information/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "stewartstown_borough_council",
    "municipality_name": "STEWARTSTOWN",
    "body_name": "Stewartstown Borough Council",
    "listing_url": "https://www.stewartstown.org/borough-government/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "warrington_twp_board_of_supervisors",
    "municipality_name": "WARRINGTON TWP",
    "body_name": "Warrington Twp Board of Supervisors",
    "listing_url": "https://warringtontwp.org/index.php/board-of-supervisors-minutes-2026/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "windsor_borough_council",
    "municipality_name": "WINDSOR",
    "body_name": "Windsor Borough Council",
    "listing_url": "https://www.windsorboropa.com/agenda-minutes.html",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "heidelberg_twp_board_of_supervisors",
    "municipality_name": "HEIDELBERG TWP",
    "body_name": "Heidelberg Twp Board of Supervisors",
    "listing_url": "https://www.heidelbergtwpmunicipal.com/meeting-agendas-monthly-minutes/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "washington_twp_board_of_supervisors",
    "municipality_name": "WASHINGTON TWP",
    "body_name": "Washington Twp Board of Supervisors",
    "listing_url": "https://washingtontownshipyc.net/meeting-minutes",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "west_york_borough_council",
    "municipality_name": "WEST YORK",
    "body_name": "West York Borough Council",
    "listing_url": "https://www.westyorkpa.gov/borough-meeting-minutes/",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "winterstown_borough_council",
    "municipality_name": "WINTERSTOWN",
    "body_name": "Winterstown Borough Council",
    "listing_url": "https://www.winterstownborough.com/documents",
    "proceeding_type": "borough_council",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "north_hopewell_twp_board_of_supervisors",
    "municipality_name": "NORTH HOPEWELL TWP",
    "body_name": "North Hopewell Twp Board of Supervisors",
    "listing_url": "https://www.northhopewelltwp.com/",
    "proceeding_type": "board_of_supervisors",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "york_county_commissioners",
    "municipality_name": null,
    "body_name": "York County Commissioners",
    "listing_url": "https://yorkcountypa.gov/817/Meeting-Agendas-and-Minutes",
    "proceeding_type": "county_commissioners",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "carroll_twp_zoning_hearing_board",
    "municipality_name": "CARROLL TWP",
    "body_name": "Carroll Twp Zoning Hearing Board",
    "listing_url": "https://www.carrolltownship.com/zoning-hearing-board/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "conewago_twp_zoning_hearing_board",
    "municipality_name": "CONEWAGO TWP",
    "body_name": "Conewago Twp Zoning Hearing Board",
    "listing_url": "https://www.conewagotwp.com/2026-zoning-agendas-minutes/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "dover_twp_zoning_hearing_board",
    "municipality_name": "DOVER TWP",
    "body_name": "Dover Twp Zoning Hearing Board",
    "listing_url": "https://www.dovertownship.org/home/government/agendas-minutes/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "east_manchester_twp_zoning_hearing_board",
    "municipality_name": "EAST MANCHESTER TWP",
    "body_name": "East Manchester Twp Zoning Hearing Board",
    "listing_url": "https://emanchestertwp.com/boards-and-committees/zoning-hearing-board/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "fairview_twp_zoning_hearing_board",
    "municipality_name": "FAIRVIEW TWP",
    "body_name": "Fairview Twp Zoning Hearing Board",
    "listing_url": "https://twp.fairview.pa.us/zoning-hearing-board/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "goldsboro_boro_zoning_hearing_board",
    "municipality_name": "GOLDSBORO BORO",
    "body_name": "Goldsboro Boro Zoning Hearing Board",
    "listing_url": "https://goldsboropa.com/zoning-hearing-board/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "hanover_boro_zoning_hearing_board",
    "municipality_name": "HANOVER BORO",
    "body_name": "Hanover Boro Zoning Hearing Board",
    "listing_url": "https://hanoverboroughpa.gov/AgendaCenter/Zoning-Hearing-Board-11",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "heidelberg_twp_zoning_hearing_board",
    "municipality_name": "HEIDELBERG TWP",
    "body_name": "Heidelberg Twp Zoning Hearing Board",
    "listing_url": "https://www.heidelbergtwpmunicipal.com/meeting-agendas-monthly-minutes/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "hellam_twp_zoning_hearing_board",
    "municipality_name": "HELLAM TWP",
    "body_name": "Hellam Twp Zoning Hearing Board",
    "listing_url": "https://www.hellamtownship.gov/government/zoning-hearing-board/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "hopewell_twp_zoning_hearing_board",
    "municipality_name": "HOPEWELL TWP",
    "body_name": "Hopewell Twp Zoning Hearing Board",
    "listing_url": "https://www.hopewelltownship.com/public-meetings/zoning-hearing-board/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "north_codorus_twp_zoning_hearing_board",
    "municipality_name": "NORTH CODORUS TWP",
    "body_name": "North Codorus Twp Zoning Hearing Board",
    "listing_url": "https://northcodorustwp.org/zoning-hearing-board-2/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "paradise_twp_zoning_hearing_board",
    "municipality_name": "PARADISE TWP",
    "body_name": "Paradise Twp Zoning Hearing Board",
    "listing_url": "https://paradisetownship.org/documents/zoning-hearing-board-notices/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "peach_bottom_twp_zoning_hearing_board",
    "municipality_name": "PEACH BOTTOM TWP",
    "body_name": "Peach Bottom Twp Zoning Hearing Board",
    "listing_url": "https://www.peachbottomtownship.org/zoning-hearing-board",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "penn_twp_zoning_hearing_board",
    "municipality_name": "PENN TWP",
    "body_name": "Penn Twp Zoning Hearing Board",
    "listing_url": "https://penntownship.org/zoning-hearing-board/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "red_lion_boro_zoning_hearing_board",
    "municipality_name": "RED LION BORO",
    "body_name": "Red Lion Boro Zoning Hearing Board",
    "listing_url": "https://redlionpa.org/government/agendas-minutes/zoning-hearing-board-agendas/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "shrewsbury_twp_zoning_hearing_board",
    "municipality_name": "SHREWSBURY TWP",
    "body_name": "Shrewsbury Twp Zoning Hearing Board",
    "listing_url": "https://www.shrewsburytownship.org/government/zoning_hearing_board/hearing_notices.php",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "spring_garden_twp_zoning_hearing_board",
    "municipality_name": "SPRING GARDEN TWP",
    "body_name": "Spring Garden Twp Zoning Hearing Board",
    "listing_url": "https://www.springgardentwp.org/zoning-hearing-board/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "spring_grove_boro_zoning_hearing_board",
    "municipality_name": "SPRING GROVE BORO",
    "body_name": "Spring Grove Boro Zoning Hearing Board",
    "listing_url": "https://www.springgrovepa.gov/zoning-hearing",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "warrington_twp_zoning_hearing_board",
    "municipality_name": "WARRINGTON TWP",
    "body_name": "Warrington Twp Zoning Hearing Board",
    "listing_url": "https://warringtontwp.org/index.php/past-zoning-minutes/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "west_manchester_twp_zoning_hearing_board",
    "municipality_name": "WEST MANCHESTER TWP",
    "body_name": "West Manchester Twp Zoning Hearing Board",
    "listing_url": "https://www.westmanchestertownship.com/boards-committees/zoning-hearing-board/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "west_manheim_twp_zoning_hearing_board",
    "municipality_name": "WEST MANHEIM TWP",
    "body_name": "West Manheim Twp Zoning Hearing Board",
    "listing_url": "https://westmanheimtwp.com/boards-comissions/zoning-hearing-board/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "york_city_zoning_hearing_board",
    "municipality_name": "YORK CITY",
    "body_name": "York City Zoning Hearing Board",
    "listing_url": "https://www.yorkcity.org/government/authorities-boards-and-commissions/zoning-hearing-board/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "york_twp_zoning_hearing_board",
    "municipality_name": "YORK TWP",
    "body_name": "York Twp Zoning Hearing Board",
    "listing_url": "https://yorktownshippa.gov/ZHB",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "lower_windsor_twp_zoning_hearing_board",
    "municipality_name": "LOWER WINDSOR TWP",
    "body_name": "Lower Windsor Twp Zoning Hearing Board",
    "listing_url": "https://www.lowerwindsor.com/zoning-hearing-board/",
    "proceeding_type": "zoning_hearing",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "carroll_twp_planning_commission",
    "municipality_name": "CARROLL TWP",
    "body_name": "Carroll Twp Planning Commission",
    "listing_url": "https://www.carrolltownship.com/planning-commission/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "conewago_twp_planning_commission",
    "municipality_name": "CONEWAGO TWP",
    "body_name": "Conewago Twp Planning Commission",
    "listing_url": "https://www.conewagotwp.com/2026-planning-agendas-minutes/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "dover_twp_planning_commission",
    "municipality_name": "DOVER TWP",
    "body_name": "Dover Twp Planning Commission",
    "listing_url": "https://www.dovertownship.org/home/government/boards-commissions/planning-commission/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "east_hopewell_twp_planning_commission",
    "municipality_name": "EAST HOPEWELL TWP",
    "body_name": "East Hopewell Twp Planning Commission",
    "listing_url": "https://www.easthopewelltownshippa.gov/planning-commission",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "east_manchester_twp_planning_commission",
    "municipality_name": "EAST MANCHESTER TWP",
    "body_name": "East Manchester Twp Planning Commission",
    "listing_url": "https://emanchestertwp.com/boards-and-committees/planning-commission/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "fairview_twp_planning_commission",
    "municipality_name": "FAIRVIEW TWP",
    "body_name": "Fairview Twp Planning Commission",
    "listing_url": "https://twp.fairview.pa.us/planning-commission/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "franklin_twp_planning_commission",
    "municipality_name": "FRANKLIN TWP",
    "body_name": "Franklin Twp Planning Commission",
    "listing_url": "https://franklintownship.org/planning-commission-meeting-minutesagendas/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "goldsboro_boro_planning_commission",
    "municipality_name": "GOLDSBORO BORO",
    "body_name": "Goldsboro Boro Planning Commission",
    "listing_url": "https://goldsboropa.com/planning-commission/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "heidelberg_twp_planning_commission",
    "municipality_name": "HEIDELBERG TWP",
    "body_name": "Heidelberg Twp Planning Commission",
    "listing_url": "https://www.heidelbergtwpmunicipal.com/meeting-agendas-monthly-minutes/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "hanover_boro_planning_commission",
    "municipality_name": "HANOVER BORO",
    "body_name": "Hanover Boro Planning Commission",
    "listing_url": "https://hanoverboroughpa.gov/AgendaCenter/Planning-Commission-8",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "hellam_twp_planning_commission",
    "municipality_name": "HELLAM TWP",
    "body_name": "Hellam Twp Planning Commission",
    "listing_url": "https://www.hellamtownship.gov/planning-commission/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "hopewell_twp_planning_commission",
    "municipality_name": "HOPEWELL TWP",
    "body_name": "Hopewell Twp Planning Commission",
    "listing_url": "https://www.hopewelltownship.com/public-meetings/planning-commission-board/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "north_codorus_twp_planning_commission",
    "municipality_name": "NORTH CODORUS TWP",
    "body_name": "North Codorus Twp Planning Commission",
    "listing_url": "https://northcodorustwp.org/planning-commission-2/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "paradise_twp_planning_commission",
    "municipality_name": "PARADISE TWP",
    "body_name": "Paradise Twp Planning Commission",
    "listing_url": "https://paradisetownship.org/documents/planning-commission-agendas-minutes/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "penn_twp_planning_commission",
    "municipality_name": "PENN TWP",
    "body_name": "Penn Twp Planning Commission",
    "listing_url": "https://penntownship.org/documents/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "red_lion_boro_planning_commission",
    "municipality_name": "RED LION BORO",
    "body_name": "Red Lion Boro Planning Commission",
    "listing_url": "https://redlionpa.org/government/agendas-minutes/2023-planning-commission-agendas-minutes/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "spring_garden_twp_planning_commission",
    "municipality_name": "SPRING GARDEN TWP",
    "body_name": "Spring Garden Twp Planning Commission",
    "listing_url": "https://www.springgardentwp.org/planning-commission/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "spring_grove_boro_planning_commission",
    "municipality_name": "SPRING GROVE BORO",
    "body_name": "Spring Grove Boro Planning Commission",
    "listing_url": "https://www.springgrovepa.gov/planning-commissions",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "warrington_twp_planning_commission",
    "municipality_name": "WARRINGTON TWP",
    "body_name": "Warrington Twp Planning Commission",
    "listing_url": "https://warringtontwp.org/index.php/planning-commission-minutes-2026/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "west_manchester_twp_planning_commission",
    "municipality_name": "WEST MANCHESTER TWP",
    "body_name": "West Manchester Twp Planning Commission",
    "listing_url": "https://www.westmanchestertownship.com/boards-committees/planning-commission/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "west_manheim_twp_planning_commission",
    "municipality_name": "WEST MANHEIM TWP",
    "body_name": "West Manheim Twp Planning Commission",
    "listing_url": "https://westmanheimtwp.com/boards-comissions/planning-commision/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "windsor_twp_planning_commission",
    "municipality_name": "WINDSOR TWP",
    "body_name": "Windsor Twp Planning Commission",
    "listing_url": "https://windsortownship.com/events-minutes/planning-commission/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "york_city_planning_commission",
    "municipality_name": "YORK CITY",
    "body_name": "York City Planning Commission",
    "listing_url": "https://www.yorkcity.org/government/authorities-boards-and-commissions/planning-commission-board/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "york_twp_planning_commission",
    "municipality_name": "YORK TWP",
    "body_name": "York Twp Planning Commission",
    "listing_url": "https://yorktownshippa.gov/PC",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "lower_windsor_twp_planning_commission",
    "municipality_name": "LOWER WINDSOR TWP",
    "body_name": "Lower Windsor Twp Planning Commission",
    "listing_url": "https://www.lowerwindsor.com/planning-commission/",
    "proceeding_type": "planning_commission",
    "rights_status": "conditional",
    "terms_review_status": "not_found",
    "notes": "Official municipal or county proceedings page; no separate site terms located in the 2026-08-27 review."
  },
  {
    "source_key": "cross_roads_borough_council",
    "municipality_name": "CROSS ROADS BORO",
    "body_name": "Cross Roads Borough Council",
    "listing_url": null,
    "proceeding_type": "borough_council",
    "rights_status": "paused",
    "terms_review_status": "no_web_presence",
    "notes": "No confirmed official web presence; contact-only coverage gap recorded from the 2026 YCPC directory review."
  },
  {
    "source_key": "railroad_borough_council",
    "municipality_name": "RAILROAD BORO",
    "body_name": "Railroad Borough Council",
    "listing_url": null,
    "proceeding_type": "borough_council",
    "rights_status": "paused",
    "terms_review_status": "no_web_presence",
    "notes": "YCPC directory lists no website; contact-only coverage gap."
  },
  {
    "source_key": "shrewsbury_twp_board_of_supervisors",
    "municipality_name": "SHREWSBURY TWP",
    "body_name": "Shrewsbury Twp Board of Supervisors",
    "listing_url": null,
    "proceeding_type": "board_of_supervisors",
    "rights_status": "paused",
    "terms_review_status": "restricted",
    "notes": "Minutes are available only through eCode360; collection remains paused under the commercial-use restriction review."
  }
]""")

# The source snapshot predates the canonical YCPC suffix normalization used by
# the application.  Normalize council-only labels here so the seeded policies
# join to municipality boundary names just like ZHB and planning-board rows.
for _source in _MUNICIPALITY_SOURCES:
    if _source["municipality_name"] is None:
        continue
    _municipality_name = _source["municipality_name"].strip().upper()
    if _source[
        "proceeding_type"
    ] == "borough_council" and not _municipality_name.endswith(" BORO"):
        _municipality_name = f"{_municipality_name} BORO"
    elif _source[
        "proceeding_type"
    ] == "city_council" and not _municipality_name.endswith(" CITY"):
        _municipality_name = f"{_municipality_name} CITY"
    _source["municipality_name"] = _municipality_name


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO meta.source_rights (
            source_key, publisher, source_url, rights_status,
            acquisition_allowed, raw_retention_allowed,
            derived_product_allowed, person_level_display_allowed,
            raw_export_allowed, allowed_methods, reviewed_on, review_due_on,
            evidence, notes
        ) VALUES (
            'county_scout', 'Multiple publishers',
            'https://yorkcountypa.gov/', 'paused',
            FALSE, FALSE, FALSE, FALSE, FALSE, ARRAY[]::TEXT[],
            DATE '2026-08-27', DATE '2026-11-27',
            '{"basis":"dynamic crawler can follow and auto-promote unreviewed sources"}'::JSONB,
            'Paused until every seed and discovered-link class has robots, terms, retention, and promotion gates.'
        );

        CREATE TABLE meta.municipality_source_rights (
            source_key TEXT PRIMARY KEY,
            parent_source_key TEXT NOT NULL DEFAULT 'public_proceedings'
                REFERENCES meta.source_rights(source_key),
            municipality_name TEXT,
            body_name TEXT NOT NULL,
            listing_url TEXT,
            proceeding_type TEXT NOT NULL,
            rights_status TEXT NOT NULL
                CHECK (rights_status IN ('conditional', 'paused')),
            acquisition_allowed BOOLEAN NOT NULL DEFAULT FALSE,
            raw_retention_allowed BOOLEAN NOT NULL DEFAULT FALSE,
            derived_product_allowed BOOLEAN NOT NULL DEFAULT FALSE,
            person_level_display_allowed BOOLEAN NOT NULL DEFAULT FALSE,
            raw_export_allowed BOOLEAN NOT NULL DEFAULT FALSE,
            allowed_methods TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            terms_review_status TEXT NOT NULL
                CHECK (terms_review_status IN (
                    'reviewed', 'not_found', 'restricted', 'no_web_presence'
                )),
            terms_url TEXT,
            reviewed_on DATE NOT NULL,
            review_due_on DATE NOT NULL,
            evidence JSONB NOT NULL DEFAULT '{}'::JSONB,
            notes TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE UNIQUE INDEX idx_municipality_source_body_url
            ON meta.municipality_source_rights (body_name, listing_url)
            WHERE listing_url IS NOT NULL;
        CREATE INDEX idx_municipality_source_municipality
            ON meta.municipality_source_rights (municipality_name);

        CREATE TABLE meta.municipality_source_audit (
            id BIGSERIAL PRIMARY KEY,
            source_key TEXT NOT NULL
                REFERENCES meta.municipality_source_rights(source_key),
            asset_key TEXT NOT NULL,
            dagster_run_id TEXT,
            acquisition_method TEXT NOT NULL,
            allowed BOOLEAN NOT NULL,
            reason TEXT NOT NULL,
            checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_municipality_source_audit_checked
            ON meta.municipality_source_audit (source_key, checked_at DESC);

        CREATE TABLE meta.municipality_source_health (
            source_key TEXT PRIMARY KEY
                REFERENCES meta.municipality_source_rights(source_key),
            listing_status TEXT NOT NULL,
            robots_allowed BOOLEAN,
            robots_reason TEXT,
            http_status INTEGER,
            document_count INTEGER NOT NULL DEFAULT 0,
            checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_success_at TIMESTAMPTZ,
            last_error TEXT
        );

        CREATE OR REPLACE FUNCTION meta.prevent_source_audit_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $function$
        BEGIN
            RAISE EXCEPTION 'source audit ledgers are append-only';
        END;
        $function$;

        CREATE TRIGGER source_rights_audit_append_only
        BEFORE UPDATE OR DELETE ON meta.source_rights_audit
        FOR EACH ROW EXECUTE FUNCTION meta.prevent_source_audit_mutation();

        CREATE TRIGGER municipality_source_audit_append_only
        BEFORE UPDATE OR DELETE ON meta.municipality_source_audit
        FOR EACH ROW EXECUTE FUNCTION meta.prevent_source_audit_mutation();
        """
    )

    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO meta.municipality_source_rights (
                source_key, municipality_name, body_name, listing_url,
                proceeding_type, rights_status, acquisition_allowed,
                raw_retention_allowed, derived_product_allowed,
                person_level_display_allowed, raw_export_allowed,
                allowed_methods, terms_review_status, reviewed_on,
                review_due_on, evidence, notes
            )
            SELECT
                row.source_key,
                row.municipality_name,
                row.body_name,
                row.listing_url,
                row.proceeding_type,
                row.rights_status,
                row.rights_status = 'conditional',
                row.rights_status = 'conditional',
                row.rights_status = 'conditional',
                FALSE,
                FALSE,
                CASE WHEN row.rights_status = 'conditional'
                    THEN ARRAY['official_document_direct']::TEXT[]
                    ELSE ARRAY[]::TEXT[]
                END,
                row.terms_review_status,
                DATE '2026-08-27',
                DATE '2026-11-27',
                jsonb_build_object(
                    'basis', 'official public proceedings page',
                    'official_directory',
                    'https://www.ycpc.org/DocumentCenter/View/5089/2026-Directory-of-Public-Officials-PDF',
                    'terms_review', row.terms_review_status
                ),
                row.notes
            FROM jsonb_to_recordset(CAST(:payload AS jsonb)) AS row(
                source_key TEXT,
                municipality_name TEXT,
                body_name TEXT,
                listing_url TEXT,
                proceeding_type TEXT,
                rights_status TEXT,
                terms_review_status TEXT,
                notes TEXT
            )
            """
        ),
        {"payload": json.dumps(_MUNICIPALITY_SOURCES)},
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS source_rights_audit_append_only
            ON meta.source_rights_audit;
        DELETE FROM meta.source_rights_audit WHERE source_key = 'county_scout';
        DELETE FROM meta.source_rights WHERE source_key = 'county_scout';
        DROP TABLE IF EXISTS meta.municipality_source_health;
        DROP TABLE IF EXISTS meta.municipality_source_audit;
        DROP TABLE IF EXISTS meta.municipality_source_rights;
        DROP FUNCTION IF EXISTS meta.prevent_source_audit_mutation();
        """
    )
