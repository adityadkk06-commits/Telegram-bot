"""
IDX Stock Universe — Official IDX Sector Classification (2021).

Sector names match IDX's 11-sector framework:
  Finance, Basic Materials, Consumer Cyclicals, Consumer Staples,
  Energy, Healthcare, Industrials, Infrastructure, Property,
  Technology, Transportation

Reference: https://www.idx.co.id/en/market-data/sectors/
"""

IDX_STOCKS = {
    # ── 1. Finance (IFIN) ────────────────────────────────────────────────────
    # Banks, multifinance, insurance, securities
    "Finance": [
        # Big-4 + state banks
        "BBCA", "BBRI", "BMRI", "BBNI", "BBTN", "BRIS",
        # Large private banks
        "BNGA", "BTPS", "NISP", "BDMN", "BNII", "PNBN", "MEGA",
        # Regional banks
        "BJTM", "BJBR", "BBYB",
        # Digital / neo banks
        "ARTO", "AGRO", "BANK", "BCIC", "BINA",
        # Mid-size banks
        "BBMD", "BBKP", "BVIC", "DNAR", "INPC", "MCOR", "NOBU", "SDRA",
        # Multifinance
        "ADMF", "BFIN", "CFIN", "MFIN", "WOMF",
        # Insurance
        "PNLF", "AMAG", "ABDA", "ASRM", "MREI",
        # Securities / investment
        "TRIM", "PANS", "KREN",
    ],

    # ── 2. Basic Materials (IBMD) ────────────────────────────────────────────
    # Mining, metals, chemicals, paper, glass, cement
    "Basic Materials": [
        # Nickel / base metals
        "ANTM", "INCO", "MDKA", "NCKL", "AMMN", "DKFT",
        # Tin
        "TINS",
        # Gold
        "GOLD", "ARCI",
        # Other minerals
        "PSAB", "ZINC", "CITA",
        # Cement
        "INTP", "SMGR", "SMBR",
        # Steel / metal fabrication
        "LION", "LMSH", "JPRS", "ISSP", "BAJA",
        # Chemicals / plastics
        "BRNA", "TRST", "IGAR", "IMPC", "EKAD", "DPNS", "UNIC", "SRSN",
        # Pulp / paper
        "INKP", "TKIM", "FASW", "SPMA", "KDSI", "ALDO",
        # Glass / ceramics
        "AMFG", "KIAS", "ARNA",
    ],

    # ── 3. Consumer Cyclicals (ICUS) ─────────────────────────────────────────
    # Retail, automotive, media, apparel, restaurants, tourism
    "Consumer Cyclicals": [
        # Retail / department stores
        "AMRT", "MIDI", "LPPF", "MAPI", "ACES", "RALS", "CSAP",
        "MPPA", "SONA", "RANC", "MARK",
        # Restaurants / F&B chains
        "FAST", "MAPA",
        # Automotive OEM & parts
        "ASII", "AUTO", "SMSM", "IMAS", "GJTL", "INDS", "BRAM", "NIPS",
        # Cables / electronics
        "KBLI", "KBRI", "SCCO", "VOKS",
        # Media / entertainment
        "MNCN", "SCMA", "BMTR", "MLPL",
        # Apparel / lifestyle
        "WIIM", "RMBA",
    ],

    # ── 4. Consumer Staples (ICNS) ───────────────────────────────────────────
    # Food, beverages, tobacco, personal care, plantation
    "Consumer Staples": [
        # FMCG giants
        "UNVR", "ICBP", "INDF", "MYOR", "GGRM", "HMSP",
        # Food & beverage
        "ROTI", "CLEO", "ULTJ", "DLTA", "MLBI", "STTP", "ADES",
        "CEKA", "HOKI", "FOOD", "GOOD", "BISI", "AISA", "SKLT", "ALTO",
        # Household / personal care
        "TCID", "MBTO", "MRAT",
        # Palm oil / plantation
        "AALI", "LSIP", "SIMP", "SSMS", "SGRO", "PALM", "DSNG",
        "TAPG", "TBLA", "BWPT", "GZCO", "UNSP", "SMAR",
    ],

    # ── 5. Energy (IENR) ────────────────────────────────────────────────────
    # Coal, oil & gas, energy distribution
    "Energy": [
        # Coal miners
        "ADRO", "PTBA", "ITMG", "HRUM", "BYAN", "MYOH", "GEMS",
        "DEWA", "KKGI", "TOBA", "GTBO",
        # Oil & gas
        "MEDC", "ELSA", "PGAS", "RUIS", "ENRG",
        # Energy distribution
        "AKRA", "FIRE",
    ],

    # ── 6. Healthcare (IHLH) ────────────────────────────────────────────────
    # Pharma, hospitals, diagnostics
    "Healthcare": [
        # Pharma
        "KLBF", "TSPC", "KAEF", "INAF", "SOHO", "DVLA", "MERK",
        "PEHA", "SCPI", "PYFA",
        # Hospitals / diagnostics
        "MIKA", "HEAL", "DGNS", "PRDA", "BMHS",
    ],

    # ── 7. Industrials (IIND) ───────────────────────────────────────────────
    # Manufacturing, feed & poultry, construction materials, misc industrial
    "Industrials": [
        # Feed & poultry
        "CPIN", "JPFA", "MAIN",
        # Heavy equipment / misc industrial
        "MASA", "PRAS", "ETWA", "INCI", "ITIC",
        # Construction / state contractors
        "WIKA", "PTPP", "ADHI", "WSKT",
        # Private contractors / precast
        "ACST", "NRCA", "WTON", "WSBP", "BALI", "TOTL",
    ],

    # ── 8. Infrastructure (IIFR) ────────────────────────────────────────────
    # Toll roads, telco towers, utilities, power
    "Infrastructure": [
        # Toll roads
        "JSMR", "META",
        # Telco towers
        "TBIG", "TOWR", "MTEL",
        # Utilities / power
        "POWR", "PLTM", "KEEN",
        # Port / airport infra
        "IPCM",
    ],

    # ── 9. Property (IPRE) ──────────────────────────────────────────────────
    # Property developers, industrial estate, commercial
    "Property": [
        # Large developers
        "BSDE", "SMRA", "CTRA", "PWON", "LPKR", "MDLN", "DILD",
        "APLN", "BKSL", "JRPT", "KIJA", "ASRI",
        # Industrial estate
        "BEST", "DMAS", "MMLP", "SSIA",
        # Commercial / mixed
        "LPCK", "MKPI", "MTLA", "PPRO", "CITY",
        "EMDE", "GPRA", "NIRO", "PANI", "PLIN", "RODA",
    ],

    # ── 10. Technology (ITEC) ───────────────────────────────────────────────
    # Telecom operators, e-commerce, digital platforms, IT services
    "Technology": [
        # Telecom operators
        "TLKM", "ISAT", "EXCL", "FREN",
        # Digital platforms / e-commerce
        "EMTK", "BUKA", "GOTO", "DMMX", "MCAS",
        # IT services / hardware
        "MTDL", "MLPT", "LUCK", "DCII", "DNET", "KIOS",
        # Emerging tech
        "VKTR", "WIFI", "ATIC", "NELY", "LINK",
    ],

    # ── 11. Transportation (ITLG) ───────────────────────────────────────────
    # Aviation, shipping, logistics, land transport
    "Transportation": [
        # Aviation
        "GIAA",
        # Land transport
        "BIRD", "ASSA", "WEHA",
        # Shipping / sea freight
        "SMDR", "TMAS", "MBSS", "SAFE",
        # Logistics / distribution
        "CMPP",
    ],
}

