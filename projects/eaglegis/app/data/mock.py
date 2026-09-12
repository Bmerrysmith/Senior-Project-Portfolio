"""
In-memory data store — seeded with real Estero, FL data exported from Supabase.

Sources:
  Locations  : "Supabase Snippet Cancelled_Rejection Meetings for 2024.csv"
  Documents  : "Supabase Snippet Cancelled_Rejection Meetings for 2024 (1).csv"

All coordinates are [longitude, latitude] per GeoJSON spec (EPSG:4326).

Swap strategy for Supabase/PostgreSQL:
  Replace MockStore methods with async DB queries.
  The routers and services call only these methods — nothing else changes.
"""
from copy import deepcopy
from datetime import date
from typing import Optional


# ---------------------------------------------------------------------------
# Meeting types
# ---------------------------------------------------------------------------

MEETING_TYPES: list[dict] = [
    {"type_id": 1, "type_name": "Village Council",                  "description": "Regular Village Council meeting"},
    {"type_id": 2, "type_name": "Planning Zoning & Design Board",   "description": "Combined planning, zoning, and design review board"},
    {"type_id": 3, "type_name": "Public Hearing",                   "description": "Public input sessions on proposed projects"},
    {"type_id": 4, "type_name": "Workshop",                         "description": "Informational workshops for Council and staff"},
]


# ---------------------------------------------------------------------------
# Projects  (project_ids match the locations export)
# ---------------------------------------------------------------------------

PROJECTS: list[dict] = [
    {
        "project_id": 1,
        "project_name": "BERT Rail Trail",
        "description": "Multi-use trail along the Bonita-Estero Regional Trail (BERT) corridor through the Village of Estero.",
        "start_year": 2021,
        "status": "Active",
    },
    {
        "project_id": 2,
        "project_name": "Septic to Sewer Conversion",
        "description": (
            "Utility extension project converting multiple Estero neighborhoods "
            "from septic systems to central sewer, including Estero Bay Village, "
            "Sunny Grove, Cypress Bend, and Broadway Avenue East."
        ),
        "start_year": 2021,
        "status": "Active",
    },
    {
        "project_id": 3,
        "project_name": "Corkscrew Road Widening",
        "description": "Corkscrew Road widening, intersection improvements, and traffic signal installations.",
        "start_year": 2021,
        "status": "Active",
    },
    {
        "project_id": 4,
        "project_name": "PZ&DB General Meeting Records",
        "description": "Administrative meeting records for the Village of Estero Planning, Zoning & Design Board.",
        "start_year": 2021,
        "status": "Active",
    },
]


# ---------------------------------------------------------------------------
# Locations — real geocoded data
# ---------------------------------------------------------------------------

LOCATIONS: list[dict] = [
    {
        "location_id": 1,
        "project_id": 1,
        "location_name": "BERT Rail Trail Corridor",
        "location_type": "Trail",
        "address": "Estero, FL 33928",
        "description": "Multi-use trail along the BERT corridor.",
        "latitude": 26.433900,
        "longitude": -81.815700,
    },
    {
        "location_id": 2,
        "project_id": 2,
        "location_name": "Estero Bay Village Septic Area",
        "location_type": "Infrastructure",
        "address": "Estero Bay Village, Estero FL",
        "description": "Septic to sewer conversion zone.",
        "latitude": 26.440800,
        "longitude": -81.822500,
    },
    {
        "location_id": 3,
        "project_id": 2,
        "location_name": "Sunny Grove Septic Area",
        "location_type": "Infrastructure",
        "address": "Sunny Grove, Estero FL",
        "description": "Septic to sewer conversion zone.",
        "latitude": 26.437600,
        "longitude": -81.812800,
    },
    {
        "location_id": 4,
        "project_id": 2,
        "location_name": "Cypress Bend Septic Area",
        "location_type": "Infrastructure",
        "address": "Cypress Bend, Estero FL",
        "description": "Septic to sewer conversion zone.",
        "latitude": 26.446900,
        "longitude": -81.811600,
    },
    {
        "location_id": 5,
        "project_id": 2,
        "location_name": "Broadway Avenue East UEP",
        "location_type": "Infrastructure",
        "address": "Broadway Ave East, Estero FL",
        "description": "Utility extension project area.",
        "latitude": 26.442000,
        "longitude": -81.805400,
    },
    {
        "location_id": 6,
        "project_id": 3,
        "location_name": "Corkscrew Road Widening Corridor",
        "location_type": "Road",
        "address": "Corkscrew Road, Estero FL",
        "description": "Corkscrew Road widening and improvements.",
        "latitude": 26.436300,
        "longitude": -81.770100,
    },
    {
        "location_id": 7,
        "project_id": 3,
        "location_name": "Corkscrew Rd / Puente Lane",
        "location_type": "Road",
        "address": "Corkscrew Rd at Puente Ln",
        "description": "Traffic signal and intersection improvements.",
        "latitude": 26.431200,
        "longitude": -81.784700,
    },
]


# ---------------------------------------------------------------------------
# Village Council meetings — from meetings table export (100 records)
# project_ids match the locations table; type_id=1 (Village Council)
# ---------------------------------------------------------------------------

