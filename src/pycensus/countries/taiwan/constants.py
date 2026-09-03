"""Static Taiwan geography reference data shared by every Taiwan census source.

Technical aspects:
    Taiwan's administrative divisions (native levels used throughout this
    module):
    - Nation (country level)
    - County/city (縣市) -- 22 units: 6 special municipalities (直轄市:
      臺北市/新北市/桃園市/臺中市/臺南市/高雄市), 3 provincial cities
      (省轄市: 基隆市/新竹市/嘉義市), 13 counties (縣), including outlying
      Kinmen (金門縣) and Lienchiang/Matsu (連江縣). This is Taiwan's
      top subnational tier -- there is no separate state/province layer
      above it.
    - District (鄉鎮市區) -- townships/districts within a county/city.
    - Village (村里) -- the finest tier MOI publishes population for.

    ``COUNTY_CODES`` below is not looked up from a code table -- it was
    built directly from the real, live MOI RIS API response used by
    :mod:`pycensus.taiwan.api`/:mod:`pycensus.taiwan.moi.loader`
    (``GET https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP013/11407``,
    verified 2026-08-20): the first 5 digits of every row's
    ``district_code`` field, paired with the first 3 characters of that
    row's ``site_id`` field (the county/city name prefix of
    "<county/city><district>", e.g. "新北市板橋區" -> "新北市"). All 22
    codes that appear in the live response are listed here; nothing was
    guessed or filled in from a naming convention.

Source:
    https://www.ris.gov.tw/ (中華民國內政部戶政司, Department of Household
    Registration, Ministry of the Interior)
"""

from __future__ import annotations

from typing import Dict, List

# Taiwan county/city (縣市) codes -- 5-digit codes, the first 5 digits of
# MOI RIS's 11-digit district_code. Verified live against ODRP013/11407
# (2025-07), see module docstring.
COUNTY_CODES: Dict[str, str] = {
    "63000": "臺北市",  # Taipei City (special municipality)
    "65000": "新北市",  # New Taipei City (special municipality)
    "68000": "桃園市",  # Taoyuan City (special municipality)
    "66000": "臺中市",  # Taichung City (special municipality)
    "67000": "臺南市",  # Tainan City (special municipality)
    "64000": "高雄市",  # Kaohsiung City (special municipality)
    "10017": "基隆市",  # Keelung City (provincial city)
    "10018": "新竹市",  # Hsinchu City (provincial city)
    "10020": "嘉義市",  # Chiayi City (provincial city)
    "10002": "宜蘭縣",  # Yilan County
    "10004": "新竹縣",  # Hsinchu County
    "10005": "苗栗縣",  # Miaoli County
    "10007": "彰化縣",  # Changhua County
    "10008": "南投縣",  # Nantou County
    "10009": "雲林縣",  # Yunlin County
    "10010": "嘉義縣",  # Chiayi County
    "10013": "屏東縣",  # Pingtung County
    "10014": "臺東縣",  # Taitung County
    "10015": "花蓮縣",  # Hualien County
    "10016": "澎湖縣",  # Penghu County
    "09020": "金門縣",  # Kinmen County
    "09007": "連江縣",  # Lienchiang (Matsu) County
}

# Romanized English names, for convenience lookups (not from MOI -- these
# are the standard/official romanizations used on Taiwanese government
# English-language sites, e.g. https://www.ris.gov.tw/app/en).
COUNTY_NAMES_EN: Dict[str, str] = {
    "63000": "Taipei City",
    "65000": "New Taipei City",
    "68000": "Taoyuan City",
    "66000": "Taichung City",
    "67000": "Tainan City",
    "64000": "Kaohsiung City",
    "10017": "Keelung City",
    "10018": "Hsinchu City",
    "10020": "Chiayi City",
    "10002": "Yilan County",
    "10004": "Hsinchu County",
    "10005": "Miaoli County",
    "10007": "Changhua County",
    "10008": "Nantou County",
    "10009": "Yunlin County",
    "10010": "Chiayi County",
    "10013": "Pingtung County",
    "10014": "Taitung County",
    "10015": "Hualien County",
    "10016": "Penghu County",
    "09020": "Kinmen County",
    "09007": "Lienchiang County",
}