ALL_IDX_STOCKS = []
for _sector, _stocks in IDX_STOCKS.items():
    for _s in _stocks:
        if _s not in ALL_IDX_STOCKS:
            ALL_IDX_STOCKS.append(_s)

# ── Sector index ETF proxies (for benchmark comparison) ──────────────────────
SECTOR_ETFS = {
    "Finance":           "BBCA.JK",
    "Basic Materials":   "ANTM.JK",
    "Consumer Cyclicals":"ASII.JK",
    "Consumer Staples":  "UNVR.JK",
    "Energy":            "ADRO.JK",
    "Healthcare":        "KLBF.JK",
    "Industrials":       "WIKA.JK",
    "Infrastructure":    "JSMR.JK",
    "Property":          "BSDE.JK",
    "Technology":        "TLKM.JK",
    "Transportation":    "GIAA.JK",
}

# ── Official IDX sector display icons ────────────────────────────────────────
SECTOR_ICONS = {
    "Finance":            "🏦",
    "Basic Materials":    "⛏️",
    "Consumer Cyclicals": "🛒",
    "Consumer Staples":   "🛍️",
    "Energy":             "⚡",
    "Healthcare":         "🏥",
    "Industrials":        "🏭",
    "Infrastructure":     "🛣️",
    "Property":           "🏠",
    "Technology":         "💻",
    "Transportation":     "🚢",
}

IHSG_TICKER = "^JKSE"

FOCUS_BROKERS = ["AK", "BK", "YP", "CC", "PD", "XL", "MG", "ZP", "RX", "OD"]

SCREENER_NAMES = {
    "ara_hunter":       "🎯 ARA HUNTER",
    "bsjp":             "📈 BSJP",
    "big_accumulation": "🏦 BIG ACCUMULATION",
    "scalper_pro":      "⚡ SCALPER PRO",
}

MIN_VALUE_ARA  = 5_000_000_000
MIN_VALUE_BSJP = 10_000_000_000
MIN_VALUE_BIG  = 3_000_000_000

# Persistent bottom keyboard button labels
BTN_SCREENER  = "📈 Screener"
BTN_HEATMAP   = "🔥 Heatmap"
BTN_SECTOR    = "🔄 Sector"
BTN_BANDAR    = "🏦 Bandar"
BTN_WATCHLIST = "📊 Watchlist"
BTN_MOMENTUM  = "⚡ Momentum"
BTN_FOREIGN   = "💰 Foreign Flow"
BTN_BREADTH   = "📉 Breadth"
BTN_MENU      = "🏠 Menu"