COUNCIL_MEETINGS: list[dict] = [
    {"meeting_id": 1, "project_id": 2, "type_id": 1, "meeting_date": date.fromisoformat("2024-01-03"), "meeting_year": 2024, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "Adopted the Village of Estero Information Security Policy. Village | Accepted a payment of $30,000 from ProEnergy, LLC, in compromise of the Village’s code enforcement lien on the owner’s property at 8800 Corkscrew Road, and to authorize the Village Manager or his designee to file a release of lien once the payment has been made. Vote : (Roll Call) Aye: | Approved Contract EC 2024-07 with Johnson Engineering, Inc. to prepare the Village Wide Traffic Study for $249,480, approve a $25,000 contingency for additional services that may be required to complete the project, authorize the Village Manager to sign the contract and other additional implementing documents within the scope of the contract on behalf of the Village of Estero | Approve d contract EC 2024- 06 with Florida Acquisition Services to provide right -of-way acquisition services to the Village of Estero and authorize the Village Manager to sign the contract and other implementing documents within the scope of the contract on behalf of the Village of Estero | Approve d Change Order No. 1 in the amount of $8,500.00 to Contract EC 2022- 83 with National Water Main Cleaning Company for the gravity sewer line testing in the Estero Bay Village, Sunny Grove, and Cypress Bend mobile home developments, approve a 10% (of the total project cost) project contingency of $9,400, and authorize the Village Manager to Village", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "01032024 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 2, "project_id": 3, "type_id": 1, "meeting_date": date.fromisoformat("2024-01-03"), "meeting_year": 2024, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "Adopted the Village of Estero Information Security Policy. Village | Accepted a payment of $30,000 from ProEnergy, LLC, in compromise of the Village’s code enforcement lien on the owner’s property at 8800 Corkscrew Road, and to authorize the Village Manager or his designee to file a release of lien once the payment has been made. Vote : (Roll Call) Aye: | Approved Contract EC 2024-07 with Johnson Engineering, Inc. to prepare the Village Wide Traffic Study for $249,480, approve a $25,000 contingency for additional services that may be required to complete the project, authorize the Village Manager to sign the contract and other additional implementing documents within the scope of the contract on behalf of the Village of Estero | Approve d contract EC 2024- 06 with Florida Acquisition Services to provide right -of-way acquisition services to the Village of Estero and authorize the Village Manager to sign the contract and other implementing documents within the scope of the contract on behalf of the Village of Estero | Approve d Change Order No. 1 in the amount of $8,500.00 to Contract EC 2022- 83 with National Water Main Cleaning Company for the gravity sewer line testing in the Estero Bay Village, Sunny Grove, and Cypress Bend mobile home developments, approve a 10% (of the total project cost) project contingency of $9,400, and authorize the Village Manager to Village", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "01032024 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 3, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2016-06-08"), "meeting_year": 2016, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "12:53 PM", "action_taken": "Adopted Resolution No. 2017-02. | Adopted Resolution No. 2017-03 and approved the agreement between the Village and Pritchard Construction LLC as amended. | Approved the Traffic Signal Maintenance Agreement with Lee County | Passed first reading and set second reading and | Passed second reading and adopted Ordinance No. 2016-15. | Passed second reading and adopted Ordinance No. 2016-16.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "010417 Council Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 4, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2023-01-18"), "meeting_year": 2023, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "Approved Change Order #1 to Contract EC 2019- 36 in t he amount of $46,980 with Coastal Engineering Consultants, Inc. for additional work required to address environmental permit application questions from the Florida Department of Environmental Protection for the propos ed dredging of sediments from the Ester o River. | A ccept ed the Village’s portion of the Opiod Settlement in the amount of $14,400.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "01042023 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 5, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2016-01-20"), "meeting_year": 2016, "location": "Village of Estero Council Chambers", "start_time": "10:00 AM", "end_time": None, "action_taken": "Approved first reading of Ordinance No. 2016-01. | Adopted Resolution No. 2016-01. | Adopted Resolution No. 2016-02. | Adopted Resolution No. 2016-03. | No action required. 8.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "01062016 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 6, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2025-01-22"), "meeting_year": 2025, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:25 AM", "action_taken": "Approved award of Task Authorization 14 to Contract EC 2022- 38 to Johnson Engineering to provide water monitoring services for The Village of Estero for $193,411, approve a $19,000 contingency for additional services that may be required to complete the project, and authorize the Village Manager to sign the STA and other additional implementing documents within the scope of the STA on behalf of the Village of Estero | Passed first reading and schedule second reading for February 5, 2025 and the applica nt will provide us with additional information. Village | Passed first reading and schedule second reading for January 22, 2025.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "01082025 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 7, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2016-02-10"), "meeting_year": 2016, "location": "Village of Estero Council Chambers", "start_time": "2:01 PM", "end_time": None, "action_taken": "Directed Village Land Use Attorney Nancy Stroud to investigate the merits | Continued deliberations to 9:00 a.m. on January 20, 2016.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "01132016 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 8, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2021-01-13"), "meeting_year": 2021, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:03 AM", "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/SS", "filename": "01132021 Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 9, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2021-02-17"), "meeting_year": 2021, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:41 AM", "action_taken": "Approved to permit | Approved Ordinance 2021- 01.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "01202021 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 10, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2024-01-24"), "meeting_year": 2024, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "12:39 PM", "action_taken": "Approve d Interlocal Agreement for Election Services with the Supervisor of Elections. Village | Approved EC 2024- 10 in the amount of $151,440 for CW3 Engineering, Inc. to provide construction engineering and inspection services for the Estero on the River Phase 1 Improvements, approve a $15,000 contingency for additional services tha t may be required to complete the project and authorize the Village Manager to sign the contract and other additional implementing documents within the scope of the contract on behalf of the Village of Estero | Approve d EC 2024- 09 in the amount of $490,560.65 for HighSpans Engineering, Inc. to provide construction engineering and inspection services for the Sandy Lake Bike/Ped Improvements, approve a $49,000 contingency for additional services that may be required to complete the project, and authorize the Village Manager to sign the contract and other additional i mplementing documents within the scope of the contract on behalf of the Village of Estero | Adopted Resolution No. 2024- 02. Vote : (Roll Call) Aye: | Approve d Agreement of Purchase and Sale Agreement for the purchase of 20897 Three Oaks Parkway. Vote : (Roll Call) Aye: | Approve d Recreation Lease Agreement with the Lee County School Board . Vote : (Roll Call) Aye:", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "01242024 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 11, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2021-01-27"), "meeting_year": 2021, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "12:45 PM", "action_taken": "Approved to permit | Approved Resolution No. 2021- 01. Village | A dopted the Land Development Code Ordinance 2020- 10 and Official Zoning Map as amended in the “Addendum of Recommended Changes ” document dated January 19, 2021 as well as the addition of a sentence to Table 3- 405.C that states “A stand -alone car wash which has applied but has not been determined to be complete for an application for Development Order prior to January 27, 2021, and which submits a complete application for Development Order prior to April 27, 2021, a permitted use and not a special exception use shall apply.”", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "01272021 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 12, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2021-01-06"), "meeting_year": 2021, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "10:26 AM", "action_taken": "Estero Chamber of Commerce approval of financial support for Strategic Plans for Future Growth and Impact . | Passed first reading of Ordinance No. 2020- 11 and schedule second reading/ | Passed first reading of Ordinance No. 2021- 01 and schedule second reading/ | Approved m otion for a continuance until February 3 with the goal of making a final decision . | A dopted Ordinance 2020- 07.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/SS", "filename": "0162021 Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 13, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2023-02-15"), "meeting_year": 2023, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "Passed first reading of Zoning Ordinance 2023- 01 and set seco nd reading for February 15, 2023. Village", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "02012023 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 14, "project_id": 2, "type_id": 1, "meeting_date": date.fromisoformat("2022-02-16"), "meeting_year": 2022, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "Adopted Resolution No. 2022- 02. | Approve d the consultants ranking for Sandy Lane and Broadway East Bicycle/Pedestrian Improvements Pro ject as follows: Number Village | Approve d the consultants ranking for Broadway Avenue West Utilities Extension Project (UEP) as follows: Number 1 – Johnson Engineering, Inc.; Number 2 – Tetra Tech, Inc. ; Number 3 – CW3 Engineering, Inc.; Number 4 – JR Evans Engineering, P.A., and authorize | Approve d the consultants ranking for Broadway Avenue East Utilities Extension Project (UEP) as follows: Number 1 – Tetra Tech, Inc.; Number 2 – Johnson Engineering, Inc.; Number 3 – CW3 Engineering, Inc .; Number 4 – JR Evans Engineering, P.A., and authorize", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "02022022 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 15, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2025-02-19"), "meeting_year": 2025, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:08 AM", "action_taken": "Approved Resolution No. 2025- 01 to reappoint two (2) Planning, Zoning, and Design Board members for a one -year term. | Adopted Ordinance No. 2024- 14 with", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "02052025.pdf", "notes": None, "location_id": None},
    {"meeting_id": 16, "project_id": 3, "type_id": 1, "meeting_date": date.fromisoformat("2024-02-21"), "meeting_year": 2024, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "Approve d schedule for Planning Zoning and Design Board appointments. Village | Adopted Resolution No. 2024- 03. Vote : (Roll Call) Aye: | Approve d EC 2024- 06 STA - 02 in the amount of $47,200 for Florida Acquisition & Appraisal Inc. to provide easement acquisition services for the Sandy Lane Bike/Ped Improvements Project, approve a $4,700 contingency for additional services that may be required to complete the project, and authorize the Village Manager to sign the contract and other additional implementing documents within the scope of the contract on behalf of the Village of Estero | Approve d EC 2024- 06 STA -03 in the amount of $200,600 for Florida Acquisition & Appraisal Inc. to provide easement acquisition services for the River Ranch Road Improvements Project, approve a $20,000 contingency for additional services that may be required to complete the project, and authorize the Village Manager to sign the contract and other additional implementing documents within the scope of the contract on behalf of the Village of Estero | Approve d EC 2019- 66 STA -42 in the amount of $236,405 for P & T Lawn & Tractor Services, Inc. to install landscaping along US 41 from Williams Road to south of Estero Parkway, approve a $23,000 contingency for additional services that may be required to complete the project, and authorize the Village Manager to sign the contract and other additional implementing documents within the scope of the contract on Village | Approve d EC 2024- 06 STA - 01 in the amount of $59,000 for Florida Acquisition & Appraisal Inc. to provide easement acquisition services for the Corkscrew Road Pathway Improvements Project, approve a $5,900 contingency for additional services that may be required to complete the project, and authorize the Village Manager to sign the contract and other additional implementing documents within the scope of the contract on behalf of the Village of Estero", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "02072024 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 17, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2016-03-16"), "meeting_year": 2016, "location": "Village of Estero Council Chambers", "start_time": "10:00 AM", "end_time": None, "action_taken": "Appointed Robert King as Village CAC Representative to MPO. | Accepted the letter of resignation from Jeffrey Mass dated January 12, 2016 and directed the Village Clerk to advertise the vacancy and solicit applications. | Adopted Resolution 2016-05 as amended. | Authorized the Mayor to sign the letter and approved and endorsed the white paper entitled \"Caloosahatchee Watershed Regional Water Management Issues.\" | Adopted Resolution No. 2016-04.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "021016 Council Regular Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 18, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2022-02-16"), "meeting_year": 2022, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "Approve d the 2021- 2022 Interlocal Agreement between Village of Estero and Lee County for Stray Animal Control Services.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "02162022 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 19, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2024-02-21"), "meeting_year": 2024, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "10:50 AM", "action_taken": "Approve da perpetual sidewalk easement agreement with GL Homes to obtain an easement for the path along the River Creek Community and pay GL Homes $104,994.23 after they build the path using asphalt as the material, approve a $10,000 contingency for additional services that may be required to complete the project, and authorize the Village Manager to sign the sidewalk easement agreement and other additional implementing documents within the scope of the agreement on behalf of the Village of Estero | P assed first reading of Ordinance No. 2024- 03 and set second reading for March 6, 2024. Vote : (Roll Call) Aye:", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "02212024 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 20, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2021-02-24"), "meeting_year": 2021, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:14 AM", "action_taken": "Approve d Resolution No. 2021- 02 and authorize the Village to modify the Resolution if needed.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "02242021 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 21, "project_id": 3, "type_id": 1, "meeting_date": date.fromisoformat("2021-03-03"), "meeting_year": 2021, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:17 AM", "action_taken": "Approved to permit | Denied request to amend the zoning for the Estero Town Center CPD for a Firestone Complete Auto C are, and adopt Ordinance 2020- 09. | Approved the Williams Road Bicycle and Pedestrian Improvements – Concept Design contract with Banks Engineering under Supplemental Task Authorization (STA) – 01 Contract EC 2020- 56 Miscellaneous Professional Services to perform a suite of desi gn services for the Bicycle & Pedestrian improvements along Williams Road, betwe en US 41 and Village | Approved Ben Hill Griffin Parkway Preliminar y Landscape Design contracts with Bruce Howard and Associates under EC2020- 42 and RWA Engineering under EC2020- 67 to perform a suite of design services for the proposed landscape improvements along Ben Hill Griffin Parkway from Corkscrew Road to Estero Pa rkway, a pprove a 10% contingency for additional services that may be r equired to complete the project, and Authorize the Village Manager to sign the Supplemental Task Authorization (STA) and other additional implementing documents within the scope of the S TAs on behalf of the Village of Estero", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "0232021 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 22, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2023-03-15"), "meeting_year": 2023, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "A pprove s Supplemental Task Authorization (STA) -34 under contract EC 2019- 06 to P & T Lawn and Tractor Service, Inc. to construct and install a monument sign on US 41 at a total cost of $69,968, approve a contingency fund amount of $7,000 (an amount equal to 10% of the total project cost) to cover unforeseen circumstances which may occur, and authorize the Village Manager to execute the STA on behalf of the Village of Estero | A pproved Ordinance No. 2023 -02 the recommended changes made by the P lanning Zoning and Design Board. Village", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "03012023 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 23, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2024-03-20"), "meeting_year": 2024, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:45 AM", "action_taken": "Approve d EC 2024- 26 in the amount of $1,967,667 for Hellas Construction, Inc. to install artificial turf on The Jeff Sommer Stadium football field, approve a $197,000 contingency for additional services that may be required to complete the project, and authorize the Village Manager to sign the contract and other additional implementing documents within the scope of the contract on behalf of the Village of Estero | A pprove d the attached Professional Services agreement with Vieste, LLC. | P assed first reading of Ordinance No. 2024- 01 and set second reading for March 20, 2024. | P assed first reading of Ordinance No. 2024- 02 and set second reading for March 20, 2024. | P assed first reading of Ordinance No. 2024- 04 and set second reading for March 20, 2024. | A dopted Ordinance No. 2024- 03 subject to changing the word enforcement to compliance .", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "03062024 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 24, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2016-04-06"), "meeting_year": 2016, "location": "Village of Estero Council Chambers", "start_time": "10:00 AM", "end_time": None, "action_taken": "Approved continuing to a date certain, March 23, 2016.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "030916 Zoning Hearing Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 133, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-12-11"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "121115 Workshop Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 25, "project_id": 2, "type_id": 1, "meeting_date": date.fromisoformat("2022-04-06"), "meeting_year": 2022, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:12 AM", "action_taken": "Approved initiation of a rezoning and Comprehensive Plan Amendme nt for property south of Estero River, East of US 41 and north of Corkscrew Road . | Approve d the purchase of the 10- acre vacant parcel, commonly known as “River Oaks” at the east end of Broadway Avenue. | Approve d First Addendum to Peoples Gas System, Inc. “(TECO)” Franchise Agreement Ordinance 2021 -09. | Approve d the contract with Atkins North Amer ica to provide design and permitting services for the Sandy Lane and Broadway East Bicycle/Pedestrian Improvements Project in the amount of $671,513.25, approve a contingency fund amount of $67,000 (an amount equal to 10% of the total project cost) to cove r unforeseen circumstances which may occur, and authorize the Vi llage Manager to execute t he contract with Atkins North America and Village", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "03162022 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 26, "project_id": 3, "type_id": 1, "meeting_date": date.fromisoformat("2022-04-06"), "meeting_year": 2022, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:12 AM", "action_taken": "Approved initiation of a rezoning and Comprehensive Plan Amendme nt for property south of Estero River, East of US 41 and north of Corkscrew Road . | Approve d the purchase of the 10- acre vacant parcel, commonly known as “River Oaks” at the east end of Broadway Avenue. | Approve d First Addendum to Peoples Gas System, Inc. “(TECO)” Franchise Agreement Ordinance 2021 -09. | Approve d the contract with Atkins North Amer ica to provide design and permitting services for the Sandy Lane and Broadway East Bicycle/Pedestrian Improvements Project in the amount of $671,513.25, approve a contingency fund amount of $67,000 (an amount equal to 10% of the total project cost) to cove r unforeseen circumstances which may occur, and authorize the Vi llage Manager to execute t he contract with Atkins North America and Village", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "03162022 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 27, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-03-17"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "6:30 PM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "031715 Regular Meeting Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 28, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2021-03-24"), "meeting_year": 2021, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "10:26 AM", "action_taken": "Elected Vice Mayor Errington to be Mayor. Village | Approved Resolution 2021-04. | Authorized the M ayor to provide letters to our legislative deleg ation on several issues of local government preemption that are being considered by the legislature, one being building design standards preemption, the other being the comprehensive plan language in S enate Bill 284, and the language in House Bill 403, which is the home-based business preemption.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "03172021 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 29, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-03-20"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "032015 Workshop Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 30, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2024-04-03"), "meeting_year": 2024, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:19 AM", "action_taken": "Approve d EC 2023- 38 STA -02 in the amount of $203,782 for Hagerty Consulting, Inc. to assist the Village of Estero in preparing and submitting CDBG -DR Infrastructure Grant applications, approve a $20,000 contingency for additional services that may be required to complete the project, and authorize the Village Manager to sign the contract and other additional implementing documents within the scope of the contract on behalf of the Village of Estero | Approve d EC 2024- 27 Chris -Tel Construction Piggyback Agreement for Construction Manager at Risk services and to authorize the Village Manager to execute the agreement and any related documents or amendments as may be necessary. | Approve d EC 2024- 28 Manhattan Construction Piggyback Agreement for Construction Manager at Risk services and to authorize the Village Manager to execute the agreement and any related documents or amendments as may be necessary. | Adopted Ordinance No. 2024- 01. | Adopted Ordinance No. 2024- 02. | Adopted Ordinance No. 2024- 04.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "03202024 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 31, "project_id": 3, "type_id": 1, "meeting_date": date.fromisoformat("2016-04-20"), "meeting_year": 2016, "location": "Village of Estero Council Chambers", "start_time": "10:00 AM", "end_time": None, "action_taken": "Adopted Ordinance No. 2016-02 as amended. | Accepted all submissions, appointed the Village Manager, Finance | Accepted all submissions, appointed the Village Manager, Finance Director and Community Development Director as the interview committee, directed the committee to interview each firm (these would be posted and | Awarded the bid to ProAudio Services with the recommended add-ons. | Authorized the Village Manager to submit a letter to Lee County requesting support for traffic control for Bella Terra and Corkscrew Road, the sidewalk project on Estero Parkway, and resurfacing Estero Parkway. | Approved commencing", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "032316 Council Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 32, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-03-27"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "03272015 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 33, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2016-05-04"), "meeting_year": 2016, "location": "Village of Estero Council Chambers", "start_time": "10:00 AM", "end_time": None, "action_taken": "Passed first reading and transmittal of Ordinance No. 2016-04.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "033016 Council Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 34, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2025-04-16"), "meeting_year": 2025, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "10:55 AM", "action_taken": "Adopted Resolution No. 2025- 06. | A dopted the First Amendment . | A uthorized a deeper solicitation process to search for additional, complimentary sports, entertainment and recreational partners within the Village Center Hub . | A pprove d award of Contract EC 2022- 33 Change Order 01 to RWA Engineering to provide additional professional services to update design changes. Vote : (Roll Call) Aye: | A pprove d the BERT Memorandum of Agreement and to authorize the Village Manager to approve any minor revisions requested by the other partners to the agreement . | Approved Ordinance No. 2025-03 on First Reading and schedule Second Reading for April 16, 2025.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "04022025.pdf", "notes": None, "location_id": None},
    {"meeting_id": 35, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2024-04-17"), "meeting_year": 2024, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:19 AM", "action_taken": "Selected Al Paivandy, James E Tatooles, and Leonard E Scotty Wood III to a one -year term to the Planning, Zoning, and Design Board members, Dan Williams, Anthony Gargano, and Michael Sheeley to a three -year term to the Planning Zoning and Design Board and approve Resolution No. 2024- 04. Vote : (Roll Call) Aye: | Selected Anthony Gargano as Chairperson of the Planning Zoning and Design Board. | Approve d the Framework of Cooperation Between the Village of Estero and the Estero Forever Foundation. | Approve d EC 2024- 29 Wright Construction Group Piggyback Agreement for Construction Manager At Risk services and to authorize the Village Manager to execute the agreement and any related documents or amendments as may be necessary. | Approve d EC 2019- 66 STA -44 in the amount of $57,500 with P & T Lawn & Tractor to relocated twelve palm trees at Jeff Sommer Stadium, approve a $5,000 contingency for additional services that may be required to complete the project, and authorize the Village Manager to sign the contract and other additional implementing documents within the scope of the contract on behalf of the Village of Estero | Approved EC 2022-38 STA-13 in the amount of $175,486 with Johnson Engineering to perform construction site inspections for all projects within the Village of Estero, approve a $17,000 contingency for additional services that may be required to complete the project, authorize the Village Manager to sign the contract and other additional implementing documents within the scope of the contract on behalf of the Village of Estero", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "04032024 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 36, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2023-04-19"), "meeting_year": 2023, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "A dopted Resolution No. 2023- 07. Village | A dopted Resolution No. 2023- 08.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "04052023 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 37, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-04-06"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "040615 Regular Meeting Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 38, "project_id": 2, "type_id": 1, "meeting_date": date.fromisoformat("2022-04-20"), "meeting_year": 2022, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:10 AM", "action_taken": "Adopted Resolution 2022- 03 which approves the updated Multijurisdictional Program for | Approve d final P lat for Estero Crossing . | Approve d final Pla t for Rivercreek Phase One (formerly known as Corkscrew Crossing) . | Approve d Resolution No. 2022- 05 to purchase the 10- acre vacant parcel, commonly known as “River Oaks” at the east end of Broadway Avenue. | Approved Resolution No. 2022- 06 Commercial Contract for the Purchase of Real Estate from Gess Family Partnership + Gulf Coast Driving Range LLC, Located at 9000 Wi lliams Road, Estero, Florida . | Approved the following list of short -listed firms listed below. Delegate authority to", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "04062022 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 39, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-04-07"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "040715 Workshop Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 40, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2021-04-21"), "meeting_year": 2021, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "12:02 PM", "action_taken": "Approved Resolution 2021- 10. | Approved Resolution 2021- 12. | Approve d award of Request for Bids No. RFB 2021- 02, US 41 Landscape Improvements Broadway East to Vintage Parkway and Coconut Road to Fountain Lakes Boulevard to P & T Lawn and Tractor Service, Inc. at a Grand Total Cost of $118,075, ap prove a contingency fund amount of $11,800 (an amount equal to 10% of the total project cost) to cover unforeseen circumstances which may occur, and a uthorize the Village Manager to execute the contract and any other related ancillary documents on behalf of the Village of Estero Counci l. | Approve d award of Supplemental Task Authorization ( STA) – 02 Contract EC 2020- 61 to KCA under the Village’s Misc. Service Contract CN 2020- 01 in the amount of $469,099, approve a contingency fund amount of $47,000 (an amount equal to 10% of the total project cost) to cover unforesee n circumstances which ma y occur, and a uthorize the Village Manager to execute the STA and any other related ancillary documents on behalf of the Village of Estero | Approve d award of Supplemental Task Authorization (STA) 06 to Contract EC 2020- 48 to CW3 Engineering under the Village’s Misc. Service Contract CN 2 020-01 in the amount of $54,000, approve a contingency fund amount of $5,400 (an amount equal to 10% of the total project cost) to cover unforesee n circumstances which may occur, and a uthorize the Village Manager to execute the STA and any other related ancillary documents on behalf of the Village of Estero | Approve d award of Suppl emental Task Authorization 06 to Contract EC 2020- 32 to Johnson Engineering to provide water monitoring services for The Village of Estero for $41,352, a pprove a 10% contingency for additional services that may be required to complete the project, and a uthorize the Village Manger to sign the STA and other additional implementing documents within the scope of the STA on behalf of the Village of Estero", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "04072021 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 41, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-04-10"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "041015 Workshop Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 42, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2022-04-13"), "meeting_year": 2022, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "04132022 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 43, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-04-17"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "04172015 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 44, "project_id": 2, "type_id": 1, "meeting_date": date.fromisoformat("2024-05-01"), "meeting_year": 2024, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:03 AM", "action_taken": "Approved EC 2024- 06 STA -05 in the amount of $81,000 with Florida Acquisition & Appraisal, Inc. to assist the Village in obtaining easement and property required to construction the Broadway Ave East UEP Areas 2 & 3, approve a $8,100 contingency for additional services that may be required to complete the project, and authorize the Village Manager to sign the contract and other additional implementing documents within the scope of the contract on behalf of the Village of Estero | Approve d the Assignment and Amendment of the License Agreement for Sandy Lane Right of Way Occupation, Drainage Pipe Construction and Maintenance agreement with Seminole Gulf Railway and authorize the Village Manager to execute the agreement on behalf of the Village | Approve d continuance to May 1, 2024.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "04172024 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 45, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2023-05-03"), "meeting_year": 2023, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:25 AM", "action_taken": "Adopted Resolution No. 2023- 09. | A pproved the award of Supplemental Task authorization 04 to Contract EC 2023- 38 to Johnson Engineering, Inc. for the Phase 1 Estero Parkway Reuse Ma in Design, Permit and Grant Funding Assistance at a cost of $89,858.00, approve a $9,000 contingency (10%) for additional services that may be required to complete the project, and authorize the Village Manager to sign the STA and other additional impleme nting documents within the scope of the STA on behalf of the Village of Estero | Approv ed the consultants ranking f or Williams Road Widening Preliminary Design and Engineering P roject as follows: Number 1 – Kisinger Campo & Associates; Number 2 – Village | Approv ed the revised Hagerty Consulting, Inc. contract and a uthorize the Village Manager to execute the contract document on behalf of the Village of Estero", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "04192023  minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 46, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2016-05-18"), "meeting_year": 2016, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "Accepted Roger Strelow's resignation, with thanks from the", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "042016 Council Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 47, "project_id": 3, "type_id": 1, "meeting_date": date.fromisoformat("2022-04-20"), "meeting_year": 2022, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "Adopted Resolution No. 2022- 08 to purchas e the 10 -acre vacant parcel, commonly known as “River Oaks” at the east end of Broadway Avenue. | Amendme nt One to Contract No. EC 2020- 31 for Estero on the River Structure Demolition and updating contract to keep structure #6, the bomb shelter . | Approve d the contract EC 2020- 48 STA 10 with CW3 Engineering to provide de sign and permitting services for the Williams Road Bicycle/Pedestrian Improvements Project in the amount of $358,790, approve a contingency fund amount of $36,000 (an amount equal to 10% of the total project cost) to cover unforeseen circumstances which ma y occur, and authorize the Vill age Manager to execute the contract with CW3 Engineering and any other related ancillary documents on behalf of the Village | Approve d Ben Hill Griffin Parkway Improvements contracts with Bruce Howard and Associates under EC2020- 42 STA - 07 and CW3 Engineering under EC2020- 48 STA - 09 to perform landscape architecture and engineering ser vices for the proposed improvements along Ben Hill Griffin Parkway from Corkscrew Road to Estero Parkway.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "04202022 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 48, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-04-24"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "10:00 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "04242015 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 49, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2024-05-15"), "meeting_year": 2024, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "12:35 PM", "action_taken": "Approved Construction Manager at Risk agreement between Village of Estero and Manhattan Construction, Inc. for Williams Road and Atlantic Gulf Blvd Intersection Project and to authorize the Village Manager to execute the agreement and any related documents or amendments as may be necessary, except for the Guaranteed Maximum Price amendment, which will be approved by | Approve d Construction Manager at Risk agreement between Village of Estero and Chris -Tel Construction, Inc. for the Sandy Lane Bike/Ped Improvements Project and to authorize the Village Manager to execute the agreement with an effective date of July 1, 2024 and any related documents or amendments as may be necessary, except for the Guaranteed Maximum Price amendment, which will be approved by | Approve d of the attached Resolution will give credibility to the Village of Estero interest in this acquisition. It can also be used as the necessary financial match for Federal and State grants. | Adopted Resolution No. 2024- 07. | Approved Resolution No. 2024- 08 authorizing the Village Manager to perform various duties including accepting and authorizing CDBG -DR grants from HUD and administered by Lee County. | Approved Resolution No. 2024- 09 Excessive Force Policy.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "05012024 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 129, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2025-12-03"), "meeting_year": 2025, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "10:21 AM", "action_taken": "Adopted Resolution No. 2025- 27. | Adopted Resolution No. 2025- 28. | Adopted Resolution No 2025- 24 and authorize the Village Manager to execute the related Interlocal Agreement with the Lee County Property Appraiser to administer the assessment process. | Adopted Resolution No. 2025- 25 and authorize the Village Manager to execute the related Interlocal Agreement with the Lee County Property Appraiser to administer the assessment process. | Adopted Ordinance No. 2025- 16 on first reading and to schedule a second reading and | Adopted Ordinance No. 2025- 13.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "12032025.pdf", "notes": None, "location_id": None},
    {"meeting_id": 50, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2022-05-04"), "meeting_year": 2022, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "10:57 AM", "action_taken": "Approve Misc. Contractor Services contract EC 2019- 66 STA 21 with P & T Lawn & Tractor Services for $109,872 to replace trees along US 41 and provide additional landscape maintenance work on medians 22- 24, approve a contingency fund amount of $11,000 (an amount equal to 10% of the total project cost) to cover unforeseen circumstances which may occur, and authorize the Village Manager to execu te the contract documents on behalf of the Village of Estero | Approve d Misc. Contractor Services contract EC 2019 -59 STA 08 with Cougar Contracting, LLC for $52,815 for the repair of sidewalks along Vi a Coconut Point and Williams Road, approve a contingency fund amount of $5,300 (an amount e qual to 10% of the total project cost) to cover unforeseen circumstances which may occur, and authorize the Village Manager to execute the contract documents on beha lf of the Village of Estero | Approve d Resolution No. 2022- 07 which a mends Resolution No. 2015- 68. | Passed first reading of Ordinance 2022- 02 and set second reading for May 18, 2022.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "05042022 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 51, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2025-05-21"), "meeting_year": 2025, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "12:36 PM", "action_taken": "Approve d send ing notification letter and affidavit signed by Mayor to Florida Department of Commerce . | Approved the award of Contract 25035 with LandDesign, Inc. to prepare the Village of Estero Eco -Historic planning study for $430,000, approve a $43,000 contingency for additional services that may be required to complete the project, and authorize the Village Manager to sign the contract and other additional implementing documents within the scope of the contract on behalf of the Village of Estero | Approved the award of landscaping, mowing and irrigation services for Village roadways for P & T Lawn & Tractor, for an amount not to exceed $2,896,517.52 annually, approve a $200,000 Contingency for additional services that may be required to complete the project, and authorize the Village Manager to sign the purchase order and other additional implementing documents on behalf of the Village of Estero | Approve d awards of landscaping, mowing and irrigation services for Village roadways for Mainscape, Inc., in an amount not to exceed $1,432,600 annually, and to P & T Lawn & Tractor, for an amount not to exceed $581,107 annually. Vote : (Roll Call) Aye: | Approve d GMP Addendum 2 for contract EC 2024 – 12 CMAR for Wright Construction to complete the site work and utility installation for the Estero Entertainment Campus for $ 9,536,910 and authorize the Village Manager to sign the contract and other additional implementation documents within the scope of the GMP addendum on behalf of the Village of Estero", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "05072025.pdf", "notes": None, "location_id": None},
    {"meeting_id": 52, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-05-08"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "05082015 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 53, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2017-05-15"), "meeting_year": 2017, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "051517 Council Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 54, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-05-15"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "05152015 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 55, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2024-06-05"), "meeting_year": 2024, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "12:17 PM", "action_taken": "Approved Resolution No. 2024- 05. Vote : (Roll Call) Aye: | Approve d the Village Manager to execute the High- 5 | Approve d that Wright Construction Group is granted a Notice to Proceed on their phase 1 construction costs based on GMP#1. | Passed First Reading of Ordinance No. 2024-06 and set second reading for June 5, 2024.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "05152024 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 56, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2017-05-17"), "meeting_year": 2017, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "051717 Council Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 57, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2023-06-07"), "meeting_year": 2023, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "Pass ed second reading of Ordinance No. 2023- 05. Village", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "05172023  minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 58, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2016-06-01"), "meeting_year": 2016, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "Adopted Ordinance No. 2016-05, amending the Commercial Planned Development Zoning Resolution No. Z-09-037, Section 2.B, as revised by including a statement that this approval is unique to this particular petition and is not to be considered a precedent in other matters. | Approved first reading of Ordinance No. 2016-06 and advanced to second reading and | Adopted Resolution No. 2016-10 establishing a Village Credit Card Account with SunTrust. | Awarded RFP 2016-01 -Village Traffic Study to Kimley-Horn and authorized the Village Manager, with the assistance of | Approved the letter of support to be sent to Office of Environmental Services Division of State Lands, Department of Environmental Protection as revised with the language suggested by Mayor Batos. | No one on the", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "051816 Council Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 59, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2022-05-18"), "meeting_year": 2022, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "Meeting Cancelled", "status": "Cancelled", "approved_by_council_date": None, "doc_ref_code": None, "filename": "05182022 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 60, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2021-05-19"), "meeting_year": 2021, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:44 AM", "action_taken": "Approved the final plat.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "05192021 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 61, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-05-20"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "052015 Regular Meeting Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 62, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2016-05-24"), "meeting_year": 2016, "location": "Village of Estero Council Chambers", "start_time": "5:30 PM", "end_time": "7:32 PM", "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "052416 Council Workshop Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 63, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2021-05-26"), "meeting_year": 2021, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:55 AM", "action_taken": "Approved to permit | Approved the first reading of the ordinance and to transmit the Comprehensive Plan Amendment request to the State reviewing agencies with", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "05262021 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 64, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2016-08-17"), "meeting_year": 2016, "location": "Village of Estero Council Chambers", "start_time": "9:31 AM", "end_time": "10:50 AM", "action_taken": "Approved Ordinance No. 2016-06. | Approved Ordinance No. 2016-06. | Approved first reading of Ordinance No. 2016-07 and advanced to second reading and | Adopted Resolution No. 2016-11. | Adopted Resolution No. 2016-12. | Adopted Resolution No. 2016-13.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "060116 Council Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 65, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2022-06-01"), "meeting_year": 2022, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "Approve da Joint Resolution with Lee County for participation in CDBG and related Programs, authorize Mayor to sign and forward to Lee County. | Approved t erminat ion as of June 1, 2022, CN 2020- 01 Miscellaneous Professional Services to allow for the immediate use of the firms approved under CN 2022- 06. | Approved the recommendation of t he evaluation committee to select all 36 consulting firms that submitted Letters of Interest under CN 2022- 06, for a contract period of three (3) years (with the option at | Authorize d the Village Manager to execute agreements for individual pr ojects as needed at or below $50,000 (contracts in excess of $50,000 will require Village | Passed Ordinance 2022- 03.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "06012022 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 130, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2024-12-18"), "meeting_year": 2024, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:19 AM", "action_taken": "Approved the final Sports Park Master Plan . | Approved m otion to accept the Standard & Poor’s General Obligation Bond Rating for the Village of Estero.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "12042024 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 134, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2023-12-13"), "meeting_year": 2023, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "Affirm ed the decision of the Planning Zoning & Design Board to issue the development order , including the conditions that have been set fo rth therein.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "12132023 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 135, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-12-16"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "121615 Regular Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 66, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2021-06-16"), "meeting_year": 2021, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:26 AM", "action_taken": "Approved award of Supplemental Task Authorization (STA) – 04 Contract EC 2020- 42 to Bruce Howard & Associates under the Village’s Misc. Service Contract CN 2020- 01 in the amount of $60,000, approve award of Supplement al Task Authorization (STA) – 03 Contract EC 2020- 67 to RWA Engineering under the Village’s Misc. Service Contract CN 2020 -01 in the amount of $11,700, approve a contingency fund amount of $7,200 (an amount equal to 10% of the total project cost) to cover unforeseen circumstances which may occur, and authorize the Village Manager to execute the Supplemental Task Authorization and any other related ancillary documents on behalf of the Village of Estero | Approved the selection of Provion Inc. as the consultant of record under Request for Information No. RFI 2020- 02 Community Development Software Consultant and authorize the Village Manager to negotiate and execute a contract on behalf of the Village of Estero | Approved the | A uthorize d the | P assed first reading of Ordinance 2021 -04 and set second reading for June 16, 2021. | P assed first reading of Ordinance 2021 -08 and set second reading for June 16, 2021.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "06022021 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 67, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-06-03"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "060315 Regular Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 68, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2025-06-18"), "meeting_year": 2025, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "7:10 PM", "action_taken": "Passed first reading of Ordinance No. 2025- 05 and set second reading for June 18, 2025. | Passed first reading of Ordinance No. 2025- 04 and set second reading for July 2, 2025. | Passed first reading of Ordinance No. 2025- 06 and Set | Passed first reading of Ordinance No. 2025- 08 and Set | A pproved continuance to July 2 , 2025 for Condition 10 only.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "06042025.pdf", "notes": None, "location_id": None},
    {"meeting_id": 69, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2024-06-19"), "meeting_year": 2024, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:35 AM", "action_taken": "Approved the ranking of construction management firms for RFP 2024- 04 as 1- Wright Construction and a uthorize Village | Approve d the ranking of construction management firms for RFP 2024- 02 as recommended by the Village of Estero’s selection committee. 1-Manhattan Construction, 2- Wright Construction, 3- Chris Tel Construction, 4- Seagate Development Group, 5 Brooks & Freund, and authorize Village | Approve d the ranking of construction management firms for RFP 2024- 03 as recommended by the Village’s selection committee. 1 – Wright Construction, 2 – AIM Construction, 3 – Chris Tel Construction, 4 – American Infrastructure Services, and authorize Village | Passed first reading and schedule second reading for June 19, 2024. | Passed Second Reading of Ordinance No. 2024- 06.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "06052024 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 70, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2023-06-21"), "meeting_year": 2023, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:24 AM", "action_taken": "Approved Village | Approved Supplemental | Pass ed First Reading of Ordinance 2023 -04 and set | M oved Capital Improvement Hearing and Resolution 2023- 11 on to second", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "06072023  minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 71, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2022-06-15"), "meeting_year": 2022, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "1:46 PM", "action_taken": "Approve d the contract with N. Harris Computer Corporation to provide “CityView” software for Community Development for an estimated cost of $397,379, approve a contingency fund amount of $49,153 (an amount equal to 15% of the total project cost minus annual fees) to cover unforeseen circumstances which may occur, and authorize the Village Manager to execute the contract including revisions resulting from fi nal negotiations and related documents including annual renewal (maintenance) fee on behalf of the | Approved Resolution No. 2022- 11. | Approved Resolution No. 2022- 17. Village | Passed first reading of Ordinance No. 2022- 04 and set second reading for July 6, 2022. | P assed Ordinance No. 2022- 02.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "06152022 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 72, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-06-17"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "061715 Regular Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 73, "project_id": 3, "type_id": 1, "meeting_date": date.fromisoformat("2023-06-21"), "meeting_year": 2023, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "12:40 PM", "action_taken": "Approved STA 02 to Contract EC 2022- 29 with Weston & Sampson to design and permit the extension of utilities to Cypress Park Circle for $311,650, approve a $31,000 contingency (10%) for additional services that may be required to complete the project, and authorize the Village Village | Approved award of Request for Bi ds No. RFB 2023- 04, 8801 Corkscrew Road Structure Demolition to Southwest Builders Inc. to demolish the structure located at 8801 Corkscrew Road at a grand total cost of $106,890, approve a contingency fund amount of $10,689 (an amount equal to 10% of t he total project cost) to cover unforeseen circumstances which may occur , and authorize the Village Manager to execute the contract documents on behalf of the Village of Estero | Approved award Contract EC 2021- 04 Amendment 5 to replace p lant materials along Estero Parkway and authorize the Village Manager to sign the contract amendment and other additional implementing documents within the scope of the contract amendment on behalf of the Village of E stero | Approved award Amendment 1 to Contract EC 2023- 21 to mulch all debris and downed trees located at 8801 Corkscrew Road for $11,886.89 and authorize the Village Manager to sign the contract amendment and other additional implementing docume nts within the scope of the contr act amendment on behalf of the Village of Estero | Approved the software as a service agreement (SaaS) for Munis ERP software between the Village of Estero and Tyler Technologies, Inc. and authorized the Vi llage Manager to execute the contract documents on behalf of the Village of Estero | Approved STA 01 to Contract EC 2022- 33 with RWA Engineering to design and permit the Estero Entertainment District for $4 85,045, subject to the consultant’s acceptance of a revised Exhibit “C” (Project Schedule) to meet the time constrain ts of the Village, to au thorize the Village Manager to sign the STA and other additional implementing documents within the scope of the STA on behalf of the Village of Estero", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "06212023  minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 74, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-06-24"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "062415 Workshop Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 75, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-06-26"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "062615 Special Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 76, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-07-01"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "070115 Regular Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 77, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2025-07-02"), "meeting_year": 2025, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "10:50 AM", "action_taken": "Adopt ed Resolution No. 2025-10. | Adopt ed Resolution No. 2025-11. | Passed first reading of Ordinance No. 2025-07 and set second reading and", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "07022025.pdf", "notes": None, "location_id": None},
    {"meeting_id": 78, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2024-09-11"), "meeting_year": 2024, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "12:08 PM", "action_taken": "Adopted Resolution No. 2024- 12. Vote : (Roll Call) Aye: | Adopted Resolution No. 2024- 13. | Adopted Resolution No. 2024- 15. Village | Approve d award of Invitation to Bid 100124, Disaster Debris Monitoring Services for the Village of Estero to the apparent low bidder, Disaster Program Operations, Inc. to provide on- call disaster debris monitoring services as provided in the contract for a one -year period, at the rates submitted on their bid, authorize the Village Manager to execute contract documents on behalf of the Village of Estero | Approve d award of Invitation to Bid 100224, Disaster Recovery Services for the Village of Estero to CrowderGulf Joint Venture, Inc. to provide on-call disaster recovery services as provided in the solicitation. Authorize the Village Manager to execute a contract document on behalf of the Village of Estero | Approve d EC Task Order in the amount of $188,921 for Hagerty Consulting, Inc. to assist the Village of Estero in CDBG -DR Recovery and Resiliency Planning Program Grant Management Support.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "07032024 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 136, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2026-01-21"), "meeting_year": 2026, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "Meeting Cancelled", "status": "Cancelled", "approved_by_council_date": None, "doc_ref_code": None, "filename": "12172025.pdf", "notes": None, "location_id": None},
    {"meeting_id": 137, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2019-01-09"), "meeting_year": 2019, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "2019-01-09 Council Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 138, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2019-01-23"), "meeting_year": 2019, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "2019-01-23 Council Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 139, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2019-01-30"), "meeting_year": 2019, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "2019-01-30 Council Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 79, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2023-07-05"), "meeting_year": 2023, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "3:16 PM", "action_taken": "Adopted Resoluti on No. 2023- 12. | Approved award of Suppleme ntal Task Authorization 06 to Contract EC 2022- 38 to Johnson Engineering to provide water monitoring services for The Village of Estero for $146,340, approve a $14,600 contingency for additional services that may be required to complete the project and authorize the Village Manager to sign the STA and other additional impleme nting documents within the scope of the STA on behalf of the Village of Estero | App roved of RFB 2023- 07, Sandy Lane Path Prefabricated Bridge to Contech Engine ered Solutions, LLC to provide the bridge as provided in the contract, at a grand total cost of $239,500, approve a contingency fund amount of $23,950 (an amount equal to 10% of the total project cost) to cover unforeseen circumstances which may occur, and authorize the Village Manager to execute the contract documents on behalf of the Village of Estero | Approved the STA 1 to Contract 2022- 32 with Tetra Tech, Inc. for the preparation of an engineering assessment of the existing roads and sidewalks maintained by the Village of Estero for $256,060, approve a $25,600 contingency (10%) for additional services that may be required to complete the project, and authorize the Village Manager to sign the STA and other additional implementing documents wi thin the scope of the STA on behalf of the Village of Estero | Approv ed the Seminole Gulf Railway license agreement and approve payment of $55,233.34 to Seminole Gulf Railway to secure the license agreement and authorize the Village Manager to execute the agreement on behalf of the Vi llage | Adopted Resolution No. 2023- 14.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "07052023  minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 80, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2022-07-06"), "meeting_year": 2022, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "12:55 PM", "action_taken": "Approve d Comprehensive Annual Financial Report | A dopted Resolution No. 2022- 20. | Adopted Resolution No. 2022- 18. | Passed first reading of Ordinance No. 2022- 05 with the map 2A-1 and set second reading for July 20, 2022. | Approved m otion to transmit Comprehensive Plan Amendment and Ordinance No. 2022- 06 to state review agency. | Passed Ordinance No. 2022- 07 on the first reading.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "07062022 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 81, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2021-07-07"), "meeting_year": 2021, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:25 AM", "action_taken": "M otion to permit | Approved Comprehensive Annual Financial Report. | A uthori zed the Village Manager to execute the attached three letters of engagement, or similarly priced alternatives, and other invoices related to these services. Village | A pprove d the lien mitigation request f rom Ms. Hernandez releasing any outstanding liens against the Property in exchange for payment of a reduced fine of $5,000.00 and $327.20 for administrative cost. | P assed first reading of Ordinance 2021 -09 and set second readi ng for July 21, 2021.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "07072021 minute.pdf", "notes": None, "location_id": None},
    {"meeting_id": 82, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-07-10"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "071015 Workshop Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 83, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-07-15"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "071515 Regular Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 84, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2022-09-08"), "meeting_year": 2022, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "10:49 AM", "action_taken": "Adopted Resolution No. 2022- 21. | Adopted Resolution No. 2022- 19. | P assed second reading of Ordinance No. 2022-05 with Map 2A-1 and ordinance shall take effect immediately upon adoption, for implementation for the next regular Village", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "07202022 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 85, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-07-22"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "072215 Workshop Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 86, "project_id": 3, "type_id": 1, "meeting_date": date.fromisoformat("2016-06-08"), "meeting_year": 2016, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "12:12pm", "action_taken": "Review proposed Budget for Fiscal Year 2020-2021 Financial Impact: The proposed budget will provide funding for the Fiscal Year 2020-2021 | Adopted Resolution No. 2020-13 | Approve Resolution 2020-12 Naming the Lee County Supervisor of Elections as the Village ofEstero's Qualifying Official and authority for the Village Manager to enter into the attached agreement with the Lee County Supervisor of Elections, which is an expansion of the existing interlocal agreement between the parties. | Approve the WCI/Lennar Transportation Impact Fee Credit Agreement between WCVLennar and the Village of Estero for the Pelican Colony Traffic Signal. Authorize the Mayor to execute this agreement on behalf of the Village ofEstero | Approved the WCI/Lennar Transportation Impact Fee Credit Agreement between WCI/Lennar and the Village ofEstero for the Pelican Colony Traffic Signal. Authorize the Mayor to execute this agreement on behalf of the Village ofEstero | Approved the Interlocal Agreement between Lee County and the Village of Estero for Corkscrew Road/Puente Lane Traffic Signal. Authorize the Mayor to execute this agreement on behalf of the Village ofEstero", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/SS", "filename": "07222020 Council Meeting Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 87, "project_id": 2, "type_id": 1, "meeting_date": date.fromisoformat("2023-07-26"), "meeting_year": 2023, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "9:47 AM", "action_taken": "Adopted Agreement to Transfer Ownership, Operation and Maintenance of the T&T Water Management System and Dedication and Conveyance of Related Roads and the Supplement to Agre ement to Transfer Ownership, Operation, and Maintenance of a Portion of the T&T Water Management System and for Dedication and Conveyance of Roads. | Approved a Sovereignty Submerged Lands easement with the Florida Department of Environmental Protection for the Sunny Groves force main and authorize the Village Mayor to sign the easement and any other associated documents on behalf of the Village.", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "07262023 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 88, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-08-10"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "081015 Regular Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 89, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2016-08-31"), "meeting_year": 2016, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": "11:55 AM", "action_taken": "Endorsed the revised Caloosahatchee Watershed Regional Water Management Issues White Paper, dated July 15, 2016, and authorized the Mayor to sign a letter indicating | Adopted Resolution No. 2016-23. | Approved the request for the Mayor to sign a letter of support for the Edward Byrne Memorial Justice Assistance Grant (JAG) | Approved the agreement between the Village ofEstero and LaRue Planning & Management Services, Inc. | Continued to next | Approved the agreement as amended, between the Village of Estero and Nancy Stroud of Lewis Stroud & Deutsch, PL, for continuing legal services related to land use matters, including legal assistance with the Comprehensive Plan", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "081716 Council Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 90, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2023-09-07"), "meeting_year": 2023, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "Approved Resolution 2023- 20 waiving the provision of SECTION 5, NUMBER 2 .", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": "td/CS", "filename": "08292023 minutes.pdf", "notes": None, "location_id": None},
    {"meeting_id": 91, "project_id": 1, "type_id": 1, "meeting_date": date.fromisoformat("2015-09-03"), "meeting_year": 2015, "location": "Village of Estero Council Chambers", "start_time": "9:30 AM", "end_time": None, "action_taken": "No action found", "status": "Accepted", "approved_by_council_date": None, "doc_ref_code": None, "filename": "090315 Regular Meeting Approved Minutes.pdf", "notes": None, "location_id": None},
]