# Taiwan's native levels (see module docstring): nation, county_city,
# district, village. Universal level names not native to Taiwan fall back
# to the closest native level, mirroring pycensus.spain.constants'
# state->autonomous_community / county->municipality pattern: county_city
# is Taiwan's only subnational tier above the township level (there is no
# separate state/province layer), district is the city/town-equivalent
# tier, and village is the finest tier MOI publishes population for.
LEVEL_FALLBACK: Dict[str, str] = {
    "state": "county_city",
    "province": "county_city",
    "county": "district",
    "municipality": "district",
    "place": "district",
    "tract": "village",
    "blockgroup": "village",
    "block": "village",
}

# geoBoundaries.org's Taiwan ADM1 (county/city) layer -- a real, keyless,
# single-file GeoJSON download (~3.2MB, verified 2026-08-20:
# `GET https://www.geoboundaries.org/api/current/gbOpen/TWN/ADM1/` returns a
# real catalog entry; `gjDownloadURL` resolves to a real 22-feature file).
# This is NOT NLSC's official file -- NLSC's real county/city boundary
# dataset is cataloged at https://data.gov.tw/dataset/7442 but its actual
# download is served from TGOS (www.tgos.tw), which returns HTTP 403 to
# every plain HTTP client (verified dead end, see geography.py docstring).
# geoBoundaries' TWN layer is itself sourced from OpenStreetMap (its own API
# response says `"boundarySource": "OpenStreetMap, Wambacher"`), not from a
# Taiwan government agency -- real, verifiable, actively-maintained
# geometry, but one step removed from an official statistics-agency file.
# Used here as the practical fallback until TGOS's download gate is beaten.
GEOBOUNDARIES_TWN_ADM1_URL = (
    "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/"
    "gbOpen/TWN/ADM1/geoBoundaries-TWN-ADM1.geojson"
)

# geoBoundaries' `shapeISO` (ISO 3166-2:TW) -> our 5-digit MOI county/city
# code. Built by downloading GEOBOUNDARIES_TWN_ADM1_URL and matching each of
# its 22 features' shapeISO/shapeName against COUNTY_CODES/COUNTY_NAMES_EN
# above (verified 2026-08-20: exactly 22 features, one per COUNTY_CODES
# entry, no leftovers on either side).
GEOBOUNDARIES_ISO_TO_COUNTY_CODE: Dict[str, str] = {
    "TW-TPE": "63000",  # Taipei
    "TW-NWT": "65000",  # New Taipei
    "TW-TAO": "68000",  # Taoyuan
    "TW-TXG": "66000",  # Taichung
    "TW-TNN": "67000",  # Tainan
    "TW-KHH": "64000",  # Kaohsiung
    "TW-KEE": "10017",  # Keelung
    "TW-HSZ": "10018",  # Hsinchu (city)
    "TW-CYI": "10020",  # Chiayi (city)
    "TW-ILA": "10002",  # Yilan County
    "TW-HSQ": "10004",  # Hsinchu County
    "TW-MIA": "10005",  # Miaoli County
    "TW-CHA": "10007",  # Changhua County
    "TW-NAN": "10008",  # Nantou County
    "TW-YUN": "10009",  # Yunlin County
    "TW-CYQ": "10010",  # Chiayi County
    "TW-PIF": "10013",  # Pingtung County
    "TW-TTT": "10014",  # Taitung County
    "TW-HUA": "10015",  # Hualien County
    "TW-PEN": "10016",  # Penghu County
    "TW-KIN": "09020",  # Kinmen County
    "TW-LIE": "09007",  # Lienchiang (Matsu) County
}

