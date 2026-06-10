IDX_STOCKS = {
    "Banking": [
        # Big-4 + state banks
        "BBCA", "BBRI", "BMRI", "BBNI", "BBTN", "BRIS",
        # Large private banks
        "BNGA", "BTPS", "NISP", "BDMN", "BNII", "PNBN", "MEGA",
        # Regional banks
        "BJTM", "BJBR", "BBYB",
        # Digital / growth banks
        "ARTO", "AGRO", "BANK", "BCIC", "BINA", "BMAS",
        # Mid-size banks
        "BBMD", "BBKP", "BVIC", "DNAR", "INPC", "MCOR", "NOBU", "SDRA",
        "BGTG", "BNBA", "BPBB",
    ],
    "Technology": [
        # Telecom operators
        "TLKM", "ISAT", "EXCL", "FREN",
        # Tech / digital platforms
        "EMTK", "BUKA", "GOTO", "DMMX", "MCAS", "KIOS", "MTDL",
        "MLPT", "LUCK", "DCII", "DNET", "VKTR", "WIFI", "ATIC",
        "NELY", "STAR", "PAZA",
    ],
    "Energy_Coal": [
        # Coal miners
        "ADRO", "PTBA", "ITMG", "HRUM", "BYAN", "MYOH", "GEMS",
        "DEWA", "KKGI", "TOBA", "GTBO", "PKPK", "SMMT",
        "BOSS",
        # Oil & gas
        "MEDC", "ELSA", "PGAS", "RUIS", "ENRG",
        # Energy / distribution
        "AKRA", "FIRE",
    ],
    "Metals_Mining": [
        # Base metals & nickel
        "ANTM", "INCO", "MDKA", "NCKL", "AMMN", "DKFT",
        # Tin
        "TINS",
        # Gold
        "GOLD", "ARCI",
        # Other mining
        "PSAB", "ZINC", "CITA", "MITI", "SMCB", "CMNT",
    ],
    "Consumer_Staples": [
        # FMCG giants
        "UNVR", "ICBP", "INDF", "MYOR", "GGRM", "HMSP",
        # Food & beverage
        "ROTI", "CLEO", "ULTJ", "DLTA", "MLBI", "STTP", "ADES",
        "CEKA", "HOKI", "FOOD", "GOOD", "BISI", "AISA",
        "SKLT", "PSDN", "ALTO", "CAMP",
        # Household / personal care
        "TCID", "MBTO", "MRAT",
    ],
    "Consumer_Discretionary": [
        # Restaurants / F&B chains
        "FAST", "KINO",
        # Apparel / lifestyle
        "WIIM", "RMBA", "LASO", "MPMX",
    ],
    "Healthcare": [
        # Pharma
        "KLBF", "TSPC", "KAEF", "INAF", "SOHO", "DVLA", "MERK",
        "PEHA", "SCPI", "PYFA",
        # Hospitals / diagnostics
        "MIKA", "HEAL", "DGNS", "PRDA", "BMHS", "PRAY",
    ],
    "Property": [
        # Diversified developers
        "BSDE", "SMRA", "CTRA", "PWON", "LPKR", "MDLN", "DILD",
        "APLN", "BKSL", "JRPT", "KIJA", "ASRI",
        # Industrial estate
        "BEST", "DMAS", "MMLP", "SSIA",
        # Commercial / mixed-use
        "LPCK", "MKPI", "MTLA", "PPRO", "CITY",
        "EMDE", "GPRA", "NIRO", "PANI", "PLIN", "RODA",
        "TARA", "GWSA", "IPAC",
    ],
    "Construction": [
        # State contractors
        "WIKA", "PTPP", "ADHI", "WSKT",
        # Private contractors / precast
        "ACST", "NRCA", "WTON", "WSBP", "DGIK",
        "IDPR", "PTSP", "BALI", "TOTL",
    ],
    "Infrastructure": [
        # Toll roads
        "JSMR", "META",
        # Tower / telco infra
        "TBIG", "TOWR", "MTEL",
        # Utilities / power
        "POWR", "PLTM", "KEEN",
    ],
    "Industrial_Manufacturing": [
        # Automotive OEM & parts
        "ASII", "AUTO", "SMSM", "IMAS", "GJTL", "INDS", "BRAM",
        "NIPS", "MASA", "PRAS",
        # Cement
        "INTP", "SMGR", "SMBR",
        # Steel / metal fabrication
        "LION", "LMSH", "JPRS", "ISSP", "BAJA", "KRAS",
        # Chemicals / plastics
        "BRNA", "TRST", "IGAR", "IMPC", "EKAD", "INCI", "DPNS",
        "UNIC", "SRSN",
        # Pulp / paper
        "INKP", "TKIM", "FASW", "SPMA", "KDSI", "ALDO",
        # Glass / ceramics
        "AMFG", "KIAS", "ARNA",
        # Cables / electronics
        "KBLI", "KBRI", "SCCO", "VOKS",
        # Feed & poultry
        "ETWA", "CPIN", "JPFA", "MAIN", "ITIC",
    ],
    "Finance_Multifinance": [
        # Multifinance
        "ADMF", "BFIN", "CFIN", "MFIN", "WOMF", "BPFI",
        # Insurance
        "PNLF", "AMAG", "ABDA", "AHAP", "ASRM", "MREI",
        # Securities / investment
        "TRIM", "PANS", "KREN", "MFAS", "APEX",
        # Holding / diversified finance
        "VRNA", "APIC", "ABMM",
    ],
    "Plantation": [
        # Palm oil
        "AALI", "LSIP", "SIMP", "SSMS", "SGRO", "PALM", "DSNG",
        "TAPG", "TBLA", "BWPT", "GZCO", "UNSP",
        # Other plantation
        "MAGP", "JAWA", "MSPT", "SMAR",
    ],
    "Media_Entertainment": [
        "MNCN", "SCMA", "BMTR", "MLPL", "KPIG",
        "JTPE", "BSTF", "LINK",
    ],
    "Transportation_Logistics": [
        # Aviation
        "GIAA",
        # Land transport / ride-hailing
        "BIRD", "ASSA", "WEHA",
        # Shipping / sea freight
        "SMDR", "TMAS", "MBSS", "SAFE",
        # Port / logistics
        "IPCM", "CMPP",
    ],
    "Retail_Trade": [
        "AMRT", "MIDI", "LPPF", "MAPI", "ACES", "RALS",
        "CSAP", "MPPA", "SONA", "RANC", "MARK", "SIDO",
    ],
}

ALL_IDX_STOCKS = []
for sector, stocks in IDX_STOCKS.items():
    for s in stocks:
        if s not in ALL_IDX_STOCKS:
            ALL_IDX_STOCKS.append(s)

FOCUS_BROKERS = ["AK", "BK", "YP", "CC", "PD", "XL", "MG", "ZP", "RX", "OD"]

SECTOR_ETFS = {
    "Banking":                  "BBCA.JK",
    "Technology":               "TLKM.JK",
    "Energy_Coal":              "ADRO.JK",
    "Metals_Mining":            "ANTM.JK",
    "Consumer_Staples":         "UNVR.JK",
    "Consumer_Discretionary":   "MAPI.JK",
    "Healthcare":               "KLBF.JK",
    "Property":                 "BSDE.JK",
    "Industrial_Manufacturing": "ASII.JK",
    "Infrastructure":           "JSMR.JK",
    "Finance_Multifinance":     "BBTN.JK",
    "Plantation":               "AALI.JK",
}

IHSG_TICKER = "^JKSE"

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