# ---------------------------------------------------------------------------
# Meetings — derived from PZ&DB minutes export
# All are type_id=2 (Planning Zoning & Design Board), project_id=4
# ---------------------------------------------------------------------------

def _pzdb(mid: int, d: str, year: int, status: str) -> dict:
    """Build a PZ&DB meeting dict from minimal fields."""
    return {
        "meeting_id": mid,
        "project_id": 4,
        "type_id": 2,
        "meeting_date": date.fromisoformat(d),
        "meeting_year": year,
        "location": "Estero Village Hall, 9401 Corkscrew Palms Blvd",
        "start_time": "6:00 PM",
        "end_time": None,
        "action_taken": None,
        "status": status,
        "approved_by_council_date": None,
        "doc_ref_code": None,
        "filename": None,
        "notes": None,
        "location_id": None,
    }


PZDB_MEETINGS: list[dict] = [
    # 2026 — future placeholders
    _pzdb(169, "2026-12-08", 2026, "Pending"),
    _pzdb(168, "2026-11-10", 2026, "Pending"),
    _pzdb(167, "2026-10-13", 2026, "Pending"),
    _pzdb(166, "2026-09-08", 2026, "Pending"),
    _pzdb(165, "2026-08-11", 2026, "Pending"),
    _pzdb(164, "2026-07-14", 2026, "Pending"),
    _pzdb(163, "2026-06-09", 2026, "Pending"),
    _pzdb(162, "2026-05-12", 2026, "Pending"),
    _pzdb(161, "2026-04-14", 2026, "Pending"),
    _pzdb(160, "2026-03-10", 2026, "Pending"),
    _pzdb(159, "2026-02-10", 2026, "Pending"),
    _pzdb(158, "2026-01-13", 2026, "Pending"),
    # 2025 — minutes not yet uploaded
    _pzdb(181, "2025-12-09", 2025, "Pending"),
    _pzdb(180, "2025-11-18", 2025, "Pending"),
    _pzdb(179, "2025-10-14", 2025, "Pending"),
    _pzdb(178, "2025-09-09", 2025, "Pending"),
    _pzdb(177, "2025-08-12", 2025, "Pending"),
    _pzdb(176, "2025-07-08", 2025, "Pending"),
    _pzdb(175, "2025-06-10", 2025, "Pending"),
    _pzdb(174, "2025-05-13", 2025, "Pending"),
    _pzdb(173, "2025-04-08", 2025, "Pending"),
    _pzdb(172, "2025-03-11", 2025, "Pending"),
    _pzdb(171, "2025-02-11", 2025, "Pending"),
    _pzdb(170, "2025-01-14", 2025, "Pending"),
    # 2024 — accepted
    _pzdb(194, "2024-12-10", 2024, "Accepted"),
    _pzdb(193, "2024-11-12", 2024, "Accepted"),
    _pzdb(192, "2024-10-29", 2024, "Accepted"),
    _pzdb(191, "2024-10-08", 2024, "Accepted"),
    _pzdb(190, "2024-09-10", 2024, "Accepted"),
    _pzdb(189, "2024-08-13", 2024, "Accepted"),
    _pzdb(188, "2024-07-09", 2024, "Accepted"),
    _pzdb(187, "2024-06-11", 2024, "Accepted"),
    _pzdb(186, "2024-05-14", 2024, "Accepted"),
    _pzdb(185, "2024-04-09", 2024, "Accepted"),
    _pzdb(184, "2024-03-12", 2024, "Accepted"),
    _pzdb(183, "2024-02-13", 2024, "Accepted"),
    _pzdb(182, "2024-01-09", 2024, "Accepted"),
    # 2023 — accepted (URLs have spacing issue)
    _pzdb(208, "2023-12-12", 2023, "Accepted"),
    _pzdb(207, "2023-11-14", 2023, "Accepted"),
    _pzdb(206, "2023-10-10", 2023, "Accepted"),
    _pzdb(205, "2023-09-12", 2023, "Accepted"),
    _pzdb(204, "2023-08-22", 2023, "Accepted"),
    _pzdb(203, "2023-08-08", 2023, "Accepted"),
    _pzdb(202, "2023-07-25", 2023, "Accepted"),
    _pzdb(201, "2023-07-11", 2023, "Accepted"),
    _pzdb(200, "2023-06-13", 2023, "Accepted"),
    _pzdb(199, "2023-05-09", 2023, "Accepted"),
    _pzdb(198, "2023-04-11", 2023, "Accepted"),
    _pzdb(197, "2023-03-14", 2023, "Accepted"),
    _pzdb(196, "2023-02-21", 2023, "Accepted"),
    _pzdb(195, "2023-01-11", 2023, "Accepted"),
    # 2022 — accepted
    _pzdb(222, "2022-12-13", 2022, "Accepted"),
    _pzdb(221, "2022-11-08", 2022, "Accepted"),
    _pzdb(220, "2022-10-25", 2022, "Accepted"),
    _pzdb(219, "2022-10-11", 2022, "Accepted"),
    _pzdb(218, "2022-09-27", 2022, "Accepted"),
    _pzdb(217, "2022-09-13", 2022, "Accepted"),
    _pzdb(216, "2022-08-09", 2022, "Accepted"),
    _pzdb(215, "2022-07-12", 2022, "Accepted"),
    _pzdb(214, "2022-06-14", 2022, "Accepted"),
    _pzdb(213, "2022-05-10", 2022, "Accepted"),
    _pzdb(212, "2022-04-12", 2022, "Accepted"),
    _pzdb(211, "2022-03-08", 2022, "Accepted"),
    _pzdb(210, "2022-02-08", 2022, "Accepted"),
    _pzdb(209, "2022-01-11", 2022, "Accepted"),
    # 2021 — accepted
    _pzdb(233, "2021-12-14", 2021, "Accepted"),
    _pzdb(232, "2021-11-09", 2021, "Accepted"),
    _pzdb(231, "2021-10-12", 2021, "Accepted"),
    _pzdb(230, "2021-09-28", 2021, "Accepted"),
    _pzdb(229, "2021-09-14", 2021, "Accepted"),
    _pzdb(228, "2021-08-24", 2021, "Accepted"),
    _pzdb(227, "2021-08-10", 2021, "Accepted"),
    _pzdb(226, "2021-07-13", 2021, "Accepted"),
    _pzdb(225, "2021-06-08", 2021, "Accepted"),
    _pzdb(224, "2021-05-11", 2021, "Accepted"),
    _pzdb(223, "2021-04-20", 2021, "Accepted"),
]