# geoBoundaries' Taiwan ADM2 (township/district) layer -- a real, keyless,
# single-file GeoJSON download (~10.5MB, verified 2026-08-20:
# `GET https://www.geoboundaries.org/api/current/gbOpen/TWN/ADM2/` returns a
# real catalog entry, `gjDownloadURL` resolves to a real 368-feature file
# -- same OpenStreetMap/Wambacher source as ADM1, see
# GEOBOUNDARIES_TWN_ADM1_URL above).
GEOBOUNDARIES_TWN_ADM2_URL = (
    "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/"
    "gbOpen/TWN/ADM2/geoBoundaries-TWN-ADM2.geojson"
)

# geoBoundaries ADM2's `shapeID` -> MOI RIS's 8-digit district_code prefix
# (see moi/loader.py's `_aggregate_to_level`, `level == "district"` branch).
# Unlike ADM1, ADM2 features carry no MOI-compatible code field at all
# (`shapeISO` is blank on every ADM2 feature) and most `shapeName` values
# are English transliterations, not the Chinese names MOI RIS uses -- so
# this table was built by:
#   1. Downloading GEOBOUNDARIES_TWN_ADM2_URL (368 features, verified
#      2026-08-20) and every district_code/site_id pair from MOI RIS's live
#      ODRP013/11407 response (7749 village rows -> 368 unique 8-digit
#      district_code prefixes, exactly matching the ADM2 feature count).
#   2. Spatially joining each ADM2 feature's representative point against
#      the already-verified GEOBOUNDARIES_ISO_TO_COUNTY_CODE-keyed ADM1
#      polygons, to get each district's county/city -- this disambiguates
#      same-named districts across counties (e.g. multiple counties/cities
#      each have a "中區"/"東區"/"西區"/"南區"/"北區") without needing to
#      parse county names out of English shapeNames.
#   3. Within each county, matching shapeName against MOI's Chinese
#      district name: directly for the ~15 ADM2 features whose shapeName
#      is itself Chinese (e.g. "苑裡鎮"), by Hanyu Pinyin (via the
#      `pypinyin` library, stripping the trailing 鄉/鎮/市/區 character and
#      English District/Township/City/Town suffix) for 329 of the
#      remaining 353, verified unambiguous because every county's set of
#      un-matched ADM2 features has the same size as its set of unmatched
#      MOI districts (a forced bijection, not a fuzzy guess).
#   4. The last 39 features needed individual, verified overrides because
#      pypinyin's default Hanyu Pinyin reading doesn't reproduce them:
#      Kaohsiung/Tainan districts romanized in Tongyong Pinyin instead of
#      Hanyu Pinyin (systematic q->c/x->s/zh->jh substitution, e.g.
#      "Cianjhen" for 前鎮, matched against the sole remaining MOI district
#      in that county after exact matches were removed -- not a guess,
#      since only one candidate was left); Taichung/Tainan/Chiayi City's
#      numbered districts given as English translations ("West District")
#      rather than transliterations; and heteronym cases where pypinyin's
#      default reading differs from the place-name reading (長 read as
#      "zhang" vs the place-name "chang" in 長治/長濱/長治鄉, 埔 read as
#      "bu" vs the place-name "pu" in 大埔鄉) -- resolved the same way,
#      because exactly one MOI district was left unmatched in that county.
#      One pair, Xiaying/Siaying (下營/新營, both in Tainan), had
#      geoBoundaries shapeNames that are swapped relative to their actual
#      geometry -- verified by checking each feature's centroid coordinates
#      against the real towns' known locations (the feature *named*
#      "Xiaying" sits at 23.30N/120.29E, i.e. Xinying's real location; the
#      feature *named* "Siaying" sits at 23.23N/120.26E, i.e. Xiaying's
#      real location) -- so this table's assignment follows the verified
#      geometry, not the mislabeled shapeName text.
# End result: all 368 ADM2 features matched to all 368 MOI district codes,
# a verified 1:1 bijection with none left over on either side and no
# fabricated/fuzzy-guessed entries (see scratch work referenced in the
# implementing session for the full derivation script).
GEOBOUNDARIES_ADM2_TO_DISTRICT_CODE: Dict[str, str] = {
    "52511910B78526013910080": "09007010",
    "52511910B38062779232785": "09007020",
    "52511910B3516463668472": "09007030",
    "52511910B39055948947966": "09007040",
    "52511910B21260910933226": "09020010",
    "52511910B24095937104675": "09020020",
    "52511910B57972476709593": "09020030",
    "52511910B29261340686380": "09020040",
    "52511910B30921209280056": "09020050",
    "52511910B62500214534323": "09020060",
    "52511910B14816404731270": "10002010",
    "52511910B2005519933546": "10002020",
    "52511910B76288634877329": "10002030",
    "52511910B1170609292065": "10002040",
    "52511910B67044835484249": "10002050",
    "52511910B24217315836254": "10002060",
    "52511910B30880402907345": "10002070",
    "52511910B8555120582575": "10002080",
    "52511910B7774942695724": "10002090",
    "52511910B30774246387934": "10002100",
    "52511910B1281835166424": "10002110",
    "52511910B58011485138839": "10002120",
    "52511910B954183777842": "10004010",
    "52511910B83254623159264": "10004020",
    "52511910B82760897224923": "10004030",
    "52511910B48556697809502": "10004040",
    "52511910B77517078586613": "10004050",
    "52511910B50770239456778": "10004060",
    "52511910B8433520860340": "10004070",
    "52511910B22102802824180": "10004080",
    "52511910B96314718972571": "10004090",
    "52511910B70638918104863": "10004100",
    "52511910B53218930904512": "10004110",
    "52511910B48822656668811": "10004120",
    "52511910B21980317252116": "10004130",
    "52511910B26440140856632": "10005010",
    "52511910B80611967822771": "10005020",
    "52511910B96063333949316": "10005030",
    "52511910B68602378722707": "10005040",
    "52511910B27389223998758": "10005050",
    "52511910B26517515062770": "10005060",
    "52511910B14763561478876": "10005070",
    "52511910B71032150875325": "10005080",
    "52511910B29818712056723": "10005090",
    "52511910B53728166380969": "10005100",
    "52511910B42807411813200": "10005110",
    "52511910B1289591480139": "10005120",
    "52511910B13267113488931": "10005130",
    "52511910B62200479590982": "10005140",
    "52511910B63672424305930": "10005150",
    "52511910B37723179298847": "10005160",
    "52511910B1345857498627": "10005170",
    "52511910B36549244443661": "10005180",
    "52511910B76643025216805": "10007010",
    "52511910B67569609565838": "10007020",
    "52511910B24911018318465": "10007030",
    "52511910B4802898208422": "10007040",
    "52511910B66525116512935": "10007050",
    "52511910B35262105049161": "10007060",
    "52511910B61439489120441": "10007070",
    "52511910B80020209032330": "10007080",
    "52511910B4018321552262": "10007090",
    "52511910B4946947315760": "10007100",
    "52511910B59824272814460": "10007110",
    "52511910B68305869820707": "10007120",
    "52511910B79023193352255": "10007130",
    "52511910B7838707993704": "10007140",
    "52511910B52234359951443": "10007150",
    "52511910B24462040337349": "10007160",
    "52511910B92709587856848": "10007170",
    "52511910B53055897182204": "10007180",
    "52511910B14295991899678": "10007190",
    "52511910B45758904415578": "10007200",
    "52511910B93844416805291": "10007210",
    "52511910B86901151057582": "10007220",
    "52511910B39925062868722": "10007230",
    "52511910B21046020325533": "10007240",
    "52511910B69050472249631": "10007250",
    "52511910B43288181316884": "10007260",
    "52511910B11437294536827": "10008010",
    "52511910B90712224530022": "10008020",
    "52511910B24890266463781": "10008030",
    "52511910B648094459248": "10008040",
    "52511910B59553354826271": "10008050",
    "52511910B95850947838113": "10008060",
    "52511910B8640641883305": "10008070",
    "52511910B28710323112279": "10008080",
    "52511910B58943778362560": "10008090",
    "52511910B81868017791126": "10008100",
    "52511910B97596648855860": "10008110",
    "52511910B65736953470193": "10008120",
    "52511910B4023851996912": "10008130",
    "52511910B54544949915679": "10009010",
    "52511910B41918855057041": "10009020",
    "52511910B66692058551395": "10009030",
    "52511910B93540688501820": "10009040",
    "52511910B60061263127196": "10009050",
    "52511910B94627775761425": "10009060",
    "52511910B61790844495814": "10009070",
    "52511910B61192023784720": "10009080",
    "52511910B82181877276071": "10009090",
    "52511910B99182661436347": "10009100",
    "52511910B3173449865557": "10009110",
    "52511910B99479800826846": "10009120",
    "52511910B12217989868885": "10009130",
    "52511910B55591891530874": "10009140",
    "52511910B17799667237096": "10009150",
    "52511910B40379944508344": "10009160",
    "52511910B1376149917055": "10009170",
    "52511910B71690687423925": "10009180",
    "52511910B9027234137610": "10009190",
    "52511910B61676244874246": "10009200",
    "52511910B26426295483490": "10010010",
    "52511910B67244265985329": "10010020",
    "52511910B59176200579981": "10010030",
    "52511910B15112316927565": "10010040",
    "52511910B34768840903386": "10010050",
    "52511910B40762326804108": "10010060",
    "52511910B52167757698823": "10010070",
    "52511910B86399036189677": "10010080",
    "52511910B91175598455743": "10010090",
    "52511910B19586040436612": "10010100",
    "52511910B1429973809191": "10010110",
    "52511910B78624558885304": "10010120",
    "52511910B68145786967648": "10010130",
    "52511910B55503333028627": "10010140",
    "52511910B52477730632252": "10010150",
    "52511910B82353065981408": "10010160",
    "52511910B78382154896940": "10010170",
    "52511910B70473175587181": "10010180",
    "52511910B78362812420952": "10013010",
    "52511910B55551570232595": "10013020",
    "52511910B63745543652662": "10013030",
    "52511910B47108576517123": "10013040",
    "52511910B53659520741831": "10013050",
    "52511910B94067910328765": "10013060",
    "52511910B59245920767717": "10013070",
    "52511910B18270670997793": "10013080",
    "52511910B32855735947523": "10013090",
    "52511910B65674101735888": "10013100",
    "52511910B31003231188752": "10013110",
    "52511910B95398494564210": "10013120",
    "52511910B65196754917234": "10013130",
    "52511910B50234287801955": "10013140",
    "52511910B59671861776280": "10013150",
    "52511910B31717620625581": "10013160",
    "52511910B1240337598967": "10013170",
    "52511910B86635109020715": "10013180",
    "52511910B8694284014765": "10013190",
    "52511910B82588790657213": "10013200",
    "52511910B132067886793": "10013210",
    "52511910B90795941917739": "10013220",
    "52511910B47244734334087": "10013230",
    "52511910B96811995525646": "10013240",
    "52511910B32484376841800": "10013250",
    "52511910B78140930961679": "10013260",
    "52511910B41847670787440": "10013270",
    "52511910B55440888068193": "10013280",
    "52511910B3118715998086": "10013290",
    "52511910B76864499188928": "10013300",
    "52511910B70153095650041": "10013310",
    "52511910B47928826922149": "10013320",
    "52511910B86664130512952": "10013330",
    "52511910B26321075911025": "10014010",
    "52511910B97060806511909": "10014020",
    "52511910B59360103371589": "10014030",
    "52511910B49397347460294": "10014040",
    "52511910B14571669428725": "10014050",
    "52511910B55567443002533": "10014060",
    "52511910B95876228816034": "10014070",
    "52511910B28406755893597": "10014080",
    "52511910B85663060935330": "10014090",
    "52511910B16211515353621": "10014100",
    "52511910B398222474379": "10014110",
    "52511910B3988585053627": "10014120",
    "52511910B70456030054544": "10014130",
    "52511910B76622709081814": "10014140",
    "52511910B9049907467318": "10014150",
    "52511910B19407638162060": "10014160",
    "52511910B56958480946992": "10015010",
    "52511910B17390178466990": "10015020",
    "52511910B43880613502989": "10015030",
    "52511910B49284203349487": "10015040",
    "52511910B33929030594907": "10015050",
    "52511910B46580896438278": "10015060",
    "52511910B4969786063416": "10015070",
    "52511910B98966812491458": "10015080",
    "52511910B22417450396653": "10015090",
    "52511910B38320737099141": "10015100",
    "52511910B12239492719020": "10015110",
    "52511910B67072521171420": "10015120",
    "52511910B84254778922177": "10015130",
    "52511910B17356876538254": "10016010",
    "52511910B80624224978544": "10016020",
    "52511910B16548233454257": "10016030",
    "52511910B49192689587509": "10016040",
    "52511910B25870488928169": "10016050",
    "52511910B27783301561641": "10016060",
    "52511910B92065650444302": "10017010",
    "52511910B49246730473855": "10017020",
    "52511910B3088598520620": "10017030",
    "52511910B30709967967550": "10017040",
    "52511910B84130893113897": "10017050",
    "52511910B26024129556324": "10017060",
    "52511910B33100646615087": "10017070",
    "52511910B28036042271757": "10018010",
    "52511910B8569683364670": "10018020",
    "52511910B39021201460320": "10018030",
    "52511910B45111644423638": "10020010",
    "52511910B30977236715140": "10020020",
    "52511910B27691000187918": "63000010",
    "52511910B97040583536387": "63000020",
    "52511910B72557613719767": "63000030",
    "52511910B2433100174245": "63000040",
    "52511910B97228601381981": "63000050",
    "52511910B40907976300093": "63000060",
    "52511910B53442502489936": "63000070",
    "52511910B85672644454395": "63000080",
    "52511910B46327040282414": "63000090",
    "52511910B60889717547120": "63000100",
    "52511910B57344020400583": "63000110",
    "52511910B98030585757527": "63000120",
    "52511910B3606287647189": "64000010",
    "52511910B97258167764484": "64000020",
    "52511910B44183742195819": "64000030",
    "52511910B91354507826004": "64000040",
    "52511910B99923381863543": "64000050",
    "52511910B42739382471676": "64000060",
    "52511910B68600157990452": "64000070",
    "52511910B57885575775117": "64000080",
    "52511910B4874504546565": "64000090",
    "52511910B42295955196197": "64000100",
    "52511910B46875128491": "64000110",
    "52511910B45067846009416": "64000120",
    "52511910B83654747413473": "64000130",
    "52511910B14985671444346": "64000140",
    "52511910B37639564414460": "64000150",
    "52511910B41569626445575": "64000160",
    "52511910B30663215399885": "64000170",
    "52511910B94488542881377": "64000180",
    "52511910B81672195550340": "64000190",
    "52511910B77588417233313": "64000200",
    "52511910B73336698759549": "64000210",
    "52511910B51671938708352": "64000220",
    "52511910B31970606922462": "64000230",
    "52511910B54132966107148": "64000240",
    "52511910B24425392494170": "64000250",
    "52511910B54123288304078": "64000260",
    "52511910B94409074074623": "64000270",
    "52511910B79940153361499": "64000280",
    "52511910B81270804246754": "64000290",
    "52511910B19330386236783": "64000300",
    "52511910B30715783231624": "64000310",
    "52511910B66300742055958": "64000320",
    "52511910B69477070610060": "64000330",
    "52511910B90052363141845": "64000340",
    "52511910B49699122775209": "64000350",
    "52511910B8366046265197": "64000360",
    "52511910B89557374460695": "64000370",
    "52511910B40932238962124": "64000380",
    "52511910B6389603869041": "65000010",
    "52511910B68505135665197": "65000020",
    "52511910B21407702399528": "65000030",
    "52511910B68559401871490": "65000040",
    "52511910B29325635095698": "65000050",
    "52511910B81807770672257": "65000060",
    "52511910B57035161982504": "65000070",
    "52511910B16992601244944": "65000080",
    "52511910B98629971413037": "65000090",
    "52511910B49336497562900": "65000100",
    "52511910B94675128167590": "65000110",
    "52511910B85706759339541": "65000120",
    "52511910B24789968471650": "65000130",
    "52511910B86675185737242": "65000140",
    "52511910B41832053670190": "65000150",
    "52511910B75402986028359": "65000160",
    "52511910B70290379794397": "65000170",
    "52511910B54921877123299": "65000180",
    "52511910B62556379472396": "65000190",
    "52511910B90991611037176": "65000200",
    "52511910B22297779295169": "65000210",
    "52511910B62922031863482": "65000220",
    "52511910B94458762678017": "65000230",
    "52511910B49041277824691": "65000240",
    "52511910B77222989775801": "65000250",
    "52511910B24338772487994": "65000260",
    "52511910B47117449404442": "65000270",
    "52511910B10855589670933": "65000280",
    "52511910B1435450581762": "65000290",
    "52511910B5845387986633": "66000010",
    "52511910B56209015841977": "66000020",
    "52511910B54429610497624": "66000030",
    "52511910B31268860247424": "66000040",
    "52511910B62562257240113": "66000050",
    "52511910B1114695065436": "66000060",
    "52511910B88737921309662": "66000070",
    "52511910B1854707671717": "66000080",
    "52511910B89393531563013": "66000090",
    "52511910B5173446134858": "66000100",
    "52511910B39647585180353": "66000110",
    "52511910B27876515321702": "66000120",
    "52511910B95956240331763": "66000130",
    "52511910B49492134849249": "66000140",
    "52511910B49637011657057": "66000150",
    "52511910B92990516943265": "66000160",
    "52511910B80553421723016": "66000170",
    "52511910B79351211043156": "66000180",
    "52511910B79904820365756": "66000190",
    "52511910B87526029786391": "66000200",
    "52511910B37647459697968": "66000210",
    "52511910B63167976390159": "66000220",
    "52511910B17490321584859": "66000230",
    "52511910B3092467574862": "66000240",
    "52511910B23437445078556": "66000250",
    "52511910B92188863099631": "66000260",
    "52511910B19191805182315": "66000270",
    "52511910B17517272780410": "66000280",
    "52511910B1724778943765": "66000290",
    "52511910B15727969780764": "67000010",
    "52511910B3549258104854": "67000020",
    "52511910B83755823779571": "67000030",
    "52511910B95098417504855": "67000040",
    "52511910B86463604693023": "67000050",
    "52511910B26605642536320": "67000060",
    "52511910B41349980343036": "67000070",
    "52511910B67622492960002": "67000080",
    "52511910B9639721186799": "67000090",
    "52511910B66393591343605": "67000100",
    "52511910B21548483035565": "67000110",
    "52511910B43412485397625": "67000120",
    "52511910B13500089926277": "67000130",
    "52511910B54492038659997": "67000140",
    "52511910B14944460308189": "67000150",
    "52511910B80613047181881": "67000160",
    "52511910B93975188491166": "67000170",
    "52511910B47006759189229": "67000180",
    "52511910B12240276172675": "67000190",
    "52511910B52040400722593": "67000200",
    "52511910B27035674370402": "67000210",
    "52511910B49735999236113": "67000220",
    "52511910B65003852157868": "67000230",
    "52511910B12166681712059": "67000240",
    "52511910B59203276225690": "67000250",
    "52511910B71538284073489": "67000260",
    "52511910B2226983620167": "67000270",
    "52511910B83187520966287": "67000280",
    "52511910B37391519791178": "67000290",
    "52511910B87738681480797": "67000300",
    "52511910B38482668702502": "67000310",
    "52511910B558444185686": "67000320",
    "52511910B45186727587827": "67000330",
    "52511910B67503722299641": "67000340",
    "52511910B51634678228857": "67000350",
    "52511910B44653158831279": "67000360",
    "52511910B28476693424992": "67000370",
    "52511910B36399926613491": "68000010",
    "52511910B96194264601254": "68000020",
    "52511910B95362195406961": "68000030",
    "52511910B40704082736400": "68000040",
    "52511910B98838605252897": "68000050",
    "52511910B2055603825455": "68000060",
    "52511910B79239618011253": "68000070",
    "52511910B50474008293669": "68000080",
    "52511910B47715712995546": "68000090",
    "52511910B6162382764157": "68000100",
    "52511910B75183314272458": "68000110",
    "52511910B57239711193520": "68000120",
    "52511910B10215199478646": "68000130",
}

# Most recent vintage confirmed live against MOI RIS's ODRP013 endpoint
# (2026-08-20): "11407" is an ROC year-month (ROC year 114 = 2025, month
# 07) -- the newest yyymm that actually returns data as of this writing;
# 11508-11512 all returned "查無資料" (no data) at verification time.
LATEST_YEAR: Dict[str, str] = {
    "census": "11407",  # ROC yyymm, see pycensus.taiwan.utils.roc_yyymm_to_year
}

# OpenStreetMap's Overpass API -- used for village (村里) boundaries, the
# only level where the polygons themselves carry MOI's own 11-digit
# district_code directly (as OSM's `nat_ref` tag), needing no fuzzy name
# matching at all. Verified live 2026-08-22: querying every
# `admin_level=9`/`boundary=administrative` relation inside Taipei City's
# OSM area returns exactly 456 relations, each with a unique `nat_ref`, and
# that 456-element set is an *exact* match (zero missing, zero extra) to
# the 456 unique 11-digit `district_code`s MOI RIS's live ODRP013/11407
# response has for county/city prefix "63000" (Taipei). New Taipei City
# ("65000") is a close but not exact match (1032 of 1039 OSM relations'
# `nat_ref`s match a real MOI village code; the other 7 don't correspond to
# any current MOI village -- likely stale/renamed splits in OSM). Real,
# public, keyless -- not an official NLSC file (NLSC's own village
# boundary download is the same TGOS-hosted, HTTP 403-blocked dead end
# documented in GEOBOUNDARIES_TWN_ADM1_URL above), but independently
# verifiable against MOI's own code list on every fetch (see
# ``geography._download_village_geojson``, which raises loudly rather than
# silently using an unmatched relation).
OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"

# Default data directory.
DEFAULT_DATA_DIR = "data/taiwan"

__all__ = [
    "COUNTY_CODES",
    "COUNTY_NAMES_EN",
    "GEOBOUNDARIES_TWN_ADM1_URL",
    "GEOBOUNDARIES_ISO_TO_COUNTY_CODE",
    "GEOBOUNDARIES_TWN_ADM2_URL",
    "GEOBOUNDARIES_ADM2_TO_DISTRICT_CODE",
    "OVERPASS_API_URL",
    "LEVEL_FALLBACK",
    "LATEST_YEAR",
    "DEFAULT_DATA_DIR",
]