MEETINGS: list[dict] = COUNCIL_MEETINGS + PZDB_MEETINGS

# ---------------------------------------------------------------------------
# Documents — PZ&DB meeting minutes with real file URLs
# document_id == meeting_id (1-to-1 in this dataset)
# link_status reflects URL accessibility at time of export
# ---------------------------------------------------------------------------

def _minutes(did: int, url: str, d: str, link_status: str) -> dict:
    """Build a meeting-minutes document dict."""
    date_obj = date.fromisoformat(d)
    return {
        "document_id": did,
        "meeting_id": did,
        "title": f"PZ&DB Meeting Minutes \u2014 {d}",
        "document_type": "Minutes",
        "file_name": url.split("/")[-1],
        "file_url": url,
        "upload_date": None,
        "notes": None,
        "doc_date": date_obj,
        "link_status": link_status,
    }


_FP  = "Future Placeholder"
_MNU = "Missing / Not Uploaded"
_WE  = "Working / Expected"
_BSI = "Broken (Spacing Issue)"

DOCUMENTS: list[dict] = [
    # 2026
    _minutes(169, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2026%20Minutes/PZDB/12082026%20PZDB%20Minutes.pdf",  "2026-12-08", _FP),
    _minutes(168, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2026%20Minutes/PZDB/11102026%20PZDB%20Minutes.pdf",  "2026-11-10", _FP),
    _minutes(167, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2026%20Minutes/PZDB/10132026%20PZDB%20Minutes.pdf",  "2026-10-13", _FP),
    _minutes(166, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2026%20Minutes/PZDB/09082026%20PZDB%20Minutes.pdf",  "2026-09-08", _FP),
    _minutes(165, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2026%20Minutes/PZDB/08112026%20PZDB%20Minutes.pdf",  "2026-08-11", _FP),
    _minutes(164, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2026%20Minutes/PZDB/07142026%20PZDB%20Minutes.pdf",  "2026-07-14", _FP),
    _minutes(163, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2026%20Minutes/PZDB/06092026%20PZDB%20Minutes.pdf",  "2026-06-09", _FP),
    _minutes(162, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2026%20Minutes/PZDB/05122026%20PZDB%20Minutes.pdf",  "2026-05-12", _FP),
    _minutes(161, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2026%20Minutes/PZDB/04142026%20PZDB%20Minutes.pdf",  "2026-04-14", _FP),
    _minutes(160, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2026%20Minutes/PZDB/03102026%20PZDB%20Minutes.pdf",  "2026-03-10", _FP),
    _minutes(159, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2026%20Minutes/PZDB/02102026%20PZDB%20Minutes.pdf",  "2026-02-10", _FP),
    _minutes(158, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2026%20Minutes/PZDB/01132026%20PZDB%20Minutes.pdf",  "2026-01-13", _FP),
    # 2025
    _minutes(181, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2025%20Minutes/PZDB/12092025%20PZDB%20Minutes.pdf",  "2025-12-09", _MNU),
    _minutes(180, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2025%20Minutes/PZDB/11182025%20PZDB%20Minutes.pdf",  "2025-11-18", _MNU),
    _minutes(179, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2025%20Minutes/PZDB/10142025%20PZDB%20Minutes.pdf",  "2025-10-14", _MNU),
    _minutes(178, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2025%20Minutes/PZDB/09092025%20PZDB%20Minutes.pdf",  "2025-09-09", _MNU),
    _minutes(177, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2025%20Minutes/PZDB/08122025%20PZDB%20Minutes.pdf",  "2025-08-12", _MNU),
    _minutes(176, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2025%20Minutes/PZDB/07082025%20PZDB%20Minutes.pdf",  "2025-07-08", _MNU),
    _minutes(175, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2025%20Minutes/PZDB/06102025%20PZDB%20Minutes.pdf",  "2025-06-10", _MNU),
    _minutes(174, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2025%20Minutes/PZDB/05132025%20PZDB%20Minutes.pdf",  "2025-05-13", _MNU),
    _minutes(173, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2025%20Minutes/PZDB/04082025%20PZDB%20Minutes.pdf",  "2025-04-08", _MNU),
    _minutes(172, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2025%20Minutes/PZDB/03112025%20PZDB%20Minutes.pdf",  "2025-03-11", _MNU),
    _minutes(171, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2025%20Minutes/PZDB/02112025%20PZDB%20Minutes.pdf",  "2025-02-11", _MNU),
    _minutes(170, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2025%20Minutes/PZDB/01142025%20PZDB%20Minutes.pdf",  "2025-01-14", _MNU),
    # 2024
    _minutes(194, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2024%20Minutes/PZDB/12102024%20PZDB%20Minutes.pdf",  "2024-12-10", _WE),
    _minutes(193, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2024%20Minutes/PZDB/11122024%20PZDB%20Minutes.pdf",  "2024-11-12", _WE),
    _minutes(192, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2024%20Minutes/PZDB/10292024%20PZDB%20Minutes.pdf",  "2024-10-29", _WE),
    _minutes(191, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2024%20Minutes/PZDB/10082024%20PZDB%20Minutes.pdf",  "2024-10-08", _WE),
    _minutes(190, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2024%20Minutes/PZDB/09102024%20PZDB%20Minutes.pdf",  "2024-09-10", _WE),
    _minutes(189, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2024%20Minutes/PZDB/08132024%20PZDB%20Minutes.pdf",  "2024-08-13", _WE),
    _minutes(188, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2024%20Minutes/PZDB/07092024%20PZDB%20Minutes.pdf",  "2024-07-09", _WE),
    _minutes(187, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2024%20Minutes/PZDB/06112024%20PZDB%20Minutes.pdf",  "2024-06-11", _WE),
    _minutes(186, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2024%20Minutes/PZDB/05142024%20PZDB%20Minutes.pdf",  "2024-05-14", _WE),
    _minutes(185, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2024%20Minutes/PZDB/04092024%20PZDB%20Minutes.pdf",  "2024-04-09", _WE),
    _minutes(184, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2024%20Minutes/PZDB/03122024%20PZDB%20Minutes.pdf",  "2024-03-12", _WE),
    _minutes(183, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2024%20Minutes/PZDB/02132024%20PZDB%20Minutes.pdf",  "2024-02-13", _WE),
    _minutes(182, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2024%20Minutes/PZDB/01092024%20PZDB%20Minutes.pdf",  "2024-01-09", _WE),
    # 2023 — spacing issue in URLs
    _minutes(208, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2023%20MINUTES/PZDB/12122023%20%20%20PZDB%20Minutes.pdf", "2023-12-12", _BSI),
    _minutes(207, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2023%20MINUTES/PZDB/11142023%20%20%20PZDB%20Minutes.pdf", "2023-11-14", _BSI),
    _minutes(206, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2023%20MINUTES/PZDB/10102023%20%20%20PZDB%20Minutes.pdf", "2023-10-10", _BSI),
    _minutes(205, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2023%20MINUTES/PZDB/09122023%20%20%20PZDB%20Minutes.pdf", "2023-09-12", _BSI),
    _minutes(204, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2023%20MINUTES/PZDB/08222023%20%20%20PZDB%20Minutes.pdf", "2023-08-22", _BSI),
    _minutes(203, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2023%20MINUTES/PZDB/08082023%20%20%20PZDB%20Minutes.pdf", "2023-08-08", _BSI),
    _minutes(202, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2023%20MINUTES/PZDB/07252023%20%20%20PZDB%20Minutes.pdf", "2023-07-25", _BSI),
    _minutes(201, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2023%20MINUTES/PZDB/07112023%20%20%20PZDB%20Minutes.pdf", "2023-07-11", _BSI),
    _minutes(200, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2023%20MINUTES/PZDB/06132023%20%20%20PZDB%20Minutes.pdf", "2023-06-13", _BSI),
    _minutes(199, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2023%20MINUTES/PZDB/05092023%20%20%20PZDB%20Minutes.pdf", "2023-05-09", _BSI),
    _minutes(198, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2023%20MINUTES/PZDB/04112023%20%20%20PZDB%20Minutes.pdf", "2023-04-11", _BSI),
    _minutes(197, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2023%20MINUTES/PZDB/03142023%20%20%20PZDB%20Minutes.pdf", "2023-03-14", _BSI),
    _minutes(196, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2023%20MINUTES/PZDB/02212023%20%20%20PZDB%20Minutes.pdf", "2023-02-21", _BSI),
    _minutes(195, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2023%20MINUTES/PZDB/01112023%20%20%20PZDB%20Minutes.pdf", "2023-01-11", _BSI),
    # 2022
    _minutes(222, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2022%20MINUTES/PZD%20BOARD/12132022%20PZDB%20Minutes.pdf", "2022-12-13", _WE),
    _minutes(221, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2022%20MINUTES/PZD%20BOARD/11082022%20PZDB%20Minutes.pdf", "2022-11-08", _WE),
    _minutes(220, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2022%20MINUTES/PZD%20BOARD/10252022%20PZDB%20Minutes.pdf", "2022-10-25", _WE),
    _minutes(219, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2022%20MINUTES/PZD%20BOARD/10112022%20PZDB%20Minutes.pdf", "2022-10-11", _WE),
    _minutes(218, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2022%20MINUTES/PZD%20BOARD/09272022%20PZDB%20Minutes.pdf", "2022-09-27", _WE),
    _minutes(217, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2022%20MINUTES/PZD%20BOARD/09132022%20PZDB%20Minutes.pdf", "2022-09-13", _WE),
    _minutes(216, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2022%20MINUTES/PZD%20BOARD/08092022%20PZDB%20Minutes.pdf", "2022-08-09", _WE),
    _minutes(215, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2022%20MINUTES/PZD%20BOARD/07122022%20PZDB%20Minutes.pdf", "2022-07-12", _WE),
    _minutes(214, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2022%20MINUTES/PZD%20BOARD/06142022%20PZDB%20Minutes.pdf", "2022-06-14", _WE),
    _minutes(213, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2022%20MINUTES/PZD%20BOARD/05102022%20PZDB%20Minutes.pdf", "2022-05-10", _WE),
    _minutes(212, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2022%20MINUTES/PZD%20BOARD/04122022%20PZDB%20Minutes.pdf", "2022-04-12", _WE),
    _minutes(211, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2022%20MINUTES/PZD%20BOARD/03082022%20PZDB%20Minutes.pdf", "2022-03-08", _WE),
    _minutes(210, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2022%20MINUTES/PZD%20BOARD/02082022%20PZDB%20Minutes.pdf", "2022-02-08", _WE),
    _minutes(209, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2022%20MINUTES/PZD%20BOARD/01112022%20PZDB%20Minutes.pdf", "2022-01-11", _WE),
    # 2021
    _minutes(233, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2021%20Minutes/PZDB%20Minutes/12142021%20PZDB%20Minutes.pdf", "2021-12-14", _WE),
    _minutes(232, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2021%20Minutes/PZDB%20Minutes/11092021%20PZDB%20Minutes.pdf", "2021-11-09", _WE),
    _minutes(231, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2021%20Minutes/PZDB%20Minutes/10122021%20PZDB%20Minutes.pdf", "2021-10-12", _WE),
    _minutes(230, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2021%20Minutes/PZDB%20Minutes/09282021%20PZDB%20Minutes.pdf", "2021-09-28", _WE),
    _minutes(229, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2021%20Minutes/PZDB%20Minutes/09142021%20PZDB%20Minutes.pdf", "2021-09-14", _WE),
    _minutes(228, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2021%20Minutes/PZDB%20Minutes/08242021%20PZDB%20Minutes.pdf", "2021-08-24", _WE),
    _minutes(227, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2021%20Minutes/PZDB%20Minutes/08102021%20PZDB%20Minutes.pdf", "2021-08-10", _WE),
    _minutes(226, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2021%20Minutes/PZDB%20Minutes/07132021%20PZDB%20Minutes.pdf", "2021-07-13", _WE),
    _minutes(225, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2021%20Minutes/PZDB%20Minutes/06082021%20PZDB%20Minutes.pdf", "2021-06-08", _WE),
    _minutes(224, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2021%20Minutes/PZDB%20Minutes/05112021%20PZDB%20Minutes.pdf", "2021-05-11", _WE),
    _minutes(223, "https://estero-fl.gov/wp-content/uploads/library-ada/minutes/2021%20Minutes/PZDB%20Minutes/04202021%20PZDB%20Minutes.pdf", "2021-04-20", _WE),
]


# ---------------------------------------------------------------------------
# Road/Trail geometry — LineString vertices anchored to real geocoded points
# [lon, lat]
# ---------------------------------------------------------------------------

ROAD_GEOMETRIES: dict[int, list[list[float]]] = {
    # BERT Rail Trail — runs N-S through the village (anchored at 26.4339, -81.8157)
    1: [
        [-81.815700, 26.410000],
        [-81.815500, 26.420000],
        [-81.815700, 26.433900],
        [-81.815600, 26.448000],
        [-81.815400, 26.460000],
    ],
    # Corkscrew Road Widening Corridor — E-W, anchored at (26.4363, -81.7701)
    6: [
        [-81.800000, 26.436300],
        [-81.790000, 26.436200],
        [-81.780000, 26.436100],
        [-81.770100, 26.436300],
        [-81.760000, 26.436500],
    ],
    # Corkscrew Rd / Puente Lane — shorter segment anchored at (26.4312, -81.7847)
    7: [
        [-81.790000, 26.431000],
        [-81.784700, 26.431200],
        [-81.780000, 26.431500],
    ],
}

# ---------------------------------------------------------------------------
# Area geometry — Polygon rings for Infrastructure zones
# Approximate neighborhood bounding boxes; tighten with real parcel data later.
# [[[lon, lat], ...]]
# ---------------------------------------------------------------------------

AREA_GEOMETRIES: dict[int, list[list[list[float]]]] = {
    # Estero Bay Village Septic Area (26.4408, -81.8225)
    2: [[
        [-81.828000, 26.436000],
        [-81.817000, 26.436000],
        [-81.817000, 26.445000],
        [-81.828000, 26.445000],
        [-81.828000, 26.436000],
    ]],
    # Sunny Grove Septic Area (26.4376, -81.8128)
    3: [[
        [-81.818000, 26.433000],
        [-81.807000, 26.433000],
        [-81.807000, 26.442000],
        [-81.818000, 26.442000],
        [-81.818000, 26.433000],
    ]],
    # Cypress Bend Septic Area (26.4469, -81.8116)
    4: [[
        [-81.817000, 26.443000],
        [-81.806000, 26.443000],
        [-81.806000, 26.451000],
        [-81.817000, 26.451000],
        [-81.817000, 26.443000],
    ]],
    # Broadway Avenue East UEP (26.4420, -81.8054)
    5: [[
        [-81.811000, 26.438000],
        [-81.800000, 26.438000],
        [-81.800000, 26.446000],
        [-81.811000, 26.446000],
        [-81.811000, 26.438000],
    ]],
}


# ---------------------------------------------------------------------------
# MockStore
# ---------------------------------------------------------------------------

class MockStore:
    """
    Data access interface backed by the in-memory tables above.

    Migration path: replace each method with an async DB query.
    The routers and services call only these methods — nothing else changes.
    """

    def get_projects(self, status: Optional[str] = None) -> list[dict]:
        rows = deepcopy(PROJECTS)
        if status:
            rows = [r for r in rows if r["status"] == status]
        return rows

    def get_project(self, project_id: int) -> Optional[dict]:
        return next((deepcopy(r) for r in PROJECTS if r["project_id"] == project_id), None)

    def get_meeting_types(self) -> list[dict]:
        return deepcopy(MEETING_TYPES)

    def get_meeting_type(self, type_id: int) -> Optional[dict]:
        return next((deepcopy(r) for r in MEETING_TYPES if r["type_id"] == type_id), None)

    def get_meetings(
        self,
        project_id: Optional[int] = None,
        year: Optional[int] = None,
        status: Optional[str] = None,
        type_id: Optional[int] = None,
        location_id: Optional[int] = None,
    ) -> list[dict]:
        rows = deepcopy(MEETINGS)
        if project_id is not None:
            rows = [r for r in rows if r["project_id"] == project_id]
        if year is not None:
            rows = [r for r in rows if r["meeting_year"] == year]
        if status:
            rows = [r for r in rows if r["status"] == status]
        if type_id is not None:
            rows = [r for r in rows if r["type_id"] == type_id]
        if location_id is not None:
            rows = [r for r in rows if r.get("location_id") == location_id]
        return rows

    def get_meeting(self, meeting_id: int) -> Optional[dict]:
        return next((deepcopy(r) for r in MEETINGS if r["meeting_id"] == meeting_id), None)

    def get_locations(
        self,
        project_id: Optional[int] = None,
        location_type: Optional[str] = None,
    ) -> list[dict]:
        rows = deepcopy(LOCATIONS)
        if project_id is not None:
            rows = [r for r in rows if r["project_id"] == project_id]
        if location_type:
            rows = [r for r in rows if r["location_type"] == location_type]
        return rows

    def get_location(self, location_id: int) -> Optional[dict]:
        return next((deepcopy(r) for r in LOCATIONS if r["location_id"] == location_id), None)

    def get_documents(
        self,
        meeting_id: Optional[int] = None,
        document_type: Optional[str] = None,
    ) -> list[dict]:
        rows = deepcopy(DOCUMENTS)
        if meeting_id is not None:
            rows = [r for r in rows if r["meeting_id"] == meeting_id]
        if document_type:
            rows = [r for r in rows if r["document_type"] == document_type]
        return rows

    def get_document(self, document_id: int) -> Optional[dict]:
        return next((deepcopy(r) for r in DOCUMENTS if r["document_id"] == document_id), None)

    def get_road_geometry(self, location_id: int) -> Optional[list[list[float]]]:
        return ROAD_GEOMETRIES.get(location_id)

    def get_area_geometry(self, location_id: int) -> Optional[list[list[list[float]]]]:
        return AREA_GEOMETRIES.get(location_id)
